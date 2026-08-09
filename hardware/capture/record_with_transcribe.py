#!/usr/bin/env python3
"""
EduPulse - VAD-segmented Capture + Real-time Light Transcription (Data Collection Tool)

This is the primary tool for a full-day capture run (e.g. "third day of final exams",
lots of logistics chatter).

What it does for an all-day run:
- Continuously listens to the radio (PX650 + UCA222 or compatible).
- Uses energy VAD (same as the test realtime script) to detect individual PTT transmissions
  (supports very short ~0.3-1s bursts and long ~30s ones).
- For *every* detected transmission:
  - Saves a raw audio file (timestamped tx_....wav, stereo 16 kHz, 16-bit PCM for fidelity
    and easy re-processing with heavier Whisper models later).
  - (Optionally) runs fast real-time transcription (tiny/base + int8 recommended for
    all-day reliability so the capture thread is never blocked).
  - Categorizes with the shared 12-category rudimentary classifier.
  - Links into INC-xxx using the full radio-protocol + student-anchor + role logic
    (Mr./Mister/Mrs./Misses/Ms./Miss/Coach as teacher/admin roles; Coach -> Athletic Department tag).
  - Optional audio "fingerprint": provide full teaching staff names + most common radio
    words via CLI. These are folded into the Whisper prompt and IncidentTracker so the
    model and name extractor are tuned to *this* channel's actual voices and vocabulary.
  - Writes a sidecar .json with ALL metadata (audio filename, times, confs, category,
    incident id, extracted students/roles, levels, etc.).
  - Appends a compact line to session_manifest.jsonl (great for later jq / pandas / analysis).
- Live metering + transcription printout exactly like the test realtime script (so you
  can watch in a tmux pane all day).
- Strong disk protection, rotation-friendly layout (date+label session dir), graceful
  shutdown (flushes queue, writes summary), Ctrl+C safe.
- Designed so that after the day you can:
  - Review the manifest + jsons for quick sense of the day.
  - Re-run heavier models (medium/large-v3) against the saved tx_*.wav files using
    test/test_whisper.py or a future reprocess script, producing updated sidecars or
    a validation report.
  - Iterate categorization / prompt / VAD params / IncidentTracker rules with real data.

Usage (last two days of school year):
    # CRITICAL: Do a 15-30 min real pre-flight test *today* (same hardware, same room) using the
    # command below. Only go for full days if the test produces mostly short segments, low noise
    # count, Testing category firing on checks, and sensible INCs.
    #
    # The script does a short 1.5s background measurement then *continuously adapts* the quiet
    # floor from the gaps between real (even sub-second) transmissions. The live line shows
    # q~ (current learned quiet) and thr~ (effective threshold). Use it to set gain so quiet gaps are -45 to -55 dB.
    tmux new -s edupulse

    # Inside the tmux session:
    cd ~/Documents/GrokBuild
    source ~/edupulse-env/bin/activate
    python hardware/capture/record_with_transcribe.py \
        --data-dir ~/edupulse/captures \
        --session "last-day-1" \
        --skip-calibration   # no pre-flight radio access — cold start both days (add backslash in real shell if continuing the command)
        --model tiny \
        --speech-threshold -32 \
        --silence-timeout 0.8 \
        --initial-prompt "School administrative radio traffic, logistics, dismissals, hallway movement, staff roles (Mr, Mrs, Coach, Nurse, Officer, etc.), EOC, 500 building, Chromebook, instructors, parent of student, room 4 of 4, Test Monitoring, Ms. Chandler:"

    # Or with a better real-time model on laptop (if it keeps up):
    ... --model base --beam-size 3

    # Pure capture (no Whisper cost, still perfect per-tx .wav + basic meta):
    ... --no-transcribe

    # Limit for a test:
    ... --max-duration 600

    # List categories:
    python hardware/capture/record_with_transcribe.py --list-categories

    # With audio fingerprint (staff names + common words) + VAD tuning for clean onsets/ends:
    python hardware/capture/record_with_transcribe.py \
        --skip-calibration \
        --known-staff-file staff_names.txt \
        --common-words-file common_radio_words.txt \
        --silence-timeout 1.0 \
        --tail-padding-sec 0.5 \
        --pre-roll-sec 0.3 \
        ... other flags ...

After the run you will have (example):
    ~/edupulse/captures/2026-06-05_finals-day3/
        tx_2026-06-05_08-12-03_2.8s.wav
        tx_2026-06-05_08-12-03_2.8s.json
        ...
        session_manifest.jsonl
        session_summary.json
        (plus your terminal log if you redirected)

See also:
- test/test_realtime_transcribe.py (the dev version of the live logic)
- test/test_whisper.py (for heavy offline re-transcription of the saved tx_*.wav)
- hardware/capture/README.md and the main project README

This script re-uses the proven threaded capture + VAD + worker architecture so new
transmissions are never dropped while a previous one is being transcribed.
"""

from __future__ import annotations

import argparse
import json
import math
import queue
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Allow running this script directly from hardware/capture/ (or any subdir)
# without setting PYTHONPATH or doing "pip install -e .".
# We walk upward from the script until we find the project root that contains
# an "edupulse/" package directory. This makes the documented commands work
# cleanly after "cd ... && source ~/edupulse-env/bin/activate".
_here = Path(__file__).resolve()
for _ in range(6):
    if (_here / "edupulse" / "__init__.py").exists():
        if str(_here) not in sys.path:
            sys.path.insert(0, str(_here))
        break
    _here = _here.parent
else:
    # Fallback (unusual layout)
    _root = Path(__file__).resolve().parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import numpy as np

# =============================================================================
# Shared analysis (categorization + INC-xxx linking with all the Mr/Coach/student rules)
# =============================================================================
from edupulse.analysis import (
    TRANSMISSION_CATEGORIES,
    build_enhanced_initial_prompt,
    categorize_transmission,
    IncidentTracker,
    is_likely_noise,
)

# =============================================================================
# Audio helpers (adapted from record_session.py + test_realtime_transcribe.py for laptop/Pi parity)
# =============================================================================

SAMPLE_RATE = 16000
CHANNELS = 2


def find_uca222() -> int | None:
    """Find a likely radio input device (UCA222 or compatible USB audio codec)."""
    import sounddevice as sd

    devices = sd.query_devices()
    candidates = []
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) < 1:
            continue
        name = d["name"].lower()
        score = 0
        if "uca222" in name or "behringer" in name:
            score = 100
        elif "pcm2902" in name:
            score = 80
        elif "usb audio codec" in name or "codec" in name:
            score = 60
        elif "usb audio" in name:
            score = 40
        if score > 0:
            candidates.append((score, i, d["name"]))
    if candidates:
        candidates.sort(reverse=True)
        best_score, best_idx, best_name = candidates[0]
        print(f"Found likely radio input: [{best_idx}] {best_name}")
        return best_idx
    return None


def db(x: float) -> float:
    if x <= 1e-8:
        return -80.0
    return 20 * np.log10(x)


def get_levels(audio: np.ndarray) -> dict[str, float]:
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
    rms_l = float(np.sqrt(np.mean(audio[:, 0] ** 2)))
    rms_r = float(np.sqrt(np.mean(audio[:, 1] ** 2))) if audio.shape[1] > 1 else rms_l
    peak_l = float(np.max(np.abs(audio[:, 0])))
    peak_r = float(np.max(np.abs(audio[:, 1]))) if audio.shape[1] > 1 else peak_l
    return {
        "rms_l": rms_l,
        "rms_r": rms_r,
        "peak_l": peak_l,
        "peak_r": peak_r,
        "db_rms_l": db(rms_l),
        "db_rms_r": db(rms_r),
        "db_peak_l": db(peak_l),
        "db_peak_r": db(peak_r),
    }


def downmix_to_mono(audio: np.ndarray) -> np.ndarray:
    """Dominant channel (usually R on PX650 2.5mm cable) + simple peak normalization.
    This is what we feed to Whisper for best radio results.
    """
    if audio.ndim == 1:
        return audio
    if audio.shape[1] == 1:
        return audio[:, 0]

    rms_l = np.sqrt(np.mean(audio[:, 0] ** 2))
    rms_r = np.sqrt(np.mean(audio[:, 1] ** 2))
    mono = audio[:, 0] if rms_l > rms_r else audio[:, 1]

    peak = np.max(np.abs(mono))
    if peak > 1e-6:
        mono = mono / peak
    return mono.astype(np.float32)


# =============================================================================
# Main capture + transcribe logic
# =============================================================================

stop_capture = False


def signal_handler(sig, frame):
    global stop_capture
    print("\n\nStopping capture (Ctrl+C received)...")
    stop_capture = True


def list_categories():
    print("Current rudimentary transmission categories (keyword-based):")
    for cat, kws in TRANSMISSION_CATEGORIES.items():
        print(f"  - {cat}")
        if kws:
            print(f"      keywords: {', '.join(kws)}")
    print("\n(These + the IncidentTracker rules live in edupulse/analysis.py)")


def run_capture(
    data_dir: Path,
    session_label: str | None = None,
    device: int | None = None,
    speech_threshold_db: float = -32.0,
    silence_timeout: float = 0.8,
    min_speech_sec: float = 0.3,
    max_segment_sec: float = 30.0,
    tail_padding_sec: float = 0.4,  # extra audio appended after silence detected, to avoid cutting off the end of transmissions and make playback feel more natural (not choppy/abrupt)
    pre_roll_sec: float = 0.25,  # audio to include *before* the energy first crosses the speech threshold (via rolling lookback buffer). Prevents the beginning of transmissions from being cut off slightly.
    model_name: str = "tiny",
    language: str | None = None,
    max_duration: float | None = None,
    beam_size: int = 5,
    temperature: float = 0.0,
    initial_prompt: str | None = None,
    transcribe: bool = True,
    skip_calibration: bool = False,
    known_staff_names: list[str] | None = None,
    common_words: list[str] | None = None,
):
    """Long-running VAD capture + optional real-time light transcription + full metadata persistence.

    Fingerprint support (new):
      known_staff_names + common_words are used to:
      - Build an enhanced Whisper `initial_prompt` (the "audio fingerprint") so the model
        better recognizes actual staff names and the most common words on this radio channel.
      - Pass known staff full names into IncidentTracker so "First Last" staff names are
        correctly treated as roles (not students) and do not pollute student-anchored INCs.

    Provide the lists via CLI --known-staff / --known-staff-file and --common-words / --common-words-file.
    """
    global stop_capture

    import sounddevice as sd
    import soundfile as sf

    data_dir = data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Session directory: date + optional label for easy organization of multi-day runs
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_label = None
    if session_label:
        safe_label = "".join(c for c in session_label if c.isalnum() or c in ("-", "_")).strip()[:40]
    session_dir_name = f"{date_str}_{safe_label}" if safe_label else date_str
    session_dir = data_dir / session_dir_name
    session_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = session_dir / "session_manifest.jsonl"
    summary_path = session_dir / "session_summary.json"
    info_path = session_dir / "session_info.json"

    dev = device or find_uca222()
    if dev is None:
        print("Warning: Could not auto-detect radio input device. Using system default.")

    signal.signal(signal.SIGINT, signal_handler)

    print("=" * 72)
    print("EDUPULSE - VAD CAPTURE + REAL-TIME TRANSCRIPTION (DATA COLLECTION)")
    print("=" * 72)
    print(f"Session dir       : {session_dir}")
    print(f"Sample rate       : {SAMPLE_RATE} Hz  Channels: {CHANNELS}")
    print(f"Device            : {dev if dev is not None else 'default'}")
    print(f"Speech threshold  : {speech_threshold_db:.1f} dB")
    print(f"Silence timeout   : {silence_timeout:.1f} s")
    print(f"Min speech        : {min_speech_sec:.1f} s")
    print(f"Max segment       : {max_segment_sec:.1f} s")
    print(f"Tail padding      : {tail_padding_sec:.1f} s (to prevent early cutoff and choppy feel)")
    print(f"Pre-roll          : {pre_roll_sec:.2f} s (to avoid clipping the very start of transmissions)")
    if transcribe:
        print(f"Whisper model     : {model_name} (for real-time; heavier models later on saved .wav)")
    else:
        print("Mode              : PURE CAPTURE (no transcription, still full per-tx .wav + basic meta)")
    if max_duration:
        print(f"Max duration      : {max_duration:.0f} s (test mode)")

    # Use fingerprint (known staff + common words) to build the best possible Whisper prompt.
    # This is the main way the "audio fingerprint" helps real-time transcription accuracy.
    initial_prompt = build_enhanced_initial_prompt(
        base=initial_prompt,
        known_staff=known_staff_names,
        common_words=common_words,
    )

    if skip_calibration:
        print()
        print("*** COLD START / NO PRE-FLIGHT MODE ***")
        print("  You have no radio access before the school day starts.")
        print("  The first transmissions may be captured with whatever gain was left from the previous day.")
        print("  The system seeds quiet very low and adapts *fast* from the first real quiet gaps.")
        print("  Watch the live line for q~ and the [GAIN HIGH] warnings.")
        print("  On the first quiet gap after you arrive / between periods / after bells: turn the knob DOWN.")
        print("  Early bad segments will be auto-flagged as Noise and will NOT create fake INCs or pollute stats.")
        print("  Once corrected, the rest of the day should be clean short segments.")
    print()
    print("OUTPUT:")
    print("  - tx_YYYY-MM-DD_HH-MM-SS_dur.wav   (raw stereo 16-bit PCM per transmission)")
    print("  - tx_....json                      (sidecar: transcription, INC, confs, students, roles, ...)")
    print("  - session_manifest.jsonl           (one compact line per tx - easy to analyze)")
    print("  - session_summary.json + info.json at end")
    print()
    print("CONTROLS / TIPS:")
    print("  - Adjust radio volume + UCA222 gains while watching live RMS/peak + q~ (quiet floor) + thr~ (current threshold).")
    print("  - The capture loop *never blocks* on Whisper. New tx are buffered while previous are transcribed.")
    print("  - Students (full First Last) are strong anchors for INC-xxx. Role calls (Mr./Coach/Nurse/...)")
    print("    usually start a fresh INC unless linked by a student mention.")
    print("  - Noise/static segments are auto-bucketed (Noise / Squelch / Hallucination) and do not create INCs.")
    print("  - Press Ctrl+C for clean stop (flushes work, writes summary).")
    print("=" * 72)
    print("\nStarting in 3 seconds...\n")
    time.sleep(3)

    # Write session info for reproducibility
    session_info = {
        "start_iso": datetime.now().isoformat(),
        "session_label": session_label,
        "data_dir": str(data_dir),
        "session_dir": str(session_dir),
        "args": {
            "speech_threshold_db": speech_threshold_db,
            "silence_timeout": silence_timeout,
            "min_speech_sec": min_speech_sec,
            "tail_padding_sec": tail_padding_sec,
            "pre_roll_sec": pre_roll_sec,
            "model_name": model_name if transcribe else None,
            "beam_size": beam_size,
            "temperature": temperature,
            "skip_calibration": skip_calibration,
            "known_staff_count": len(known_staff_names or []),
            "common_words_count": len(common_words or []),
        },
        "git_commit": None,  # TODO: could run git rev-parse if wanted
    }
    with open(info_path, "w") as f:
        json.dump(session_info, f, indent=2)

    # Load Whisper only if transcribing
    whisper_model = None
    if transcribe:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            print("ERROR: faster-whisper not installed. pip install faster-whisper")
            sys.exit(1)
        print("Loading Whisper model for real-time (this can take a moment on first run)...")
        whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
        print("Model ready.\n")

    tracker = IncidentTracker(known_staff_names=known_staff_names)  # one tracker for the whole day/session

    stop_event = threading.Event()
    segment_queue: queue.Queue = queue.Queue(maxsize=30)  # a bit larger buffer for long day

    total_start = time.time()
    last_level_print = 0.0
    tx_count = 0
    total_speech_sec = 0.0
    category_counts: dict[str, int] = {}

    def audio_capture_loop():
        """Dedicated thread: VAD, save raw per-tx WAV immediately, enqueue mono for (optional) transcription."""
        nonlocal last_level_print, tx_count, total_speech_sec
        stream = None
        audio_buffer: list[np.ndarray] = []
        is_speaking = False
        silence_start = None
        segment_start_time = None
        segment_done_time = None
        # Rolling pre-roll buffer for capturing the start of transmissions (to fix "beginning cut off just slightly")
        pre_buffer: list[np.ndarray] = []
        pre_roll_blocks = max(1, int(pre_roll_sec * SAMPLE_RATE / 1024))
        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                device=dev,
                blocksize=1024,
            )
            stream.start()

            # --- Noise floor calibration / gain staging advice (learned from the June 3 all-day run) ---
            # The #1 problem observed: radio squelch/hiss was above the threshold even when no one was keyed,
            # producing 30s max-length noise files + Whisper repetitive hallucinations.
            # 
            # KEY POINT: We are measuring the *background level when the radio is idle* (squelch closed, no PTT).
            # Real transmissions break that background "almost instantaneously" (as you said) — that's what we *want*.
            # The goal of knob adjustment is to make the *quiet gaps* sit at -45 to -55 dB so that even a 0.5s PTT jumps clearly above it.
            print("\n[GAIN STAGING] Adjust UCA222 Line/In knob + radio volume NOW so *quiet* (no one keyed) is low.")
            print("  Target for idle/squelch-closed gaps: dominant RMS -45 to -55 dB or lower.")
            print("  A real PTT (even <1s) should then push it to -25 dB or much higher.")
            print("  The system now continuously learns the actual quiet floor from the gaps between transmissions.")
            print("  Watch the 'q~' (quiet) and 'thr~' (effective threshold) numbers in the live line.")
            print("  If quiet gaps are only -10 or -5 dB, turn the physical knob DOWN.\n")

            # Initial best-effort noise floor measurement.
            # IMPORTANT: This measures the *background* when the radio is idle (squelch closed, no PTT keyed).
            # Real transmissions (even 0.3-1s PTTs) are *supposed* to be much louder than this background.
            # The 1.5s sample is just a starting seed. If the channel has traffic right at startup,
            # the measurement may be polluted — that's OK, the live RMS + running adaptation below will show you the real quiet level
            # as soon as a gap appears. Use the live numbers to finish adjusting the knob.
            if skip_calibration:
                print("[COLD START / NO PRE-FLIGHT] Skipping initial background measurement.")
                print("  System will seed a conservative quiet floor (-55 dB) and learn *fast* from the first real quiet gaps between transmissions.")
                print("  Expect possible early noisy segments if the knob is still high from previous day.")
                print("  PROTOCOL: As soon as the first quiet gap appears (after arrival, between periods, after bells), watch the live line and turn the UCA222 knob DOWN until q~ drops to -45..-55.")
                floor = -55.0
                high_spike_seen = False
            else:
                print("[CALIBRATION] Measuring background (idle) level for 1.5s. Turn UCA222 knob(s) so that when NO ONE is keyed up the dominant RMS is -45 to -55 dB.")
                print("  Transmissions (even very short ones) will be much louder — we deliberately want the quiet gaps to sit low so short bursts stand out.")
                noise_samples = []
                high_spike_seen = False
                for i in range(15):  # shortened to 1.5s to reduce chance of hitting a transmission
                    a, _ = stream.read(1024)
                    nl = get_levels(a)
                    ndb = max(nl["db_rms_l"], nl["db_rms_r"])
                    noise_samples.append(ndb)
                    if ndb > -20:  # any block this loud during "calibration" is probably a transmission
                        high_spike_seen = True
                    ch_note = ""
                    if nl["db_rms_l"] > nl["db_rms_r"] + 6:
                        ch_note = " [L]"
                    elif nl["db_rms_r"] > nl["db_rms_l"] + 6:
                        ch_note = " [R]"
                    print(f"  CAL [{i+1:2d}/15] RMS L:{nl['db_rms_l']:5.1f} R:{nl['db_rms_r']:5.1f} dB{ch_note}", end="\r")
                    time.sleep(0.1)
                print()
                if noise_samples:
                    floor = sum(noise_samples) / len(noise_samples)
                    suggested = round(floor + 12, 1)
                    print(f"[NOISE FLOOR] Initial background measurement ~{floor:.1f} dB")
                    if high_spike_seen:
                        print("  (Note: saw loud spikes during measurement — likely a transmission. Will adapt live below.)")
                    print(f"  Suggested --speech-threshold for this gain: {suggested:.1f} (you can restart with it if you want)")
                    if floor > speech_threshold_db - 8:
                        print("  >>> Current threshold may be too sensitive for the measured background.")
            print("Starting main loop + live adaptation. Watch q~ and thr~ — adjust knob on the first quiet gap.\n")

            # For channel note de-dupe (to avoid spamming [L] every line when one channel dominates, as is common on your hardware)
            audio_capture_loop._last_ch_note = None
            audio_capture_loop._ch_note_printed = False
            audio_capture_loop._channel_info_printed = False

            # Running background (quiet) floor estimate.
            # For --skip-calibration (cold start / no pre-flight): start very conservative low so we don't trigger on high background initially.
            # Adaptation will pull it up or down from actual gaps very quickly (faster learning rate at beginning).
            initial_quiet_seed = floor if 'floor' in locals() else -55.0
            quiet_db_ema = initial_quiet_seed
            cold_start = skip_calibration
            cold_start_elapsed_for_fast_adapt = 300.0  # first 5 min use faster adaptation

            while not stop_event.is_set():
                if max_duration and (time.time() - total_start) >= max_duration:
                    print("\nMax duration reached.")
                    stop_event.set()
                    break

                audio, _ = stream.read(1024)
                now = time.time()

                # Maintain rolling pre-roll lookback (always keep last ~pre_roll_sec of audio blocks)
                pre_buffer.append(audio.copy())
                if len(pre_buffer) > pre_roll_blocks:
                    pre_buffer.pop(0)

                # Compute levels + dominant once
                levels = get_levels(audio)
                dominant_rms = max(levels["rms_l"], levels["rms_r"])
                dominant_db = 20 * np.log10(dominant_rms + 1e-8)

                # One-time note about channel dominance (common on this hardware: radio audio is almost always almost entirely on one channel)
                if not getattr(audio_capture_loop, "_channel_info_printed", False):
                    if levels["db_rms_l"] > levels["db_rms_r"] + 10:
                        print("\n[INFO] Audio is predominantly on LEFT channel (normal for PX650 + UCA222 cabling). Dominant channel is auto-selected for transcription and metering. The [L]/[R] note will only appear on change.")
                        audio_capture_loop._channel_info_printed = True
                    elif levels["db_rms_r"] > levels["db_rms_l"] + 10:
                        print("\n[INFO] Audio is predominantly on RIGHT channel (normal for PX650 + UCA222 cabling). Dominant channel is auto-selected for transcription and metering. The [L]/[R] note will only appear on change.")
                        audio_capture_loop._channel_info_printed = True

                # Update running quiet/background floor from blocks that are not obviously loud.
                # Because real PTTs can be <1s and "almost instantaneous", we rely on the gaps between them.
                # Only pull the estimate toward values that are close to or below the current estimate.
                # Cold start / early run: learn faster from gaps so we recover quickly once user adjusts the knob.
                learn_rate = 0.25 if (cold_start and (now - total_start) < cold_start_elapsed_for_fast_adapt) else 0.05
                if dominant_db < quiet_db_ema + 6:
                    quiet_db_ema = (1 - learn_rate) * quiet_db_ema + learn_rate * dominant_db

                # Hybrid threshold:
                # - Respect the user's --speech-threshold as a hard floor (they can raise it if wanted).
                # - Also require the signal to be clearly above the *measured recent quiet level* (default +10 dB).
                # Cold start: start with a bit more margin (15 dB) for the first 5 min so we are less likely to flood on bad initial gain.
                # Once a good quiet gap is seen and q drops, it will behave normally.
                adaptive_margin = 15.0 if (cold_start and (now - total_start) < cold_start_elapsed_for_fast_adapt) else 10.0
                effective_threshold = max(speech_threshold_db, quiet_db_ema + adaptive_margin)
                is_speech = dominant_db > effective_threshold

                # Always show live metering (helps tuning all day)
                if now - last_level_print > 0.3:
                    # Only note channel dominance once or on change (your hardware typically has audio almost entirely on one channel)
                    # This reduces log spam while still letting you know the dominant side for troubleshooting.
                    if not hasattr(audio_capture_loop, "_last_ch_note"):
                        audio_capture_loop._last_ch_note = None
                    if levels["db_rms_l"] > levels["db_rms_r"] + 6:
                        curr = "L"
                    elif levels["db_rms_r"] > levels["db_rms_l"] + 6:
                        curr = "R"
                    else:
                        curr = ""
                    if curr != audio_capture_loop._last_ch_note:
                        ch_note = f" [{curr}]" if curr else ""
                        audio_capture_loop._last_ch_note = curr
                        if curr and not getattr(audio_capture_loop, "_ch_note_printed", False):
                            print(f"\n[INFO] Dominant channel is {curr} (typical for PX650 cabling — code auto-selects the louder channel for transcription).")
                            audio_capture_loop._ch_note_printed = True
                    else:
                        ch_note = ""
                    # Show the current adaptive quiet floor and effective threshold so user can see the system adapting in real time
                    extra = f"  q~{quiet_db_ema:.1f} thr~{effective_threshold:.1f}"
                    gain_status = ""
                    if quiet_db_ema > -35.0:
                        gain_status = "  [!!! GAIN TOO HIGH - ADJUST KNOB ON NEXT QUIET GAP !!!]"
                    print(
                        f"[{int(now - total_start):5d}s] "
                        f"RMS L:{levels['db_rms_l']:5.1f} R:{levels['db_rms_r']:5.1f} dB  "
                        f"Peak L:{levels['db_peak_l']:5.1f} R:{levels['db_peak_r']:5.1f} dB{ch_note}{extra}{gain_status}",
                        end="\r",
                    )
                    last_level_print = now

                    # Persistent loud warnings for cold start / high background (user has no pre-flight, must fix live during school day)
                    if quiet_db_ema > -35.0 and (now - total_start) > 60 and ((now - total_start) % 45 < 1):
                        # Every ~45s after first minute, if still bad, print a full line (not \r) so it doesn't get lost
                        print(f"\n!!! GAIN STILL TOO HIGH (learned quiet q~ = {quiet_db_ema:.1f} dB) !!!")
                        print("    During the next quiet gap (passing period, after bell, between classes, when radio is silent):")
                        print("    Turn the UCA222 'Line In' / input knob DOWN. Watch the q~ number drop in real time.")
                        print("    Once q~ reaches -45 to -55, the VAD will stop flooding on static and segments will be short & clean.")
                        print("    Early noisy segments are auto-bucketed as Noise and will not pollute your real INCs or stats.\n")

                # VAD with tail padding to avoid cutting off the end of transmissions (common complaint with radio squelch/fading)
                # and to make saved clips sound less "choppy" / abrupt compared to real-time listening.
                # We keep buffering (appending low-energy blocks) for silence_timeout + tail_padding_sec
                # after energy drops, so the utterance tail is included.
                # Improved VAD with tail padding:
                # - Buffer speech blocks while energy high.
                # - When energy drops, start silence timer.
                # - After silence_timeout we mark speaking done, BUT continue appending the next 'tail_padding_sec'
                #   worth of (low energy) blocks. This ensures the end of the utterance (fading speech, radio tail)
                #   is not cut off, and each saved .wav ends more naturally instead of feeling chopped/abrupt/choppy
                #   compared to real-time listening.
                if is_speech:
                    if not is_speaking:
                        is_speaking = True
                        # Prepend the recent pre-roll so the beginning isn't cut off (ramp-up energy before threshold crossed)
                        audio_buffer = pre_buffer[:] + [audio.copy()]
                        segment_start_time = now
                        silence_start = None
                        segment_done_time = None
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> Speech detected (buffering tx)")
                    else:
                        audio_buffer.append(audio.copy())
                        silence_start = None
                        segment_done_time = None

                    if segment_start_time and (now - segment_start_time) > max_segment_sec:
                        print("\n>>> Max segment length reached, finishing tx...")
                        is_speaking = False
                        segment_done_time = now
                else:
                    if is_speaking:
                        if silence_start is None:
                            silence_start = now
                        silence_dur = now - silence_start
                        if silence_dur >= silence_timeout and segment_done_time is None:
                            is_speaking = False
                            segment_done_time = now
                    # Keep appending during the timeout countdown + tail padding period
                    # (these appended blocks after done_time are the "tail" that prevents early cutoff)
                    if silence_start is not None:
                        time_since_done = now - (segment_done_time or silence_start)
                        if time_since_done <= (silence_timeout if segment_done_time is None else 0) + tail_padding_sec:
                            audio_buffer.append(audio.copy())

                # Segment complete -> save raw audio + enqueue for analysis
                cut_now = False
                if segment_done_time is not None and (now - segment_done_time) > tail_padding_sec and audio_buffer and segment_start_time:
                    cut_now = True
                elif (not is_speaking) and segment_done_time is None and audio_buffer and segment_start_time:
                    cut_now = True

                if cut_now:
                    full_raw = np.concatenate(audio_buffer, axis=0)
                    duration = len(full_raw) / SAMPLE_RATE

                    if duration >= min_speech_sec:
                        wall_dt = datetime.now()
                        ts_str = wall_dt.strftime("%Y-%m-%d_%H-%M-%S")
                        dur_str = f"{duration:.1f}s"
                        wav_name = f"tx_{ts_str}_{dur_str}.wav"
                        wav_path = session_dir / wav_name

                        # Save *raw* capture (stereo) as 16-bit PCM so heavier models later have clean input
                        try:
                            audio_i16 = (full_raw * 32767.0).clip(-32768, 32767).astype("int16")
                            sf.write(str(wav_path), audio_i16, SAMPLE_RATE, subtype="PCM_16")
                        except Exception as e:
                            print(f"\nWarning: failed to write {wav_name}: {e}")
                            wav_path = None

                        # Prepare mono (dominant + norm) for Whisper
                        mono_audio = downmix_to_mono(full_raw)

                        # Snapshot of levels during the transmission (max RMS etc. could be enhanced)
                        seg_levels = {
                            "db_rms_max_l": float(np.max([get_levels(b)["db_rms_l"] for b in audio_buffer])),
                            "db_rms_max_r": float(np.max([get_levels(b)["db_rms_r"] for b in audio_buffer])),
                        }

                        tx_count += 1
                        total_speech_sec += duration

                        # Enqueue for worker (transcription + meta writing)
                        item = (mono_audio, wall_dt, duration, str(wav_path) if wav_path else None, seg_levels)
                        try:
                            segment_queue.put_nowait(item)
                        except queue.Full:
                            print("\nWarning: analysis queue full, dropping a transmission.")

                    # reset for next tx
                    audio_buffer = []
                    segment_start_time = None
                    silence_start = None
                    segment_done_time = None

                # Safety cap on buffer memory
                if len(audio_buffer) > int((max_segment_sec + 5) * SAMPLE_RATE / 1024):
                    audio_buffer = audio_buffer[-int(5 * SAMPLE_RATE / 1024):]

        except Exception as e:
            print(f"\nError in audio capture loop: {e}")
            stop_event.set()
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

    def analysis_worker():
        """Background worker: (optional) Whisper + categorize + INC + write .json + manifest line + print."""
        nonlocal total_speech_sec
        while not stop_event.is_set() or not segment_queue.empty():
            try:
                mono_audio, wall_dt, duration, wav_path_str, seg_levels = segment_queue.get(timeout=0.5)
                wall_ts = wall_dt.strftime("%H:%M:%S")
                print(f"\n[{wall_ts}] >>> Processing {duration:.1f}s transmission...")

                cat_result = {"category": "Other / Unclear", "confidence": 0.0, "matched_keywords": []}
                transcription = ""
                conf = 0.0
                inc_id = "INC-000"
                students: list[str] = []
                roles: list[str] = []
                cat_str = "Other / Unclear"
                cat_conf = 0.0

                if transcribe and whisper_model is not None:
                    try:
                        segments, info = whisper_model.transcribe(
                            mono_audio,
                            beam_size=beam_size,
                            temperature=temperature,
                            initial_prompt=initial_prompt,
                            language=language,
                            vad_filter=False,
                            condition_on_previous_text=False,
                        )
                        seg_list = list(segments)
                        if seg_list:
                            seg = seg_list[0]  # we already segmented
                            conf = math.exp(seg.avg_logprob)
                            transcription = seg.text.strip()

                            if is_likely_noise(transcription, duration, conf):
                                cat_str = "Noise / Squelch / Hallucination"
                                cat_conf = 0.95
                                cat_result = {"category": cat_str, "confidence": cat_conf, "matched_keywords": []}
                                inc_id = "NOISE"
                                students = []
                                roles = []
                                print(
                                    f"[{wall_ts} +{seg.start:5.1f}s] "
                                    f"[NOISE] (conf {conf:.2f}) "
                                    f"duration {duration:.1f}s — likely static/hallucination, skipping INC linking"
                                )
                                category_counts[cat_str] = category_counts.get(cat_str, 0) + 1
                            else:
                                cat_result = categorize_transmission(transcription)
                                cat_str = cat_result["category"]
                                cat_conf = cat_result["confidence"]

                                inc_id = tracker.get_incident_id(
                                    transcription, wall_dt, cat_str, whisper_conf=conf, cat_conf=cat_conf
                                )

                                # Re-extract for the sidecar (cheap; same rules as linking)
                                ex = tracker._extract_names(transcription)
                                students = ex.get("students", [])
                                roles = ex.get("roles", [])

                                print(
                                    f"[{wall_ts} +{seg.start:5.1f}s] "
                                    f"[{inc_id}] "
                                    f"(conf {conf:.2f}) "
                                    f"[{cat_str} conf:{cat_conf:.2f}] "
                                    f"{transcription}"
                                )

                                # update counters
                                category_counts[cat_str] = category_counts.get(cat_str, 0) + 1
                        else:
                            print(f"[{wall_ts}] (no speech in model output)")
                    except Exception as e:
                        print(f"Transcription/analysis error: {e}")
                        # still write a minimal json with the audio ref
                        transcription = ""
                else:
                    # Pure capture or no model: still give a basic category from empty (Other) and a new INC?
                    # For pure capture we can still run a trivial categorization or just mark as captured.
                    cat_result = {"category": "Other / Unclear", "confidence": 0.0, "matched_keywords": []}
                    cat_str = "Other / Unclear"
                    cat_conf = 0.0
                    inc_id = tracker.get_incident_id("", wall_dt, "Other / Unclear")
                    print(f"[{wall_ts}] [CAPTURED] {duration:.1f}s raw -> {Path(wav_path_str).name if wav_path_str else 'no file'}")

                # Write sidecar JSON (always, even in pure capture mode)
                if wav_path_str:
                    meta = {
                        "audio_file": Path(wav_path_str).name,
                        "start_iso": wall_dt.isoformat(),
                        "duration_sec": round(duration, 2),
                        "levels": seg_levels,
                        "model": model_name if transcribe else None,
                        "transcription": transcription,
                        "whisper_conf": round(conf, 4) if transcribe else None,
                        "category": cat_result["category"],
                        "cat_conf": cat_result["confidence"],
                        "incident_id": inc_id,
                        "students": students,
                        "roles": roles,
                    }
                    try:
                        with open(Path(wav_path_str).with_suffix(".json"), "w") as jf:
                            json.dump(meta, jf, indent=2)
                    except Exception as e:
                        print(f"Warning: failed to write sidecar json: {e}")

                    # Append to manifest (jsonl - append only, robust)
                    try:
                        manifest_entry = {
                            "audio_file": meta["audio_file"],
                            "start_iso": meta["start_iso"],
                            "duration_sec": meta["duration_sec"],
                            "transcription": transcription,
                            "whisper_conf": meta["whisper_conf"],
                            "category": meta["category"],
                            "cat_conf": meta["cat_conf"],
                            "incident_id": inc_id,
                            "students": students,
                            "roles": roles,
                        }
                        with open(manifest_path, "a") as mf:
                            mf.write(json.dumps(manifest_entry, ensure_ascii=False) + "\n")
                    except Exception as e:
                        print(f"Warning: failed to append to manifest: {e}")

                segment_queue.task_done()
            except queue.Empty:
                continue

    # Start threads
    audio_thread = threading.Thread(target=audio_capture_loop, daemon=True)
    worker_thread = threading.Thread(target=analysis_worker, daemon=True)
    audio_thread.start()
    worker_thread.start()

    # Main waits
    try:
        while not stop_capture and not stop_event.is_set():
            if max_duration and (time.time() - total_start) >= max_duration:
                stop_event.set()
                break
            time.sleep(0.2)
    except Exception as e:
        print(f"\nError in main loop: {e}")
        stop_event.set()
    finally:
        stop_event.set()
        try:
            segment_queue.join()
        except Exception:
            pass
        audio_thread.join(timeout=2.0)
        worker_thread.join(timeout=30.0)  # give last transcriptions time

        elapsed = time.time() - total_start
        print("\n\nCapture stopped.")
        print(f"Elapsed           : {elapsed:.1f} s")
        print(f"Transmissions     : {tx_count}")
        print(f"Total speech time : {total_speech_sec:.1f} s")
        print(f"Incidents created : {tracker.next_id - 1}")
        noise_cnt = category_counts.get("Noise / Squelch / Hallucination", 0)
        if noise_cnt:
            print(f"  (of which {noise_cnt} were auto-flagged as noise/static/hallucination and did not create INCs)")
        if category_counts:
            print("Top categories    :")
            for cat, cnt in sorted(category_counts.items(), key=lambda x: -x[1])[:5]:
                print(f"  {cnt:4d}  {cat}")

        # Final summary
        summary = {
            "end_iso": datetime.now().isoformat(),
            "elapsed_sec": round(elapsed, 1),
            "transmissions": tx_count,
            "total_speech_sec": round(total_speech_sec, 1),
            "incidents": tracker.next_id - 1,
            "category_counts": category_counts,
            "session_dir": str(session_dir),
            "manifest": str(manifest_path),
        }
        try:
            with open(summary_path, "w") as sf:
                json.dump(summary, sf, indent=2)
            print(f"\nSummary written to: {summary_path}")
        except Exception:
            pass

        # Explicit reminder for the tight end-of-year + long break
        noise_cnt = category_counts.get("Noise / Squelch / Hallucination", 0)
        print("\n" + "="*70)
        print("END-OF-RUN REMINDER (you have very little live time left)")
        print(f"  Usable-ish tx (non-noise): {tx_count - noise_cnt}")
        print("  The .wav files + sidecars in this session dir are now your primary")
        print("  asset for the 3-month break. Re-process them with heavier models,")
        print("  iterate rules in edupulse/analysis.py, validate by listening, etc.")
        print("  See hardware/capture/LAST_TWO_DAYS_AND_BREAK_PLAN.md for the overall")
        print("  schedule and offline plan.")
        print("="*70)

        print(f"\nAll artifacts in: {session_dir}")
        print("You can now iterate: review the manifest, re-transcribe selected tx_*.wav with larger models, etc.")


def main():
    parser = argparse.ArgumentParser(
        description="EduPulse long-running capture + real-time light transcription for data collection days"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / "edupulse" / "captures",
        help="Base directory for session captures (will create dated subdir inside)",
    )
    parser.add_argument(
        "--session",
        "--session-label",
        dest="session_label",
        default=None,
        help="Label for this run (e.g. finals-day3) - included in session directory name",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=None,
        help="Sound device index (use --list-devices; WASAPI on Windows, ALSA/etc on Linux)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List sounddevice input devices (Windows/Linux) and exit",
    )
    parser.add_argument("--speech-threshold", type=float, default=-32.0, dest="speech_threshold",
                        help="RMS dB threshold for speech (hard lower bound, default -32). "
                             "The system does a short background measurement at start then continuously adapts "
                             "the quiet floor (q~) from gaps between real (even <1s) transmissions. Live metering "
                             "shows q~ (learned quiet) and thr~ (effective = max(this value, q+10dB)). "
                             "Adjust UCA222 knob until quiet gaps show q around -45 to -55 dB.")
    parser.add_argument("--silence-timeout", type=float, default=0.8,
                        help="Seconds of silence to end a transmission segment (0.8s default for natural radio feel without cutting off ends; lower if rapid calls are merging into one tx). Use with --pre-roll-sec and --tail-padding-sec for clean segment boundaries.")
    parser.add_argument("--tail-padding-sec", type=float, default=0.4,
                        help="Extra seconds of audio (including low-energy tail) to keep at end of each segment. Helps prevent 'cutting off too early' and makes individual recordings sound less choppy/abrupt compared to real-time.")
    parser.add_argument("--pre-roll-sec", type=float, default=0.25,
                        help="Seconds of audio to prepend to each segment from just before speech was detected. Prevents the beginning of transmissions from being cut off slightly (common with energy VAD on signals that ramp up).")
    parser.add_argument("--min-speech-sec", type=float, default=0.3,
                        help="Ignore segments shorter than this (noise)")
    parser.add_argument("--max-segment-sec", type=float, default=30.0,
                        help="Force end of segment after this many seconds")
    parser.add_argument("--model", default="tiny",
                        help="Whisper model for *real-time* (tiny recommended for all-day; use test/test_whisper.py later for medium/large on the saved files)")
    parser.add_argument("--language", default=None)
    parser.add_argument("--max-duration", type=float, default=None,
                        help="Stop after N seconds (useful for testing the tool)")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--initial-prompt", default=None,
                        help="Base domain prompt for Whisper. If --known-staff or --common-words(-file) are provided, they are automatically merged in to build a strong 'audio fingerprint' prompt for better recognition of staff names and radio jargon.")
    parser.add_argument("--no-transcribe", dest="transcribe", action="store_false",
                        help="Capture per-transmission .wav + basic meta only (no Whisper cost)")
    parser.add_argument("--list-categories", action="store_true",
                        help="List the current categories and exit")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--skip-calibration", "--no-calibration", dest="skip_calibration", action="store_true",
                        help="Skip the initial 1.5s background measurement (use for cold starts with no pre-flight access to radio). "
                             "The system will seed a conservative quiet floor and learn aggressively from the first real quiet gaps. "
                             "Strong warnings will be printed if the learned q~ stays high.")
    parser.add_argument("--known-staff", help="Comma-separated list of full teaching staff names for the audio fingerprint (e.g. 'Ms. Chandler,Mr. Moore,Dr. Strickland'). Improves name extraction and Whisper prompt.")
    parser.add_argument("--known-staff-file", type=Path, help="Text file with one full staff name per line. Used to build the audio fingerprint for better role recognition and prompt biasing.")
    parser.add_argument("--common-words", help="Comma-separated list of common radio words/phrases for the fingerprint (e.g. 'chromebook,retake,500,monitoring'). Helps Whisper and categorization.")
    parser.add_argument("--common-words-file", type=Path, help="Text file with common broadcast words/phrases (one per line or space/comma separated). Builds the domain fingerprint for transcription.")

    args = parser.parse_args()

    if args.list_categories:
        list_categories()
        return

    if args.list_devices:
        try:
            from edupulse.platform_util import print_input_devices

            print_input_devices()
        except Exception as e:
            # Fallback if package path not set up yet
            try:
                import sounddevice as sd

                print(sd.query_devices())
            except Exception as e2:
                print(f"ERROR listing devices: {e} / {e2}")
        return

    # Parse fingerprint data (staff names + common words) for the audio "fingerprint"
    known_staff_names: list[str] = []
    if args.known_staff:
        known_staff_names.extend([x.strip() for x in args.known_staff.split(",") if x.strip()])
    if args.known_staff_file and args.known_staff_file.exists():
        for line in args.known_staff_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                known_staff_names.append(line)
    known_staff_names = sorted(set(known_staff_names))

    common_words: list[str] = []
    if args.common_words:
        common_words.extend([x.strip() for x in args.common_words.split(",") if x.strip()])
    if args.common_words_file and args.common_words_file.exists():
        for line in args.common_words_file.read_text().splitlines():
            for token in line.replace(",", " ").split():
                token = token.strip()
                if token and not token.startswith("#"):
                    common_words.append(token)
    common_words = sorted(set(common_words))

    run_capture(
        data_dir=args.data_dir,
        session_label=args.session_label,
        device=args.device,
        speech_threshold_db=args.speech_threshold,
        silence_timeout=args.silence_timeout,
        min_speech_sec=args.min_speech_sec,
        max_segment_sec=args.max_segment_sec,
        tail_padding_sec=args.tail_padding_sec,
        pre_roll_sec=args.pre_roll_sec,
        model_name=args.model,
        language=args.language,
        max_duration=args.max_duration,
        beam_size=args.beam_size,
        temperature=args.temperature,
        initial_prompt=args.initial_prompt,
        transcribe=args.transcribe,
        skip_calibration=args.skip_calibration,
        known_staff_names=known_staff_names,
        common_words=common_words,
    )


if __name__ == "__main__":
    main()
