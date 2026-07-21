#!/usr/bin/env python3
from __future__ import annotations

"""
EduPulse - Session Recorder for Cobra PX650 + Behringer UCA222

This is the main tool you will use for the first few days after the UCA222 arrives.

Features:
- Record for a set duration or until Ctrl+C
- --preview mode: live level metering without writing any files
- --label support: tag recordings (included in filename)
- Writes timestamped (and optionally labeled) files to a configurable directory
- dB-scale live metering with channel dominance indication
- Auto file rotation every ~60s (safety on SD card)
- Strong disk space protection and warnings
- Designed for Option A (radio volume knob + UCA222 gain control)

Usage examples:
    python record_session.py --duration 120
    python record_session.py --preview
    python record_session.py --label "class-change" --duration 300
    python record_session.py --data-dir ~/edupulse/test_recordings
    python record_session.py --data-dir ~/edupulse/raw --duration 300
"""

import argparse
import shutil
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# ====================== CONFIG ======================
SAMPLE_RATE = 16000
CHANNELS = 2
DEFAULT_DURATION = None   # None = run until Ctrl+C
DEFAULT_DATA_DIR = Path.home() / "edupulse" / "test_recordings"
# ===================================================


stop_recording = False


def signal_handler(sig, frame):
    global stop_recording
    print("\n\nStopping recording (Ctrl+C received)...")
    stop_recording = True


def find_uca222():
    """Find a likely radio input device (UCA222 or compatible USB audio codec).

    Enhanced to also match generic PCM2902 / USB Audio CODEC devices that
    the user may be using on laptop for testing (same chipset as UCA222).
    """
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
    """Convert linear amplitude to dBFS (clipped at -80 dB)."""
    import numpy as np
    if x <= 1e-8:
        return -80.0
    return 20 * np.log10(x)

def get_levels(audio: "np.ndarray") -> dict:
    """Return useful level metrics for a block of audio."""
    import numpy as np
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


def record_session(data_dir: Path, duration: int | None, device: int | None, label: str | None = None, preview: bool = False):
    """Record (or preview) audio from the radio.

    Args:
        data_dir: Where to write recordings (ignored in preview mode)
        duration: Seconds to record, or None for manual stop (Ctrl+C)
        device: Specific sounddevice index, or None to auto-detect UCA222
        label: Optional tag to include in the WAV filename(s)
        preview: If True, show live levels only; do not create or write any files
    """
    global stop_recording

    # Lazy imports so that --help / CLI inspection works without audio packages installed
    # (important for laptop development before running `pip install -r requirements.txt`)
    import sounddevice as sd
    import soundfile as sf

    data_dir = data_dir.expanduser().resolve()
    if not preview:
        data_dir.mkdir(parents=True, exist_ok=True)

    dev = device or find_uca222()
    if dev is None:
        print("Warning: Could not auto-detect UCA222. Using default input device.")

    signal.signal(signal.SIGINT, signal_handler)

    print("=" * 65)
    print("EDUPULSE - SESSION RECORDER (Option A)")
    print("=" * 65)
    print(f"Sample rate : {SAMPLE_RATE} Hz")
    print(f"Channels    : {CHANNELS}")
    print(f"Data dir    : {data_dir}")
    if duration:
        print(f"Duration    : {duration} seconds")
    else:
        print("Duration    : Until Ctrl+C")
    print(f"Device      : {dev if dev is not None else 'default'}")
    if label:
        print(f"Label       : {label}")
    if preview:
        print("Mode        : PREVIEW (no files will be written)")
    print()
    print("CONTROLS:")
    print("  - Adjust radio volume knob for coarse level")
    print("  - Adjust UCA222 gain knobs for fine level")
    print("  - Press Ctrl+C to stop early")
    print("=" * 65)
    print("\nStarting in 3 seconds...\n")
    time.sleep(3)

    current_file = None
    writer = None
    file_start_time = None

    def new_file():
        nonlocal current_file, writer, file_start_time
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if label:
            safe = "".join(c for c in label if c.isalnum() or c in ("-", "_")).strip()[:32] or "session"
            fname = f"px650_{ts}_{safe}.wav"
        else:
            fname = f"px650_{ts}.wav"
        current_file = data_dir / fname
        writer = sf.SoundFile(current_file, mode='w', samplerate=SAMPLE_RATE, channels=CHANNELS)
        file_start_time = time.time()
        print(f"\n>>> New file: {current_file.name}")

    if not preview:
        new_file()
    else:
        print("\n>>> PREVIEW MODE - live metering only. No files created.\n")

    blocksize = 1024
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype='float32',
        device=dev,
        blocksize=blocksize
    )
    stream.start()

    start_time = time.time()
    total_frames = 0

    # Quick channel detection hint for PX650 users
    print("\nTip: With the 2.5mm cable on the PX650, usually only one channel will have strong audio.")
    print("     The louder channel is the one carrying the radio traffic.\n")

    try:
        last_level_print = 0.0
        while not stop_recording:
            if duration and (time.time() - start_time) >= duration:
                print("\nDuration reached.")
                break

            audio, _ = stream.read(blocksize)
            if not preview:
                writer.write(audio)
            total_frames += len(audio)

            now = time.time()

            # Print levels roughly twice per second
            if now - last_level_print > 0.5:
                levels = get_levels(audio)
                diff = abs(levels["db_rms_l"] - levels["db_rms_r"])

                # Highlight which channel is dominant
                if levels["db_rms_l"] > levels["db_rms_r"] + 6:
                    channel_note = "  [L active]"
                elif levels["db_rms_r"] > levels["db_rms_l"] + 6:
                    channel_note = "  [R active]"
                else:
                    channel_note = ""

                print(
                    f"[{int(now - start_time):4d}s] "
                    f"RMS L:{levels['db_rms_l']:5.1f} R:{levels['db_rms_r']:5.1f} dB  "
                    f"Peak L:{levels['db_peak_l']:5.1f} R:{levels['db_peak_r']:5.1f} dB{channel_note}",
                    end="\r"
                )
                last_level_print = now

            # Rotate file every ~60 seconds (safety while on SD card) -- only when recording
            if not preview and (now - file_start_time) > 60:
                writer.close()
                new_file()

            # Disk space warning (only relevant when actually writing)
            if not preview:
                try:
                    free_gb = shutil.disk_usage(str(data_dir)).free / (1024**3)
                    if free_gb < 1.5:
                        print(f"\n⚠️  LOW DISK SPACE: Only {free_gb:.1f} GB free!")
                except Exception:
                    pass

    except Exception as e:
        print(f"\nError during recording: {e}")
    finally:
        stream.stop()
        stream.close()
        if not preview and writer:
            writer.close()

        elapsed = time.time() - start_time
        print(f"\n\nSession finished.")
        print(f"Duration     : {elapsed:.1f} seconds")
        if preview:
            print("Mode         : PREVIEW (no files were written)")
        else:
            print(f"Files written to: {data_dir}")
            print("Clean up old test .wav files regularly while testing on SD card.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EduPulse PX650 Session Recorder")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help="Where to write recordings (use SSD path when available)")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
                        help="Recording duration in seconds (omit for manual stop with Ctrl+C)")
    parser.add_argument("--device", type=int, default=None,
                        help="Sound device index (see arecord -l)")
    parser.add_argument("--label", type=str, default=None,
                        help="Optional label/tag to include in recorded filenames")
    parser.add_argument("--preview", action="store_true",
                        help="Preview live audio levels only; do not write any files to disk")

    args = parser.parse_args()
    record_session(args.data_dir, args.duration, args.device, label=args.label, preview=args.preview)
