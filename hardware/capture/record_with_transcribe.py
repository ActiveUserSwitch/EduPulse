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

import sys
from pathlib import Path
# Prefer: pip install -e .  — else add repo root for `import edupulse`
_repo = Path(__file__).resolve().parents[2]
if (_repo / "edupulse" / "__init__.py").is_file() and str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))



import argparse
import json
import math
import queue
import signal
import threading
import time
from datetime import datetime
from typing import Any

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
try:
    from edupulse.speaker import (
        default_speaker_db_path,
        get_persistent_speaker_database,
        process_transmission_speaker,
    )
except Exception:  # pragma: no cover
    default_speaker_db_path = None  # type: ignore
    get_persistent_speaker_database = None  # type: ignore
    process_transmission_speaker = None  # type: ignore

# =============================================================================
# Audio helpers (shared)
# =============================================================================
from edupulse.audio_io import db, downmix_to_mono, find_uca222, get_levels
from edupulse.day_context import ensure_day_context
from edupulse.sidecar import build_sidecar, process_transcript

SAMPLE_RATE = 16000
CHANNELS = 2


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
    pre_roll_sec: float = 1.25,  # seconds before energy threshold (was 0.25; +1s to catch soft radio onsets)
    enable_speaker_id: bool = True,  # pyannote voice ID after Whisper (does not alter audio; can be disabled)
    model_name: str = "tiny",
    language: str | None = None,
    max_duration: float | None = None,
    beam_size: int = 5,
    temperature: float = 0.0,
    initial_prompt: str | None = None,
    transcribe: bool = True,
    skip_calibration: bool = False,
    known_staff_names: list[str] | None = None,
    radio_staff_names: list[str] | None = None,
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

    # Whisper fingerprint: prefer radio-users list (small) over full staff roster.
    # Full known_staff_names still drives IncidentTracker + enrollment resolve.
    prompt_staff = radio_staff_names or known_staff_names
    initial_prompt = build_enhanced_initial_prompt(
        base=initial_prompt,
        known_staff=prompt_staff,
        common_words=common_words,
    )
    if radio_staff_names:
        print(
            f"Whisper fingerprint staff: {len(radio_staff_names)} radio users "
            f"(full staff list still {len(known_staff_names or [])} for resolve)"
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
    print("  - DAY_CONTEXT.md                   (your notes: fire drill, early release, …)")
    print("  - session_summary.json + info.json at end")
    print()
    print("CONTROLS / TIPS:")
    print("  - Adjust radio volume + UCA222 gains while watching live RMS/peak + q~ (quiet floor) + thr~ (current threshold).")
    print("  - The capture loop *never blocks* on Whisper. New tx are buffered while previous are transcribed.")
    print("  - Students (full First Last) are strong anchors for INC-xxx. Role calls (Mr./Coach/Nurse/...)")
    print("    usually start a fresh INC unless linked by a student mention.")
    print("  - Noise/static segments are auto-bucketed (Noise / Squelch / Hallucination) and do not create INCs.")
    print("  - Day events: edupulse note \"Fire drill ~09:15\"   (writes DAY_CONTEXT.md)")
    print("  - Press Ctrl+C for clean stop (flushes work, writes summary).")
    print("=" * 72)
    print("\nStarting in 3 seconds...\n")
    time.sleep(3)

    # Human day-context stub (fire drill, early release, etc.)
    day_ctx = ensure_day_context(session_dir, session_name=session_dir.name)
    print(f"Day context file: {day_ctx}")
    print("  Add notes anytime: edupulse note \"Fire drill mid-morning\"\n")

    # Write session info for reproducibility
    session_info = {
        "start_iso": datetime.now().isoformat(),
        "session_label": session_label,
        "data_dir": str(data_dir),
        "session_dir": str(session_dir),
        "day_context_md": str(day_ctx),
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
        print(f"Loading Whisper model '{model_name}' for live transcription (first load can take a while)...")
        print("  Note: WAVs are written as soon as each tx ends; on-screen text may lag behind the radio.")
        print("  Prints/manifest lines always emit in *receive* order (seq), even if work finishes unevenly.")
        whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
        print(f"Model ready: {model_name} (cpu/int8)\n")

    tracker = IncidentTracker(known_staff_names=known_staff_names)  # one tracker for the whole day/session

    # Continual voice ID — lazy-init AFTER Whisper so pyannote doesn't compete at load time.
    # Speaker ID never modifies the audio fed to Whisper; it only reads the saved WAV after.
    speaker_db = None
    speaker_db_path = None
    pending_callee: str | None = None  # next TX likely this person (just called)
    speaker_id_enabled = bool(enable_speaker_id and transcribe and process_transmission_speaker is not None)
    if speaker_id_enabled:
        speaker_db_path = default_speaker_db_path() if default_speaker_db_path else None
        print(f"Speaker voice ID: ON (lazy load) → {speaker_db_path}")
        print("  Enroll gold: 'Name1 to Name2' then 'Go for Name2' / 'This is Name2'.")
        print("  (Does NOT assume next voice is the callee — too often someone else keys up.)")
        print("  Disable with --no-speaker-id if you want to A/B test transcription quality.")
    else:
        print("Speaker voice ID: OFF")

    stop_event = threading.Event()
    # Deep queue so large-v3 lag does not drop tx while capture keeps saving WAVs
    _qsize = 200 if str(model_name).startswith("large") else 80
    segment_queue: queue.Queue = queue.Queue(maxsize=_qsize)
    # Receive-order emit: print + manifest only in seq order
    next_emit_seq = 1
    emit_buffer: dict[int, dict] = {}
    emit_lock = threading.Lock()

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
                        # Start buffer from the rolling pre-roll ONLY.
                        # `audio` was already appended to pre_buffer above this frame —
                        # concatenating it again duplicated ~64ms and sounded like a
                        # skip/jitter on the first syllable (confirmed on 2026-09-04
                        # Harris/Coach clips: exact duplicate block at ~1.15s).
                        audio_buffer = pre_buffer[:]
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
                        seq = tx_count  # receive order (1-based); preserved for print/manifest
                        total_speech_sec += duration

                        # Enqueue for worker (transcription + meta writing)
                        item = (
                            seq,
                            mono_audio,
                            wall_dt,
                            duration,
                            str(wav_path) if wav_path else None,
                            seg_levels,
                        )
                        try:
                            # Block briefly instead of dropping — order/completeness > latency
                            segment_queue.put(item, timeout=30.0)
                        except queue.Full:
                            print(
                                f"\nWarning: analysis queue full for 30s — "
                                f"still saving WAV seq={seq} {wav_name}; transcript may be delayed."
                            )
                            try:
                                segment_queue.put(item, timeout=120.0)
                            except queue.Full:
                                print(
                                    f"\nERROR: could not enqueue seq={seq}; WAV kept on disk for offline upgrade."
                                )

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

    def _flush_ordered_emits() -> None:
        """Print + append manifest strictly in receive (seq) order."""
        nonlocal next_emit_seq
        while next_emit_seq in emit_buffer:
            ev = emit_buffer.pop(next_emit_seq)
            for line in ev.get("print_lines") or []:
                print(line)
            ment = ev.get("manifest_entry")
            if ment is not None:
                try:
                    with open(manifest_path, "a") as mf:
                        mf.write(json.dumps(ment, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"Warning: failed to append to manifest: {e}")
            next_emit_seq += 1

    def analysis_worker():
        """Background worker: Whisper first, then optional speaker ID; emit in receive order."""
        nonlocal total_speech_sec, speaker_db, pending_callee
        while not stop_event.is_set() or not segment_queue.empty() or emit_buffer:
            try:
                seq, mono_audio, wall_dt, duration, wav_path_str, seg_levels = segment_queue.get(timeout=0.5)
                wall_ts = wall_dt.strftime("%H:%M:%S")
                # Do not print "Processing" immediately — that races ahead of earlier seq prints.
                # Status is included in the ordered emit block below.

                cat_result = {"category": "Other / Unclear", "confidence": 0.0, "matched_keywords": []}
                transcription = ""
                transcription_raw = ""
                conf = 0.0
                inc_id = "INC-000"
                students: list[str] = []
                roles: list[str] = []
                cat_str = "Other / Unclear"
                cat_conf = 0.0
                likely_speaker: str | None = None
                likely_speaker_conf: str = "none"
                primary_speaker: str | None = None
                speaker_conf_val: float | None = None
                speaker_source: str | None = None
                radio_caller: str | None = None
                radio_callee: str | None = None
                enrolled_names: list[str] = []
                speaker_tentative = False
                speaker_best: str | None = None
                speaker_best_score: float | None = None
                print_lines: list[str] = [
                    f"\n[{wall_ts}] >>> seq={seq} Processing {duration:.1f}s transmission..."
                ]

                if transcribe and whisper_model is not None:
                    try:
                        # --- Whisper ONLY on in-memory mono (never altered by pyannote) ---
                        segments, info = whisper_model.transcribe(
                            mono_audio,
                            beam_size=beam_size,
                            temperature=temperature,
                            initial_prompt=initial_prompt,
                            language=language or "en",
                            vad_filter=False,
                            condition_on_previous_text=False,
                        )
                        seg_list = list(segments)
                        if seg_list:
                            seg = seg_list[0]  # we already segmented
                            conf = math.exp(seg.avg_logprob)
                            transcription_raw = seg.text.strip()
                            # Codes are prompt-only; display/sidecar use canonical last names.
                            try:
                                from edupulse.name_codebook import expand_transcript_names

                                transcription, transcription_raw = expand_transcript_names(
                                    transcription_raw
                                )
                            except Exception:
                                transcription = transcription_raw

                            domain = process_transcript(
                                transcription,
                                duration_sec=duration,
                                whisper_conf=conf,
                                tracker=tracker,
                                timestamp=wall_dt,
                            )

                            # Speaker ID AFTER Whisper (optional). Lazy-load embedder once.
                            if (
                                speaker_id_enabled
                                and wav_path_str
                                and not domain.get("is_noise")
                            ):
                                try:
                                    if speaker_db is None and get_persistent_speaker_database is not None:
                                        speaker_db = get_persistent_speaker_database(path=speaker_db_path)
                                        if speaker_db is not None:
                                            print_lines.append(
                                                f"  (speaker DB ready: {len(speaker_db.known_speakers())} profiles)"
                                            )
                                    if speaker_db is not None and process_transmission_speaker is not None:
                                        spk = process_transmission_speaker(
                                            wav_path_str,
                                            transcription,
                                            known_staff_names or [],
                                            db=speaker_db,
                                            db_path=speaker_db_path,
                                            persist=True,
                                            pending_callee=pending_callee,
                                        )
                                        likely_speaker = spk.get("likely_speaker")
                                        likely_speaker_conf = spk.get("likely_speaker_conf") or "none"
                                        primary_speaker = spk.get("primary_speaker")
                                        speaker_conf_val = spk.get("speaker_conf")
                                        speaker_source = spk.get("speaker_source")
                                        radio_caller = spk.get("caller")
                                        radio_callee = spk.get("callee") or spk.get("addressed")
                                        enrolled_names = list(spk.get("enrolled") or [])
                                        pending_callee = spk.get("pending_callee_out")
                                        speaker_tentative = bool(spk.get("speaker_tentative"))
                                        speaker_best = spk.get("speaker_best")
                                        speaker_best_score = spk.get("speaker_best_score")
                                except Exception as e:
                                    print_lines.append(f"  (speaker ID warn: {e})")

                            # Prefer miss ("?") over a wrong confident name.
                            # Tentative guesses are clearly marked and not stored as hard primary.
                            if primary_speaker and not speaker_tentative:
                                speaker_label = primary_speaker
                            elif speaker_tentative and speaker_best:
                                sc = f"{speaker_best_score:.2f}" if speaker_best_score is not None else "?"
                                speaker_label = f"~{speaker_best}? ({sc})"
                            elif (
                                likely_speaker
                                and likely_speaker_conf in ("gold", "strong", "protocol")
                            ):
                                speaker_label = likely_speaker
                            else:
                                speaker_label = "?"

                            if domain["is_noise"]:
                                cat_str = "Noise / Squelch / Hallucination"
                                cat_conf = 0.95
                                cat_result = {"category": cat_str, "confidence": cat_conf, "matched_keywords": []}
                                inc_id = "NOISE"
                                students = []
                                roles = []
                                print_lines.append(
                                    f"[{wall_ts}] [seq={seq}] [NOISE] (conf {conf:.2f}) "
                                    f"duration {duration:.1f}s — likely static/hallucination"
                                )
                                print_lines.append(f"  >>> {speaker_label}: {transcription}")
                            else:
                                cat_str = domain["category"]
                                cat_conf = domain["cat_conf"]
                                cat_result = {
                                    "category": cat_str,
                                    "confidence": cat_conf,
                                    "matched_keywords": domain.get("matched_keywords") or [],
                                }
                                inc_id = domain["incident_id"]
                                students = domain.get("students") or []
                                roles = domain.get("roles") or []
                                src = speaker_source or likely_speaker_conf
                                print_lines.append(
                                    f"[{wall_ts}] [seq={seq}] [{inc_id}] "
                                    f"(conf {conf:.2f}) "
                                    f"[{cat_str} conf:{cat_conf:.2f}] "
                                    f"[spk:{src}"
                                    f"{f' {speaker_conf_val:.2f}' if speaker_conf_val else ''}]"
                                    + (f" enrolled={enrolled_names}" if enrolled_names else "")
                                )
                                print_lines.append(f"  >>> {speaker_label}: {transcription}")
                            category_counts[cat_str] = category_counts.get(cat_str, 0) + 1
                        else:
                            print_lines.append(f"[{wall_ts}] [seq={seq}] (no speech in model output)")
                    except Exception as e:
                        print_lines.append(f"Transcription/analysis error (seq={seq}): {e}")
                        transcription = ""
                else:
                    cat_result = {"category": "Other / Unclear", "confidence": 0.0, "matched_keywords": []}
                    cat_str = "Other / Unclear"
                    cat_conf = 0.0
                    inc_id = tracker.get_incident_id("", wall_dt, "Other / Unclear")
                    print_lines.append(
                        f"[{wall_ts}] [seq={seq}] [CAPTURED] {duration:.1f}s raw -> "
                        f"{Path(wav_path_str).name if wav_path_str else 'no file'}"
                    )

                manifest_entry = None
                # Write sidecar immediately (per-file; order irrelevant). Include seq.
                if wav_path_str:
                    meta = build_sidecar(
                        audio_file=Path(wav_path_str).name,
                        start_iso=wall_dt.isoformat(),
                        duration_sec=round(duration, 2),
                        transcription=transcription,
                        whisper_conf=round(conf, 4) if transcribe else None,
                        category=cat_result["category"],
                        cat_conf=cat_result["confidence"],
                        matched_keywords=cat_result.get("matched_keywords") or [],
                        incident_id=inc_id,
                        students=students,
                        roles=roles,
                        is_noise=(inc_id == "NOISE"),
                        model=model_name if transcribe else "",
                        sample_rate=SAMPLE_RATE,
                        channels=CHANNELS,
                        levels=seg_levels,
                        seq=seq,
                        likely_speaker=likely_speaker,
                        likely_speaker_conf=likely_speaker_conf,
                        primary_speaker=primary_speaker,
                        speaker_conf=speaker_conf_val,
                        speaker_source=speaker_source,
                        radio_caller=radio_caller,
                        radio_callee=radio_callee,
                        speaker_enrolled=enrolled_names or None,
                        speaker_tentative=speaker_tentative or None,
                        speaker_best=speaker_best,
                        speaker_best_score=speaker_best_score,
                        transcription_raw=transcription_raw or None,
                    )
                    try:
                        with open(Path(wav_path_str).with_suffix(".json"), "w") as jf:
                            json.dump(meta, jf, indent=2)
                    except Exception as e:
                        print_lines.append(f"Warning: failed to write sidecar json: {e}")

                    manifest_entry = {
                        "seq": seq,
                        "audio_file": meta["audio_file"],
                        "start_iso": meta["start_iso"],
                        "duration_sec": meta["duration_sec"],
                        "transcription": transcription,
                        "whisper_conf": meta.get("whisper_conf"),
                        "category": meta["category"],
                        "cat_conf": meta["cat_conf"],
                        "incident_id": inc_id,
                        "students": students,
                        "roles": roles,
                        "is_noise": meta.get("is_noise", False),
                        "likely_speaker": likely_speaker,
                        "likely_speaker_conf": likely_speaker_conf,
                        "primary_speaker": primary_speaker,
                        "speaker_conf": speaker_conf_val,
                        "speaker_source": speaker_source,
                        "speaker_tentative": speaker_tentative,
                        "speaker_best": speaker_best,
                        "speaker_best_score": speaker_best_score,
                    }

                with emit_lock:
                    emit_buffer[seq] = {
                        "print_lines": print_lines,
                        "manifest_entry": manifest_entry,
                    }
                    _flush_ordered_emits()

                segment_queue.task_done()
            except queue.Empty:
                # Still flush if anything pending (shouldn't, with single worker)
                with emit_lock:
                    _flush_ordered_emits()
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
    parser.add_argument("--pre-roll-sec", type=float, default=1.25,
                        help="Seconds of audio to prepend before speech threshold (default 1.25). "
                             "Longer preamble catches soft radio onsets.")
    parser.add_argument("--no-speaker-id", dest="enable_speaker_id", action="store_false",
                        help="Disable pyannote voice ID (Whisper-only). Use to A/B test transcription quality.")
    parser.set_defaults(enable_speaker_id=True)
    parser.add_argument("--min-speech-sec", type=float, default=0.3,
                        help="Ignore segments shorter than this (noise)")
    parser.add_argument("--max-segment-sec", type=float, default=30.0,
                        help="Force end of segment after this many seconds")
    parser.add_argument("--model", default="large-v3",
                        help="Whisper model for live transcription (default: large-v3). "
                             "Capture never blocks on Whisper; printout may lag. "
                             "Use --model small/base/tiny if the queue backs up on a weak CPU.")
    parser.add_argument("--language", default="en",
                        help="Force language for Whisper (default: en — avoids junk multilingual guesses)")
    parser.add_argument("--max-duration", type=float, default=None,
                        help="Stop after N seconds (useful for testing the tool)")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--initial-prompt", default=None,
                        help="Base domain prompt for Whisper. If --known-staff or --common-words(-file) are provided, they are automatically merged in to build a strong 'audio fingerprint' prompt for better recognition of staff names and radio jargon.")
    parser.set_defaults(transcribe=True)
    parser.add_argument("--no-transcribe", dest="transcribe", action="store_false",
                        help="Capture per-transmission .wav + basic meta only (no Whisper cost)")
    parser.add_argument("--transcribe", dest="transcribe", action="store_true",
                        help="Enable real-time Whisper (default unless --no-transcribe / edupulse launcher)")
    parser.add_argument("--list-categories", action="store_true",
                        help="List the current categories and exit")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--skip-calibration", "--no-calibration", dest="skip_calibration", action="store_true",
                        help="Skip the initial 1.5s background measurement (use for cold starts with no pre-flight access to radio). "
                             "The system will seed a conservative quiet floor and learn aggressively from the first real quiet gaps. "
                             "Strong warnings will be printed if the learned q~ stays high.")
    parser.add_argument("--known-staff", help="Comma-separated list of full teaching staff names for the audio fingerprint (e.g. 'Ms. Chandler,Mr. Moore,Dr. Strickland'). Improves name extraction and Whisper prompt.")
    parser.add_argument("--known-staff-file", type=Path, help="Text file with one full staff name per line. Used for IncidentTracker / resolve (full roster).")
    parser.add_argument(
        "--radio-staff-file",
        type=Path,
        help="Staff who USE the radio (subset). Whisper fingerprint prefers this when present; "
        "full --known-staff-file still used for resolve/enrollment.",
    )
    parser.add_argument("--common-words", help="Comma-separated list of common radio words/phrases for the fingerprint (e.g. 'chromebook,retake,500,monitoring'). Helps Whisper and categorization.")
    parser.add_argument("--common-words-file", type=Path, help="Text file with common broadcast words/phrases (one per line or space/comma separated). Builds the domain fingerprint for transcription.")

    args = parser.parse_args()

    if args.list_categories:
        list_categories()
        return

    if args.list_devices:
        from edupulse.platform_util import print_input_devices
        print_input_devices()
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

    radio_staff_names: list[str] = []
    radio_path = args.radio_staff_file
    if radio_path is None:
        # Default next to known-staff-file when present
        if args.known_staff_file:
            cand = args.known_staff_file.with_name("radio_staff.txt")
            if cand.exists():
                radio_path = cand
    if radio_path and radio_path.exists():
        for line in radio_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                radio_staff_names.append(line)
    radio_staff_names = sorted(set(radio_staff_names))

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
        radio_staff_names=radio_staff_names or None,
        common_words=common_words,
        enable_speaker_id=args.enable_speaker_id,
    )


if __name__ == "__main__":
    main()
