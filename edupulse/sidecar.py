"""Canonical sidecar / manifest field contracts (TypedDict).

Capture and offline tools should build these shapes instead of ad-hoc dicts.
"""
from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class CategoryResult(TypedDict):
    category: str
    confidence: float
    matched_keywords: list[str]


class TransmissionSidecar(TypedDict, total=False):
    """Fields commonly written next to tx_*.wav (JSON sidecar)."""

    transmission_id: str
    audio_file: str
    wav_path: str
    start_iso: str
    duration_sec: float
    sample_rate: int
    channels: int
    model: str
    transcription: str
    whisper_conf: float | None
    category: str
    cat_conf: float
    matched_keywords: list[str]
    incident_id: str
    students: list[str]
    roles: list[str]
    is_noise: bool
    # Optional acoustic / speaker enrichment
    acoustic_features: dict[str, Any]
    primary_speaker: str | None
    speaker_conf: float | None
    speaker_segments: list[dict[str, Any]]
    information_score: dict[str, Any]
    acoustic_zscores: dict[str, Any]
    lexical_surprisal: float
    tags: list[str]
    critical_baseline: bool
    notes: str


class ManifestEntry(TypedDict, total=False):
    """One line of session_manifest.jsonl."""

    transmission_id: str
    audio_file: str
    start_iso: str
    duration_sec: float
    transcription: str
    whisper_conf: float | None
    category: str
    cat_conf: float
    incident_id: str
    students: list[str]
    roles: list[str]
    is_noise: bool


def build_sidecar(
    *,
    audio_file: str,
    start_iso: str,
    duration_sec: float,
    transcription: str = "",
    whisper_conf: float | None = None,
    category: str = "Other / Unclear",
    cat_conf: float = 0.0,
    matched_keywords: list[str] | None = None,
    incident_id: str = "INC-000",
    students: list[str] | None = None,
    roles: list[str] | None = None,
    is_noise: bool = False,
    model: str = "",
    sample_rate: int = 16000,
    channels: int = 2,
    **extra: Any,
) -> TransmissionSidecar:
    """Assemble a sidecar dict with required core fields."""
    tx_id = audio_file.replace(".wav", "") if audio_file.endswith(".wav") else audio_file
    out: TransmissionSidecar = {
        "transmission_id": tx_id,
        "audio_file": audio_file,
        "start_iso": start_iso,
        "duration_sec": float(duration_sec),
        "sample_rate": sample_rate,
        "channels": channels,
        "model": model,
        "transcription": transcription or "",
        "whisper_conf": whisper_conf,
        "category": category,
        "cat_conf": float(cat_conf),
        "matched_keywords": list(matched_keywords or []),
        "incident_id": incident_id,
        "students": list(students or []),
        "roles": list(roles or []),
        "is_noise": bool(is_noise),
    }
    for k, v in extra.items():
        if v is not None:
            out[k] = v  # type: ignore[literal-required]
    return out


def process_transcript(
    text: str,
    *,
    duration_sec: float = 0.0,
    whisper_conf: float | None = None,
    tracker: Any | None = None,
    timestamp: float | Any = 0.0,
) -> dict[str, Any]:
    """Canonical post-transcript domain step: noise → category → optional INC.

    Capture/offline tools should call this instead of re-sequencing domain logic.
    """
    from .categories import categorize_transmission, is_likely_noise

    noise = is_likely_noise(text, duration_sec, whisper_conf)
    cat = categorize_transmission(text or "")
    result: dict[str, Any] = {
        "is_noise": noise,
        "category": cat["category"],
        "cat_conf": cat["confidence"],
        "matched_keywords": cat.get("matched_keywords") or [],
        "incident_id": "INC-000",
        "students": [],
        "roles": [],
    }
    if noise or tracker is None:
        return result
    inc_id = tracker.get_incident_id(
        text,
        timestamp,
        cat["category"],
        whisper_conf=whisper_conf,
        cat_conf=cat["confidence"],
    )
    result["incident_id"] = inc_id
    # Best-effort name sets from last open incident if present
    for inc in reversed(getattr(tracker, "incidents", []) or []):
        if inc.get("id") == inc_id:
            result["students"] = list(inc.get("students") or [])
            result["roles"] = list(inc.get("roles") or [])
            break
    return result
