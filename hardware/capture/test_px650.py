#!/usr/bin/env python3
"""
EduPulse - First Audio Test for Cobra PX650 + Behringer UCA222

Minimal Option A approach:
- Control levels primarily with the radio's physical volume knob
- Secondary control via UCA222 hardware gain knobs
- This script is for initial bring-up and clipping tests only.

Run this on the Raspberry Pi after connecting the hardware.

Usage examples:
    python test_px650.py
    python test_px650.py --data-dir /data/edupulse/raw --duration 60
"""

import argparse
import sounddevice as sd
import soundfile as sf
import time
from datetime import datetime
from pathlib import Path

# ====================== DEFAULTS ======================
SAMPLE_RATE = 16000
CHANNELS = 2
DEFAULT_DURATION = 30
DEVICE = None  # Will try to auto-detect UCA222
# ===========================================================

def find_uca222_device():
    """Try to find the UCA222 (or compatible USB audio codec) in the list of devices."""
    devices = sd.query_devices()
    candidates = []
    for i, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) < 1:
            continue
        name = dev["name"].lower()
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
            candidates.append((score, i, dev["name"]))
    if candidates:
        candidates.sort(reverse=True)
        best_score, best_idx, best_name = candidates[0]
        print(f"Found likely radio input: [{best_idx}] {best_name}")
        return best_idx
    print("Could not auto-detect radio input device. Using default input device.")
    return None


def parse_args():
    parser = argparse.ArgumentParser(description="EduPulse PX650 first audio test recording")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / "edupulse" / "test_recordings",
        help="Directory to write recordings to. Currently defaulting to SD card path because SSDs are not mounted yet."
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION,
        help="Recording duration in seconds"
    )
    parser.add_argument(
        "--device",
        type=int,
        default=None,
        help="ALSA device index (run 'arecord -l' to list)"
    )
    return parser.parse_args()


def record_test(data_dir: Path, duration: int, device: int | None = None):
    data_dir = data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    dev = device or find_uca222_device() or DEVICE

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = data_dir / f"px650_test_{timestamp}.wav"

    print("\n" + "=" * 60)
    print("EDUPULSE - PX650 + UCA222 FIRST TEST RECORDING (Option A)")
    print("=" * 60)
    print(f"Sample rate : {SAMPLE_RATE} Hz")
    print(f"Channels    : {CHANNELS} (stereo)")
    print(f"Duration    : {duration} seconds")
    print(f"Output dir  : {data_dir}")
    print(f"Output file : {filename}")
    print("\n⚠️  TEMPORARY MODE: Writing to SD card (SSDs not mounted yet).")
    print("   Keep recordings short and delete old files regularly.\n")
    print("INSTRUCTIONS (Option A - Minimal):")
    print("  1. Set PX650 physical volume knob to ~25-35%")
    print("  2. Set both UCA222 input gain knobs to ~50%")
    print("  3. Have someone transmit on the radio")
    print("  4. Watch console for clipping warnings")
    print("=" * 60)
    print("\nRecording starts in 3 seconds...\n")
    time.sleep(3)

    print("Recording...")

    try:
        audio = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype='float32',
            device=dev
        )
        sd.wait()

        # Basic clipping check
        clipped_samples = (audio > 0.98).sum() + (audio < -0.98).sum()
        if clipped_samples > 0:
            print(f"\n⚠️  WARNING: Possible clipping detected ({clipped_samples} samples near ±1.0)")
            print("   → Turn the PX650 volume knob DOWN and try again.")
        else:
            print("\n✅ No obvious clipping detected in this take.")

        sf.write(str(filename), audio, SAMPLE_RATE)
        print(f"\nSaved: {filename}")
        print("\nNext steps:")
        print("  - Listen to the file")
        print("  - Note which stereo channel has the radio audio")
        print("  - Adjust radio volume knob + UCA222 gains as needed")

    except Exception as e:
        print(f"\nERROR during recording: {e}")
        print("Common fixes:")
        print("  - Run on the Pi:  arecord -l")
        print("  - Pass --device <index> or edit the script")


def main():
    args = parse_args()
    record_test(
        data_dir=args.data_dir,
        duration=args.duration,
        device=args.device
    )


if __name__ == "__main__":
    main()
