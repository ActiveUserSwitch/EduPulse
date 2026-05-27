#!/usr/bin/env python3
"""
EduPulse - Session Recorder for Cobra PX650 + Behringer UCA222

This is the main tool you will use for the first few days after the UCA222 arrives.

Features:
- Record for a set duration or until Ctrl+C
- Writes timestamped files to a configurable directory
- Shows basic level information (per channel)
- Warns about low disk space (important while on SD card)
- Designed for Option A (radio volume knob + UCA222 gain control)

Usage examples:
    python record_session.py --duration 120
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

import numpy as np
import sounddevice as sd
import soundfile as sf

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
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        name = d['name'].lower()
        if 'uca222' in name or 'behringer' in name:
            return i
    return None


def db(x: float) -> float:
    """Convert linear amplitude to dBFS (clipped at -80 dB)."""
    if x <= 1e-8:
        return -80.0
    return 20 * np.log10(x)

def get_levels(audio: np.ndarray) -> dict:
    """Return useful level metrics for a block of audio."""
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


def record_session(data_dir: Path, duration: int | None, device: int | None):
    global stop_recording

    data_dir = data_dir.expanduser().resolve()
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
        current_file = data_dir / f"px650_{ts}.wav"
        writer = sf.SoundFile(current_file, mode='w', samplerate=SAMPLE_RATE, channels=CHANNELS)
        file_start_time = time.time()
        print(f"\n>>> New file: {current_file.name}")

    new_file()

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

            # Rotate file every ~60 seconds (safety while on SD card)
            if (now - file_start_time) > 60:
                writer.close()
                new_file()

            # Disk space warning
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
        if writer:
            writer.close()

        elapsed = time.time() - start_time
        print(f"\n\nSession finished.")
        print(f"Duration     : {elapsed:.1f} seconds")
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

    args = parser.parse_args()
    record_session(args.data_dir, args.duration, args.device)
