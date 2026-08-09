"""Shared audio level helpers and device preference (no capture loop)."""
from __future__ import annotations

from typing import Any

import numpy as np

from .platform_util import find_preferred_input, list_input_devices, print_input_devices

__all__ = [
    "db",
    "downmix_to_mono",
    "find_preferred_input",
    "find_uca222",
    "get_levels",
    "list_input_devices",
    "print_input_devices",
]


def db(x: float) -> float:
    if x <= 1e-8:
        return -80.0
    return float(20 * np.log10(x))


def get_levels(audio: np.ndarray) -> dict[str, float]:
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
    rms_l = float(np.sqrt(np.mean(audio[:, 0] ** 2)))
    rms_r = float(np.sqrt(np.mean(audio[:, 1] ** 2))) if audio.shape[1] > 1 else rms_l
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


def downmix_to_mono(audio: np.ndarray) -> np.ndarray:
    """Dominant channel + peak normalization for Whisper."""
    if audio.ndim == 1:
        return audio.astype(np.float32, copy=False)
    if audio.shape[1] == 1:
        return audio[:, 0].astype(np.float32, copy=False)

    rms_l = np.sqrt(np.mean(audio[:, 0] ** 2))
    rms_r = np.sqrt(np.mean(audio[:, 1] ** 2))
    mono = audio[:, 0] if rms_l > rms_r else audio[:, 1]
    peak = np.max(np.abs(mono))
    if peak > 1e-6:
        mono = mono / peak
    return mono.astype(np.float32)


def find_uca222() -> int | None:
    """Back-compat name: preferred radio USB input index."""
    return find_preferred_input(verbose=True)
