#!/usr/bin/env python3
"""
EduPulse - Lightweight Continuous Recorder (Skeleton)

This is an early skeleton for long-running capture.
It is intentionally simple and not yet optimized.

Current design goals:
- Rotate files by time (e.g. every 15 or 30 minutes)
- Strong disk space protection
- Same level monitoring style as the other tools
- Easy to extend later with VAD, metadata, etc.

This is **not** the primary tool yet. Use `record_session.py` for now.

Future improvements (when needed):
- Configurable rotation size/time
- Voice Activity Detection
- Automatic upload / processing hooks
- Proper session management

Usage (example):
    python record_continuous.py --data-dir ~/edupulse/raw --rotation-minutes 15
"""

import argparse
import shutil
import signal
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf


SAMPLE_RATE = 16000
CHANNELS = 2
stop_recording = False


def signal_handler(sig, frame):
    global stop_recording
    print("\n\nStopping continuous recorder (Ctrl+C)...")
    stop_recording = True


def db(x: float) -> float:
    if x <= 1e-8:
        return -80.0
    return 20 * np.log10(x)


def get_levels(audio: np.ndarray) -> dict:
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
    rms_l = float(np.sqrt(np.mean(audio[:, 0]**2)))
    rms_r = float(np.sqrt(np.mean(audio[:, 1]**2))) if audio.shape[1] > 1 else rms_l
    return {
        "db_rms_l": db(rms_l),
        "db_rms_r": db(rms_r),
    }


def find_uca222():
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if 'uca222' in d['name'].lower() or 'behringer' in d['name'].lower():
            return i
    return None


def record_continuous(data_dir: Path, rotation_minutes: int, device: int | None):
    global stop_recording

    data_dir = data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    dev = device or find_uca222()

    signal.signal(signal.SIGINT, signal_handler)

    print("=" * 65)
    print("EDUPULSE - CONTINUOUS RECORDER (SKELETON)")
    print("=" * 65)
    print(f"Data dir           : {data_dir}")
    print(f"Rotation every     : {rotation_minutes} minutes")
    print(f"Device             : {dev if dev is not None else 'default'}")
    print("WARNING: This is an early skeleton. Use with caution on SD card.")
    print("=" * 65)
    print("\nStarting in 3 seconds... (Ctrl+C to stop)\n")
    time.sleep(3)

    blocksize = 1024
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype='float32',
        device=dev,
        blocksize=blocksize
    )
    stream.start()

    writer = None
    current_file = None
    file_start_time = time.time()

    def new_file():
        nonlocal writer, current_file, file_start_time
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        current_file = data_dir / f"continuous_{ts}.wav"
        writer = sf.SoundFile(current_file, mode='w', samplerate=SAMPLE_RATE, channels=CHANNELS)
        file_start_time = time.time()
        print(f"\n>>> New continuous file: {current_file.name}")

    new_file()

    try:
        while not stop_recording:
            audio, _ = stream.read(blocksize)
            writer.write(audio)

            # Very light level print every ~2 seconds
            if int(time.time()) % 2 == 0:
                levels = get_levels(audio)
                print(f"[{int(time.time() - file_start_time):4d}s] "
                      f"RMS L:{levels['db_rms_l']:5.1f} R:{levels['db_rms_r']:5.1f} dB", end="\r")

            # Rotate file
            if (time.time() - file_start_time) > (rotation_minutes * 60):
                writer.close()
                new_file()

            # Disk protection
            try:
                free_gb = shutil.disk_usage(str(data_dir)).free / (1024**3)
                if free_gb < 1.0:
                    print(f"\n\n🚨 CRITICAL: Only {free_gb:.2f} GB free. Stopping continuous recording.")
                    stop_recording = True
            except Exception:
                pass

    except Exception as e:
        print(f"\nError: {e}")
    finally:
        stream.stop()
        stream.close()
        if writer:
            writer.close()
        print("\n\nContinuous recorder stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path,
                        default=Path.home() / "edupulse" / "raw",
                        help="Directory for continuous recordings")
    parser.add_argument("--rotation-minutes", type=int, default=15,
                        help="Rotate to a new file every N minutes")
    parser.add_argument("--device", type=int, default=None)

    args = parser.parse_args()
    record_continuous(args.data_dir, args.rotation_minutes, args.device)