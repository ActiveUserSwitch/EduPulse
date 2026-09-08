"""IRB research-export layer.

Builds a de-identified analysis table from live sidecars / manifests.
Does not change live capture. Does not copy WAVs. Does not use
name_codebook.py (that module expands aliases into real last names).

Live PII stays in ~/edupulse/captures and gitignored fingerprint files.
Export writes only to an output directory (default ~/edupulse/research_export).

By default the analysis file includes a redacted transcript: staff names
are replaced with role labels and student names with [STUDENT]. The raw
transcript stays in the local sidecar.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

STRIP_KEYS = {
    "transcription",
    "transcription_raw",
    "transcription_whisper",
    "transcription_repair",
    "students",
    "roles",
    "likely_speaker",
    "likely_speaker_conf",
    "radio_caller",
    "radio_callee",
    "speaker_source",
    "speaker_enrolled",
    "primary_speaker",
    "speaker_conf",
    "speaker_segments",
    "wav_path",
    "audio_file",
    "notes",
    "matched_keywords",
}

MEDICAL_CATEGORY = "Medical / Health Emergency"

_ROLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("nurse", ("nurse", "rn", "lpn")),
    ("sro", ("officer", "deputy", "sro", "sheriff")),
    ("jrotc", ("jrotc", "asi", "sasi", "cadet")),
    ("admin", ("principal", "assistant principal", "ap ", "admin")),
    ("facilities", ("custodian", "maintenance", "facilities", "janitor")),
    ("teacher", ("teacher", "coach", "ms.", "mr.", "mrs.", "mx.", "dr.")),
)

_TITLE = {"ms.", "mr.", "mrs.", "mx.", "dr.", "nurse", "coach", "officer", "principal"}
_NAME_TOKEN = re.compile(r"\b(?:Ms\.|Mr\.|Mrs\.|Mx\.|Dr\.)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")


def load_staff_names(path: Path | None) -> list[str]:
    if path is None or not path.is_file():
        return []
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


def role_bucket(label: str) -> str:
    low = (label or "").lower()
    for bucket, needles in _ROLE_RULES:
        if any(n in low for n in needles):
            return bucket
    return "other"


def _stable_code(kind: str, raw: str) -> str:
    digest = hashlib.blake2s(raw.strip().lower().encode("utf-8"), digest_size=4).hexdigest()
    return f"{kind}_{digest}"


def staff_role_code(name: str) -> str:
    return _stable_code(role_bucket(name), name)


def hash_incident_id(incident_id: str, salt: str) -> str | None:
    raw = (incident_id or "").strip()
    if not raw or raw.upper() in {"INC-000", "NONE", "NA"}:
        return None
    digest = hashlib.blake2s(f"{salt}|{raw}".encode("utf-8"), digest_size=6).hexdigest()
    return f"INC_{digest}"


def _name_parts(name: str) -> list[str]:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    return [p for p in parts if p.lower().strip(".") not in {t.strip(".") for t in _TITLE}]


def redact_transcript(
    text: str,
    *,
    staff: list[str],
    students: Iterable[str],
    roles: Iterable[str],
) -> str:
    """Replace known names. Raw text is not returned."""
    out = text or ""
    # Longest names first so "Jane Example" goes before "Jane".
    staff_hits: list[tuple[str, str]] = []
    for name in list(staff) + list(roles):
        name = (name or "").strip()
        if not name:
            continue
        label = f"[{role_bucket(name).upper()}]"
        staff_hits.append((name, label))
        parts = _name_parts(name)
        if parts:
            staff_hits.append((" ".join(parts), label))
            staff_hits.append((parts[-1], label))
    staff_hits.sort(key=lambda item: len(item[0]), reverse=True)
    for needle, label in staff_hits:
        out = re.sub(re.escape(needle), label, out, flags=re.IGNORECASE)

    student_hits: list[str] = []
    for name in students:
        name = (name or "").strip()
        if not name:
            continue
        student_hits.append(name)
        parts = _name_parts(name)
        if parts:
            student_hits.append(" ".join(parts))
            student_hits.append(parts[-1])
    student_hits = sorted(set(student_hits), key=len, reverse=True)
    for needle in student_hits:
        out = re.sub(re.escape(needle), "[STUDENT]", out, flags=re.IGNORECASE)

    out = _NAME_TOKEN.sub("[PERSON]", out)
    return re.sub(r"\s+", " ", out).strip()


def _numeric_acoustics(features: Any) -> dict[str, float]:
    if not isinstance(features, dict):
        return {}
    clean: dict[str, float] = {}
    for key, val in features.items():
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            clean[str(key)] = float(val)
    return clean


def _safe_info_score(blob: Any) -> dict[str, float] | None:
    if not isinstance(blob, dict):
        return None
    out: dict[str, float] = {}
    for key in ("value", "lexical_surprisal", "acoustic_composite_z"):
        val = blob.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            out[key] = float(val)
    return out or None


def _safe_tags(tags: Any) -> list[str]:
    allowed = {
        "fire_drill",
        "lockdown_drill",
        "tornado_drill",
        "early_release",
        "late_start",
        "graduation",
        "finals",
        "assembly",
        "bus_issue",
        "opening_weeks",
        "ordinary",
        "testing",
        "incident_adjacent",
        "fight_report",
        "critical_baseline",
        "student_transmit",
    }
    out: list[str] = []
    for tag in tags or []:
        t = str(tag).strip().lower().replace(" ", "_")
        if t in allowed:
            out.append(t)
    return out


def looks_like_student_transmit(row: dict[str, Any]) -> bool:
    tags = {str(t).lower() for t in (row.get("tags") or [])}
    if "student_transmit" in tags:
        return True
    students = [s for s in (row.get("students") or []) if str(s).strip()]
    speaker = (row.get("likely_speaker") or row.get("primary_speaker") or "")
    speaker_l = str(speaker).strip().lower()
    if students and speaker_l and any(s.lower() in speaker_l or speaker_l in s.lower() for s in students):
        return True
    return False


def export_row(
    row: dict[str, Any],
    *,
    staff: list[str],
    salt: str,
    exclude_medical: bool = True,
    include_redacted_transcript: bool = True,
    day_tags: list[str] | None = None,
    session_label: str | None = None,
) -> dict[str, Any] | None:
    category = str(row.get("category") or "Other / Unclear")
    if exclude_medical and category == MEDICAL_CATEGORY:
        return None
    if looks_like_student_transmit(row):
        return None

    students = [str(s) for s in (row.get("students") or []) if str(s).strip()]
    raw_roles = [str(r) for r in (row.get("roles") or []) if str(r).strip()]
    role_codes = sorted({staff_role_code(r) for r in raw_roles}) if raw_roles else []

    tags = _safe_tags(list(row.get("tags") or []) + list(day_tags or []))
    out: dict[str, Any] = {
        "session": session_label,
        "start_iso": row.get("start_iso"),
        "duration_sec": row.get("duration_sec"),
        "category": category,
        "cat_conf": row.get("cat_conf"),
        "is_noise": bool(row.get("is_noise")),
        "whisper_conf": row.get("whisper_conf"),
        "model": row.get("model"),
        "critical_baseline": bool(row.get("critical_baseline")),
        "incident_id_hash": hash_incident_id(str(row.get("incident_id") or ""), salt),
        "role_codes": role_codes,
        "student_mention_count": len(students),
        "acoustic_features": _numeric_acoustics(row.get("acoustic_features")),
        "information_score": _safe_info_score(row.get("information_score")),
        "acoustic_zscores": _numeric_acoustics(row.get("acoustic_zscores")),
        "lexical_surprisal": row.get("lexical_surprisal"),
        "tags": tags,
    }
    if include_redacted_transcript:
        out["transcript_redacted"] = redact_transcript(
            str(row.get("transcription") or ""),
            staff=staff,
            students=students,
            roles=raw_roles,
        )
    return out


def _iter_source_rows(session_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for manifest in (
        session_dir / "session_manifest.retagged.jsonl",
        session_dir / "session_manifest.jsonl",
    ):
        if manifest.is_file():
            for line in manifest.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if rows:
                return rows
    for sidecar in sorted(session_dir.glob("tx_*.json")):
        try:
            rows.append(json.loads(sidecar.read_text(encoding="utf-8")))
        except Exception:
            continue
    return rows


def _day_tags(session_dir: Path) -> list[str]:
    try:
        from edupulse.day_context import load_day_context

        ctx = load_day_context(session_dir)
        return [str(t) for t in (ctx.get("tags") or [])]
    except Exception:
        js = session_dir / "day_context.json"
        if js.is_file():
            try:
                return list(json.loads(js.read_text(encoding="utf-8")).get("tags") or [])
            except Exception:
                return []
        return []


def export_session(
    session_dir: Path,
    *,
    staff: list[str],
    salt: str,
    exclude_medical: bool = True,
    include_redacted_transcript: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    session_dir = Path(session_dir)
    source = _iter_source_rows(session_dir)
    tags = _day_tags(session_dir)
    kept: list[dict[str, Any]] = []
    stats = {"read": len(source), "kept": 0, "dropped_medical": 0, "dropped_student_tx": 0}
    for row in source:
        if exclude_medical and str(row.get("category") or "") == MEDICAL_CATEGORY:
            stats["dropped_medical"] += 1
            continue
        if looks_like_student_transmit(row):
            stats["dropped_student_tx"] += 1
            continue
        exported = export_row(
            row,
            staff=staff,
            salt=salt,
            exclude_medical=exclude_medical,
            include_redacted_transcript=include_redacted_transcript,
            day_tags=tags,
            session_label=session_dir.name,
        )
        if exported is None:
            continue
        kept.append(exported)
    stats["kept"] = len(kept)
    return kept, stats


def default_export_dir() -> Path:
    return Path.home() / "edupulse" / "research_export"


def write_export(
    sessions: list[Path],
    out_dir: Path,
    *,
    staff_file: Path | None = None,
    exclude_medical: bool = True,
    include_redacted_transcript: bool = True,
    salt: str | None = None,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    staff = load_staff_names(staff_file)
    salt = salt or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    all_rows: list[dict[str, Any]] = []
    session_stats: list[dict[str, Any]] = []
    for session in sessions:
        rows, stats = export_session(
            session,
            staff=staff,
            salt=salt,
            exclude_medical=exclude_medical,
            include_redacted_transcript=include_redacted_transcript,
        )
        all_rows.extend(rows)
        session_stats.append({"session": Path(session).name, **stats})

    table_path = out_dir / "research_table.jsonl"
    with table_path.open("w", encoding="utf-8") as handle:
        for row in all_rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    codebook = out_dir / "codebook.md"
    codebook.write_text(
        "# EduPulse research export codebook\n\n"
        "This folder is the analysis file. It is not the live capture store.\n\n"
        "- `transcript_redacted`: speech with staff names replaced by role labels and student names by [STUDENT].\n"
        "- Raw transcripts and WAVs stay next to the live capture files.\n"
        "- `role_codes`: stable hashes of staff role labels.\n"
        "- `incident_id_hash`: salted hash of the live INC-id.\n"
        "- `student_mention_count`: count only.\n"
        f"- Rows: {len(all_rows)}\n"
        f"- Medical category dropped: {exclude_medical}\n",
        encoding="utf-8",
    )
    log_path = out_dir / "export_log.json"
    log_path.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "sessions": session_stats,
                "exclude_medical": exclude_medical,
                "include_redacted_transcript": include_redacted_transcript,
                "staff_file_used": bool(staff),
                "n_rows": len(all_rows),
                "wav_copied": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return table_path


def discover_sessions(base_dir: Path) -> list[Path]:
    base = Path(base_dir)
    if not base.is_dir():
        return []
    sessions = [p for p in base.iterdir() if p.is_dir()]
    return sorted(sessions, key=lambda p: p.name)
