#!/usr/bin/env python3
"""
EduPulse cross-platform environment checker (primary diagnostics tool).

**Preferred** over check_pi_environment.py for all current work.
Primary live capture host: Windows work PC (WASAPI).

Reports:
  - OS / Python
  - sounddevice input devices (WASAPI on Windows; ALSA/Pulse/etc on Linux)
  - Python audio packages
  - Default capture paths
  - Optional Linux extras: arecord/lsusb when present (skipped on Windows)

Usage:
    python hardware/capture/check_audio_environment.py
    python hardware/capture/check_audio_environment.py --list-devices
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Repo root on sys.path for `edupulse` package
_here = Path(__file__).resolve()
for parent in [_here.parent, *_here.parents]:
    if (parent / "edupulse" / "__init__.py").exists():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break

from edupulse.platform_util import (  # noqa: E402
    default_captures_dir,
    is_linux,
    is_windows,
    print_input_devices,
)


def run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return (result.stdout or "").strip() or (result.stderr or "").strip()
    except Exception as e:
        return f"Error: {e}"


def has_cmd(name: str) -> bool:
    return shutil.which(name) is not None


def check_system() -> None:
    print("\n=== System ===")
    print(f"Python : {sys.version.splitlines()[0]}")
    print(f"Platform: {sys.platform}")
    print(f"Windows: {is_windows()}  Linux: {is_linux()}")
    print(f"HOME/USERPROFILE equivalent: {Path.home()}")
    print(f"Default captures dir: {default_captures_dir()}")


def check_python_packages() -> None:
    print("\n=== Python packages ===")
    for pkg in ("sounddevice", "soundfile", "numpy", "scipy"):
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "unknown")
            print(f"  {pkg}: {ver}")
        except ImportError:
            print(f"  {pkg}: NOT INSTALLED  (pip install {pkg})")
    try:
        import faster_whisper  # noqa: F401

        print("  faster-whisper: installed")
    except ImportError:
        print("  faster-whisper: NOT INSTALLED  (optional for live/offline Whisper)")


def check_sounddevice_devices() -> None:
    print("\n=== Input devices (sounddevice) ===")
    print_input_devices()


def check_linux_extras() -> None:
    if not is_linux():
        return
    print("\n=== Linux extras (optional) ===")
    if has_cmd("arecord"):
        print("arecord -l:")
        print(run(["arecord", "-l"]) or "(none)")
    else:
        print("arecord: not found")
    if has_cmd("lsusb"):
        print("\nlsusb (USB audio):")
        print(run(["lsusb"]) or "(none)")


def check_windows_hints() -> None:
    if not is_windows():
        return
    print("\n=== Windows tips ===")
    print("  - Prefer: python hardware\\capture\\check_audio_environment.py --list-devices")
    print("  - Capture: python hardware\\capture\\record_with_transcribe.py --device N ...")
    print("  - Data root: %USERPROFILE%\\edupulse\\captures")
    print("  - If open() fails: device Properties → Advanced → uncheck exclusive mode")
    print("  - See hardware/capture/WINDOWS_QUICKSTART.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="EduPulse audio environment check (Windows + Linux)")
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Only print sounddevice input devices and exit",
    )
    args = parser.parse_args()

    if args.list_devices:
        print_input_devices()
        return

    print("=" * 60)
    print("EDUPULSE AUDIO ENVIRONMENT CHECK")
    print("=" * 60)
    check_system()
    check_python_packages()
    check_sounddevice_devices()
    check_linux_extras()
    check_windows_hints()
    print("\n" + "=" * 60)
    print("Next: pick a device index, plug in UCA222 if using radio, then capture.")
    print("=" * 60)


if __name__ == "__main__":
    main()
