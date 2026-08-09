"""Cross-platform helpers for EduPulse (Windows primary live host + Linux).

Keep this small. Prefer pathlib + sounddevice; avoid OS-specific sprawl
in capture scripts. Raspberry Pi is optional/historical only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def default_captures_dir() -> Path:
    """Live capture root: ~/edupulse/captures on all platforms."""
    return (Path.home() / "edupulse" / "captures").expanduser()


def default_test_recordings_dir() -> Path:
    return (Path.home() / "edupulse" / "test_recordings").expanduser()


def default_raw_dir() -> Path:
    return (Path.home() / "edupulse" / "raw").expanduser()


def expand_path(p: str | Path) -> Path:
    """Expand ~ and env vars; resolve for stable paths (safe with spaces)."""
    path = Path(os.path.expandvars(str(p))).expanduser()
    try:
        return path.resolve()
    except OSError:
        return path


# Session folder names used as the "complete" clean reference set (when present).
DEFAULT_REFERENCE_SESSION_NAMES: tuple[str, ...] = (
    "2026-06-05_last-day-2",
    "2026-06-09_2026-06-08_graduation",
)


def default_reference_capture_dirs() -> list[str]:
    """Dirs used as 'complete' clean references for batch info-scores / corpus.

    Uses ~/edupulse/captures/<session> when those folders exist.
    Override with env EDUPULSE_REFERENCE_DIRS (os.pathsep-separated).
    """
    env = os.environ.get("EDUPULSE_REFERENCE_DIRS", "").strip()
    if env:
        return [str(expand_path(p)) for p in env.split(os.pathsep) if p.strip()]

    home_cap = default_captures_dir()
    existing = [
        str((home_cap / name).resolve())
        for name in DEFAULT_REFERENCE_SESSION_NAMES
        if (home_cap / name).is_dir()
    ]
    if existing:
        return existing
    # Placeholders for docs/callers that only need stable path strings
    return [str(home_cap / name) for name in DEFAULT_REFERENCE_SESSION_NAMES]


def list_input_devices() -> list[dict[str, Any]]:
    """Return sounddevice input devices with indices (WASAPI on Windows, ALSA/etc on Linux)."""
    try:
        import sounddevice as sd
    except ImportError as e:
        raise RuntimeError(
            "sounddevice is not installed. pip install sounddevice"
        ) from e

    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    rows: list[dict[str, Any]] = []
    for i, d in enumerate(devices):
        max_in = int(d.get("max_input_channels") or 0)
        if max_in <= 0:
            continue
        api_idx = int(d.get("hostapi", 0))
        api_name = ""
        try:
            api_name = str(hostapis[api_idx].get("name", ""))
        except Exception:
            pass
        rows.append(
            {
                "index": i,
                "name": str(d.get("name", "")),
                "max_input_channels": max_in,
                "default_samplerate": d.get("default_samplerate"),
                "hostapi": api_name,
            }
        )
    return rows


_DEFAULT_INPUT_PREFER = (
    "uca222",
    "behringer",
    "pcm2902",
    "usb audio codec",
    "usb audio",
)


def find_preferred_input(
    prefer: tuple[str, ...] = _DEFAULT_INPUT_PREFER,
    *,
    verbose: bool = False,
) -> int | None:
    """Pick best matching input device index (radio USB first)."""
    rows = list_input_devices()
    scored: list[tuple[int, int, str]] = []
    for r in rows:
        name = r["name"].lower()
        score = 0
        for rank, needle in enumerate(prefer):
            if needle in name:
                # earlier prefer entries score higher
                score = 100 - rank * 10
                break
        if score > 0:
            scored.append((score, int(r["index"]), r["name"]))
    if not scored:
        return None
    scored.sort(reverse=True)
    best_score, best_idx, best_name = scored[0]
    if verbose:
        print(f"Found likely radio input: [{best_idx}] {best_name}")
    return best_idx


def print_input_devices(file=None) -> None:
    """Human-readable device table for CLIs."""
    out = file or sys.stdout
    try:
        rows = list_input_devices()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=out)
        return

    if not rows:
        print("No input devices found.", file=out)
        return

    print(f"{'idx':>4}  {'in':>3}  {'rate':>8}  hostapi / name", file=out)
    print("-" * 72, file=out)
    for r in rows:
        rate = r.get("default_samplerate") or "?"
        print(
            f"{r['index']:4d}  {r['max_input_channels']:3d}  {str(rate):>8}  "
            f"{r.get('hostapi', '')} | {r['name']}",
            file=out,
        )
    print(file=out)
    print("Pass the index as --device N to capture scripts.", file=out)
    if is_windows():
        print(
            "Windows tip: Sound Settings → Input, or disable exclusive mode "
            "if open() fails (device Properties → Advanced).",
            file=out,
        )


def huggingface_token_search_paths() -> list[Path]:
    """Candidate locations for HF token (first existing wins in caller)."""
    home = Path.home()
    return [
        home / "HuggingFaceToken.txt",
        home / ".cache" / "huggingface" / "token",
        Path.cwd() / "HuggingFaceToken.txt",
        # Repo-relative when running from clone
        Path(__file__).resolve().parents[1] / "HuggingFaceToken.txt",
    ]
