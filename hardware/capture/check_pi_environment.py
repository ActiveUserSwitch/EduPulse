#!/usr/bin/env python3
"""
EduPulse Pi Environment Checker

Run this on the target Raspberry Pi to get a quick report of:
- Audio devices (especially whether UCA222 is visible)
- Python audio packages
- Storage / SSD mounts
- Basic system info

Usage:
    python check_pi_environment.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

def run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except Exception as e:
        return f"Error running {' '.join(cmd)}: {e}"

def check_audio():
    print("\n=== Audio Devices (arecord -l) ===")
    print(run(["arecord", "-l"]) or "arecord not found or no devices")

    print("\n=== Audio Devices (aplay -l) ===")
    print(run(["aplay", "-l"]) or "aplay not found")

    print("\n=== USB Audio Devices ===")
    print(run(["lsusb"]) or "lsusb not available")

def check_python_audio():
    print("\n=== Python Audio Packages ===")
    packages = ["sounddevice", "soundfile", "numpy", "scipy"]
    for pkg in packages:
        try:
            mod = __import__(pkg)
            version = getattr(mod, "__version__", "unknown")
            print(f"  {pkg}: {version}")
        except ImportError:
            print(f"  {pkg}: NOT INSTALLED")

def check_storage():
    print("\n=== Storage / Mounts ===")
    print(run(["df", "-h"]))
    print("\n=== Block Devices ===")
    print(run(["lsblk", "-f"]))

def check_system():
    print("\n=== System Info ===")
    print(f"Python version: {sys.version.splitlines()[0]}")
    print(run(["uname", "-a"]))
    print(f"Hostname: {run(['hostname'])}")

def main():
    print("=" * 60)
    print("EDUPULSE PI ENVIRONMENT CHECK")
    print("=" * 60)
    check_system()
    check_storage()
    check_audio()
    check_python_audio()
    print("\n" + "=" * 60)
    print("Run this again AFTER plugging in the UCA222.")
    print("=" * 60)

if __name__ == "__main__":
    main()
