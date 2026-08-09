#!/usr/bin/env python3
"""
EduPulse - Real-time Radio Monitor + Live Transcription Test Script

This is a development/test tool for live monitoring of the radio while
printing transcriptions in (near) real time.

It uses a simple energy-based VAD (voice activity detection) to detect when
someone is transmitting on the radio, buffers the audio for the utterance,
then runs faster-whisper (default: tiny + int8 + cpu for speed) and prints
the result with timestamps.

Why this exists:
- Quick iteration / testing of the capture + Whisper pipeline on a laptop
  or Windows work PC without filling the disk with long recordings.
- Validate that the radio + interface + levels are good before doing long
  sessions.
- Experiment with real-time transcription parameters (model size, prompts, temperature).
- Each printed line now includes a model confidence score (0.0–1.0) derived from avg_logprob.
- Transmissions are linked into INC-xxx conversation/incident IDs using the radio protocol you described (Caller calls name, Receiver acknowledges, message, clarification). This helps connect related short and long transmissions belonging to the same event.

Usage examples:
    # Basic live monitoring (auto-detects UCA222 / USB audio codec)
    python test/test_realtime_transcribe.py

    # With your test device and more sensitive detection
    python test/test_realtime_transcribe.py --speech-threshold -35 --silence-timeout 1.0

    # Force a specific device (see --list-devices)
    python test/test_realtime_transcribe.py --device 1

    # Use a better model for testing (slower, try on laptop)
    python test/test_realtime_transcribe.py --model base

    # With domain prompt for radio context (helps a lot with discrepancies)
    python test/test_realtime_transcribe.py --initial-prompt "School administrative radio traffic, clear spoken messages:"

    # Better accuracy settings for laptop testing
    python test/test_realtime_transcribe.py --model base --beam-size 5 --temperature 0.0

    # List available input devices
    python test/test_realtime_transcribe.py --list-devices

    # List the current categories used for rudimentary classification
    python test/test_realtime_transcribe.py --list-categories

    # Limit for a quick test run
    python test/test_realtime_transcribe.py --max-duration 120

    # With fingerprint for this specific radio environment (staff names + common words)
    # (the live monitor can benefit from a better prompt if you rebuild the model call)

Each printed transcription now includes the model's confidence (0.00–1.00), rudimentary category, and an incident ID:

    [12:34:56] (conf 0.87) [INC-003] [Discipline (Student Conflict, Defiance, etc.) conf:0.80] Two students fighting in the cafeteria.

    [19:23:46 +0.0s] (conf 0.38) [INC-004] [Early Dismissal conf:1.00] Ben for dismissal.

Notes:
- Transcription happens after each detected utterance (not word-by-word streaming).
- **Model choice is key for accuracy**:
  - "tiny" (default): fastest, acceptable for quick tests.
  - "base" or "small": significantly better on radio audio, still usable on laptop.
  - "medium" / "large-v3": best accuracy but slow (use for offline analysis on good hardware).
  On low-power hosts use tiny or base; on the Windows work PC try base+ if CPU allows.
- Use `--initial-prompt` with context like "School radio administrative messages:" — this reduces hallucinations and improves domain-specific terms.
- Set `--temperature 0.0` (default) for most deterministic results.
- We now select the louder audio channel (instead of averaging) which helps with the PX650 cable setup.
- Supports very short (~1s) and long (up to 30s) transmissions via tunable min-speech and max-segment.
- Transcription is now fully decoupled from capture: the audio + VAD loop runs in its own thread and keeps recording/buffering new transmissions (short or long) while previous segments are being transcribed in a background worker thread (via queue.Queue). This directly addresses the need to not miss transmissions during Whisper processing time.
- Live RMS metering is always printed so you can adjust radio volume / UCA222 gains in real time.
- Press Ctrl+C to stop cleanly.

This is intentionally a test/development script. For production recording use
the tools in hardware/capture/.
"""

import argparse
import math
import queue
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

_repo = Path(__file__).resolve().parents[1]
if (_repo / "edupulse" / "__init__.py").is_file() and str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

import numpy as np

# =============================================================================
# Shared categorization + incident linking (single source of truth)
# See edupulse/analysis.py for the implementation and detailed radio protocol rules.
# =============================================================================
from edupulse.audio_io import downmix_to_mono, find_uca222, get_levels, print_input_devices
from edupulse.analysis import (
    TRANSMISSION_CATEGORIES,
    build_enhanced_initial_prompt,
    categorize_transmission,
    IncidentTracker,
)


# The IncidentTracker implementation lives in edupulse/analysis.py (imported above).
# We still create the module-level tracker instance here for the live monitor.
incident_tracker = IncidentTracker()  # for full fingerprint support in live monitor, pass known_staff_names here or rebuild with build_enhanced... for its prompt


# =============================================================================
# Try to reuse helpers from the main capture code (they have lazy imports inside)
try:
    from hardware.capture.record_session import find_uca222, get_levels, db
except Exception:
    # Fallback local implementations (kept in sync with the main ones)
    def find_uca222():
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

    def get_levels(audio: np.ndarray) -> dict:
        if audio.ndim == 1:
            audio = audio.reshape(-1, 1)
        rms_l = float(np.sqrt(np.mean(audio[:, 0]**2)))
        rms_r = float(np.sqrt(np.mean(audio[:, 1]**2))) if audio.shape[1] > 1 else rms_l
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


stop_monitoring = False


def signal_handler(sig, frame):
    global stop_monitoring
    print("\n\nStopping real-time monitor (Ctrl+C received)...")
    stop_monitoring = True


def list_input_devices():
    import sounddevice as sd
    print("\nAvailable input devices (with input channels):")
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) > 0:
            print(f"  [{i}] {d['name']}  (in: {d['max_input_channels']}, hostapi: {d.get('hostapi', '?')})")
    print()


def downmix_to_mono(audio: np.ndarray) -> np.ndarray:
    """Convert stereo to mono by selecting the louder channel (energy-based).

    From testing, the PX650 + 2.5mm cable usually puts the radio audio primarily
    on one channel (often R). Selecting the dominant channel often gives cleaner
    input to Whisper than simple averaging, especially on noisy radio signals.
    """
    if audio.ndim == 1:
        return audio
    if audio.shape[1] == 1:
        return audio[:, 0]

    # Compute RMS per channel
    rms_l = np.sqrt(np.mean(audio[:, 0]**2))
    rms_r = np.sqrt(np.mean(audio[:, 1]**2))

    if rms_l > rms_r:
        mono = audio[:, 0]
    else:
        mono = audio[:, 1]

    # Simple peak normalization — helps Whisper on quiet or varying radio levels
    peak = np.max(np.abs(mono))
    if peak > 1e-6:
        mono = mono / peak
    return mono.astype(np.float32)


def realtime_monitor(
    device: int | None = None,
    sample_rate: int = 16000,
    channels: int = 2,
    blocksize: int = 1024,
    speech_threshold_db: float = -40.0,
    silence_timeout: float = 1.5,
    min_speech_sec: float = 0.3,
    max_segment_sec: float = 30.0,
    model_name: str = "tiny",
    language: str | None = None,
    max_duration: float | None = None,
    list_devices: bool = False,
    list_categories: bool = False,
    beam_size: int = 5,
    temperature: float = 0.0,
    initial_prompt: str | None = None,
):
    global stop_monitoring

    if list_devices:
        list_input_devices()
        return

    if list_categories:
        print("Current rudimentary transmission categories (keyword-based):")
        for cat, kws in TRANSMISSION_CATEGORIES.items():
            print(f"  - {cat}")
            print(f"      keywords: {', '.join(kws)}")
        return

    dev = device or find_uca222()
    if dev is None:
        print("Warning: Could not auto-detect radio input device. Using system default.")

    signal.signal(signal.SIGINT, signal_handler)

    print("=" * 70)
    print("EDUPULSE - REAL-TIME RADIO MONITOR + LIVE TRANSCRIPTION (TEST)")
    print("=" * 70)
    print(f"Sample rate       : {sample_rate} Hz")
    print(f"Channels          : {channels}")
    print(f"Device            : {dev if dev is not None else 'default'}")
    print(f"Speech threshold  : {speech_threshold_db:.1f} dB")
    print(f"Silence timeout   : {silence_timeout:.1f} s")
    print(f"Min speech        : {min_speech_sec:.1f} s (supports ~1s short transmissions)")
    print(f"Whisper model     : {model_name} (cpu, int8)")
    if language:
        print(f"Language          : {language}")
    if max_duration:
        print(f"Auto-stop after   : {max_duration:.1f} s")
    print()
    print("CONTROLS:")
    print("  - Adjust radio volume + UCA222 gains while watching live levels below.")
    print("  - Key the radio (PTT) to trigger a transcription segment.")
    print("  - The capture loop continues running: new transmissions (1s short or 30s long) are buffered")
    print("    even while a previous segment is being transcribed in the background worker.")
    print("  - Long silences between transmissions are handled (we use energy VAD).")
    print("  - INC-xxx IDs: Students are strong anchors for the *same* incident. Role calls (Nurse/Officer/etc.)")
    print("    usually start new incidents unless linked by a student or other clear factors.")
    print("  - Press Ctrl+C to stop.")
    print()
    print("RUDIMENTARY CATEGORIES (user-provided list, keyword-based):")
    for cat in TRANSMISSION_CATEGORIES:
        print(f"  - {cat}")
    print("=" * 70)
    print("\nListening... (live metering every ~0.3s)\n")

    # Load Whisper model once (can be slow the first time)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("ERROR: faster-whisper not installed.")
        print("pip install faster-whisper")
        sys.exit(1)

    print("Loading Whisper model...")
    whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
    print("Model ready. Start transmitting on the radio.\n")

    # Threaded architecture: audio/VAD runs continuously in one thread (so it can
    # keep recording new transmissions), while transcription happens in a background
    # worker thread using a queue. This allows capturing short (1s) or long (30s)
    # transmissions even while a previous one is being transcribed by Whisper.
    stop_event = threading.Event()
    segment_queue = queue.Queue(maxsize=20)  # allow buffering a few segments

    total_start = time.time()
    last_level_print = 0.0

    def audio_capture_loop():
        """Dedicated thread: keeps the sounddevice stream alive, does VAD, enqueues completed segments."""
        import sounddevice as sd
        nonlocal last_level_print
        stream = None
        audio_buffer = []
        is_speaking = False
        silence_start = None
        segment_start_time = None
        try:
            stream = sd.InputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="float32",
                device=dev,
                blocksize=blocksize,
            )
            stream.start()

            while not stop_event.is_set():
                if max_duration and (time.time() - total_start) >= max_duration:
                    print("\nMax duration reached.")
                    stop_event.set()

                audio, _ = stream.read(blocksize)
                now = time.time()

                # Live metering (always, for tuning) -- runs in audio thread
                if now - last_level_print > 0.3:
                    levels = get_levels(audio)
                    # Show the dominant channel (useful for the 2.5mm cable)
                    if levels["db_rms_l"] > levels["db_rms_r"] + 6:
                        ch_note = " [L]"
                    elif levels["db_rms_r"] > levels["db_rms_l"] + 6:
                        ch_note = " [R]"
                    else:
                        ch_note = ""
                    print(
                        f"[{int(now - total_start):4d}s] "
                        f"RMS L:{levels['db_rms_l']:5.1f} R:{levels['db_rms_r']:5.1f} dB  "
                        f"Peak L:{levels['db_peak_l']:5.1f} R:{levels['db_peak_r']:5.1f} dB{ch_note}",
                        end="\r",
                    )
                    last_level_print = now

                # Simple energy VAD on the louder channel
                levels = get_levels(audio)
                dominant_rms = max(levels["rms_l"], levels["rms_r"])
                dominant_db = 20 * np.log10(dominant_rms + 1e-8)
                is_speech = dominant_db > speech_threshold_db

                if is_speech:
                    if not is_speaking:
                        is_speaking = True
                        audio_buffer = [audio.copy()]
                        segment_start_time = now
                        silence_start = None
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> Speech detected (starting buffer)")
                    else:
                        audio_buffer.append(audio.copy())
                        silence_start = None

                    # Safety: force end of segment if it gets too long
                    if segment_start_time and (now - segment_start_time) > max_segment_sec:
                        print("\n>>> Max segment length reached, queuing for transcription...")
                        is_speaking = False
                else:
                    if is_speaking:
                        if silence_start is None:
                            silence_start = now
                        if (now - silence_start) >= silence_timeout:
                            is_speaking = False

                # If we just ended a speech segment, *queue* it (do not transcribe here!)
                # This is the key change: audio loop continues immediately and can
                # start buffering the *next* transmission (short or long) while the
                # previous one is transcribed in the worker thread.
                if (not is_speaking) and audio_buffer and segment_start_time:
                    full_audio = np.concatenate(audio_buffer, axis=0)
                    duration = len(full_audio) / sample_rate

                    if duration >= min_speech_sec:
                        mono_audio = downmix_to_mono(full_audio)
                        try:
                            segment_queue.put_nowait((mono_audio, datetime.now(), duration))
                        except queue.Full:
                            print("\nWarning: transcription queue full, dropping a segment.")

                    # reset for next utterance immediately
                    audio_buffer = []
                    segment_start_time = None
                    silence_start = None

                # Prevent unbounded growth if something goes wrong
                if len(audio_buffer) > int((max_segment_sec + 2) * sample_rate / blocksize):
                    audio_buffer = audio_buffer[-int(10 * sample_rate / blocksize):]

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

    def transcription_worker():
        """Background worker: pulls queued segments and runs (potentially slow) Whisper."""
        while not stop_event.is_set() or not segment_queue.empty():
            try:
                mono_audio, wall_dt, duration = segment_queue.get(timeout=0.5)
                print(f"\n[{wall_dt.strftime('%H:%M:%S')}] >>> Transcribing {duration:.1f}s segment...")

                try:
                    segments, info = whisper_model.transcribe(
                        mono_audio,
                        beam_size=beam_size,
                        temperature=temperature,
                        initial_prompt=initial_prompt,
                        language=language,
                        vad_filter=False,  # we did our own segmentation
                        condition_on_previous_text=False,
                    )
                    seg_list = list(segments)
                    if seg_list:
                        wall_ts = wall_dt.strftime("%H:%M:%S")
                        for seg in seg_list:
                            conf = math.exp(seg.avg_logprob)
                            cat_result = categorize_transmission(seg.text)
                            cat_str = cat_result["category"]
                            cat_conf = cat_result["confidence"]

                            # Link this transmission to an incident/conversation using radio protocol + context.
                            # Pass confs so low-quality "Other" segments don't pollute student name anchors.
                            inc_id = incident_tracker.get_incident_id(seg.text, wall_dt, cat_str,
                                                                      whisper_conf=conf, cat_conf=cat_conf)

                            print(
                                f"[{wall_ts} +{seg.start:5.1f}s] "
                                f"[{inc_id}] "
                                f"(conf {conf:.2f}) "
                                f"[{cat_str} conf:{cat_conf:.2f}] "
                                f"{seg.text.strip()}"
                            )
                    else:
                        print(f"[{wall_dt.strftime('%H:%M:%S')}] (no speech detected by model)")
                except Exception as e:
                    print(f"Transcription error: {e}")
                segment_queue.task_done()
            except queue.Empty:
                continue

    # Start decoupled threads
    audio_thread = threading.Thread(target=audio_capture_loop, daemon=True)
    trans_thread = threading.Thread(target=transcription_worker, daemon=True)
    audio_thread.start()
    trans_thread.start()

    # Main thread just waits / handles shutdown
    try:
        while not stop_monitoring and not stop_event.is_set():
            if max_duration and (time.time() - total_start) >= max_duration:
                print("\nMax duration reached.")
                stop_event.set()
            time.sleep(0.1)
    except Exception as e:
        print(f"\nError during monitoring: {e}")
        stop_event.set()
    finally:
        stop_event.set()
        # Wait for any queued work to finish (important for long transcriptions)
        try:
            segment_queue.join()
        except Exception:
            pass
        audio_thread.join(timeout=2.0)
        trans_thread.join(timeout=15.0)  # give Whisper time to finish current work
        print("\n\nReal-time monitor stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Real-time radio monitor with live Whisper transcription (for testing)"
    )
    parser.add_argument("--device", type=int, default=None,
                        help="Sound device index (use --list-devices to see options)")
    parser.add_argument("--list-devices", action="store_true",
                        help="List available input devices and exit")
    parser.add_argument("--list-categories", action="store_true",
                        help="List the current rudimentary transmission categories and exit")
    parser.add_argument("--speech-threshold", type=float, default=-40.0,
                        help="RMS dB threshold to consider audio as speech (e.g. -45 to -30)")
    parser.add_argument("--silence-timeout", type=float, default=1.2,
                        help="Seconds of silence before ending a speech segment")
    parser.add_argument("--min-speech-sec", type=float, default=0.3,
                        help="Ignore very short segments (noise). Set low (e.g. 0.3) to catch 1-second transmissions.")
    parser.add_argument("--max-segment-sec", type=float, default=30.0,
                        help="Force transcription after this many seconds of continuous speech")
    parser.add_argument("--model", default="tiny",
                        help="Whisper model size (tiny is fastest for real-time testing; try 'base' or 'small' for better accuracy on laptop)")
    parser.add_argument("--language", default=None,
                        help="Force language code (e.g. 'en'). Default: auto-detect")
    parser.add_argument("--max-duration", type=float, default=None,
                        help="Automatically stop after N seconds (useful for scripted tests)")
    parser.add_argument("--beam-size", type=int, default=5,
                        help="Beam search size (higher can improve accuracy, slower)")
    parser.add_argument("--temperature", type=float, default=0.0,
                        help="Sampling temperature (0.0 = deterministic/greedy, good for accuracy)")
    parser.add_argument("--initial-prompt", default=None,
                        help="Text prompt to guide the model (e.g. 'School administrative radio traffic:')")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--channels", type=int, default=2)

    args = parser.parse_args()

    realtime_monitor(
        device=args.device,
        sample_rate=args.sample_rate,
        channels=args.channels,
        speech_threshold_db=args.speech_threshold,
        silence_timeout=args.silence_timeout,
        min_speech_sec=args.min_speech_sec,
        max_segment_sec=args.max_segment_sec,
        model_name=args.model,
        language=args.language,
        max_duration=args.max_duration,
        list_devices=args.list_devices,
        list_categories=args.list_categories,
        beam_size=args.beam_size,
        temperature=args.temperature,
        initial_prompt=args.initial_prompt,
    )


if __name__ == "__main__":
    main()
