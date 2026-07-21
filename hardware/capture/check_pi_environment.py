#!/usr/bin/env python3
"""
EduPulse Pi Environment Checker

Run this on the target Raspberry Pi (or a development laptop) to get a quick report of:
- Audio devices (especially whether UCA222/Behringer is visible) -- Pi-focused
- Python audio packages (sounddevice, soundfile, numpy, scipy)
- Storage / SSD mounts (Pi-focused)
- Basic system info

This script is primarily written for the Raspberry Pi 4 target but degrades gracefully
on other Linux machines (laptop dev) for the Python package checks and basic info.

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


def has_cmd(name: str) -> bool:
    return shutil.which(name) is not None


def is_raspberry_pi() -> bool:
    try:
        with open("/sys/firmware/devicetree/base/model") as f:
            model = f.read().strip()
            if "raspberry pi" in model.lower():
                return True, model
    except Exception:
        pass
    # Fallback uname check
    ua = run(["uname", "-a"]).lower()
    if "raspberrypi" in ua or "rpi" in ua:
        return True, "detected via uname"
    return False, None

def check_audio():
    print("\n=== Audio Devices (arecord -l) ===")
    if has_cmd("arecord"):
        out = run(["arecord", "-l"])
        print(out or "arecord found but no devices listed")
    else:
        print("arecord not found (normal on non-Pi dev machines)")

    print("\n=== Audio Devices (aplay -l) ===")
    if has_cmd("aplay"):
        out = run(["aplay", "-l"])
        print(out or "aplay found but no devices listed")
    else:
        print("aplay not found (normal on non-Pi dev machines)")

    print("\n=== USB Audio Devices ===")
    if has_cmd("lsusb"):
        print(run(["lsusb"]) or "lsusb found but no output")
    else:
        print("lsusb not available (common on minimal containers or some Linux setups)")

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
    if has_cmd("df"):
        print(run(["df", "-h"]))
    else:
        print("df not available")

    print("\n=== Block Devices ===")
    if has_cmd("lsblk"):
        print(run(["lsblk", "-f"]))
    else:
        print("lsblk not available (storage checks are Pi/SSD focused)")

def check_system():
    print("\n=== System Info ===")
    print(f"Python version: {sys.version.splitlines()[0]}")
    print(f"Platform: {sys.platform}")
    on_pi, model = is_raspberry_pi()
    if on_pi:
        print(f"Raspberry Pi detected: {model}")
    else:
        print("Raspberry Pi: NOT DETECTED (running on laptop/dev machine is fine for code work)")
    ua = run(["uname", "-a"])
    print(f"uname: {ua}")
    host = run(["hostname"])
    print(f"Hostname: {host}")

def main():
    print("=" * 60)
    print("EDUPULSE PI ENVIRONMENT CHECK")
    print("=" * 60)
    check_system()
    check_storage()
    check_audio()
    check_python_audio()
    print("\n" + "=" * 60)
    print("Pi-specific audio/storage checks are best effort and will degrade on laptops.")
    print("Run this again AFTER plugging in the UCA222 (on the real Pi).")
    print("=" * 60)

if __name__ == "__main__":
    main()
