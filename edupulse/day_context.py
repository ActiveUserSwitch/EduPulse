"""Per-day human context for EduPulse capture sessions.

School days are not interchangeable: fire drills, lockdown drills, early
release, graduation, etc. change how radio traffic should be read.

Canonical file (human-edited):
  ~/edupulse/captures/<session>/DAY_CONTEXT.md

Machine-readable companion (optional tags):
  ~/edupulse/captures/<session>/day_context.json

CLI (via scripts/edupulse):
  edupulse note "Fire drill mid-morning"
  edupulse context              # show / path for latest or --day
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


CONTEXT_MD = "DAY_CONTEXT.md"
CONTEXT_JSON = "day_context.json"

_TEMPLATE = """# Day context — {session}

Human notes for interpreting this day's radio traffic.
Edit freely, or append with: `edupulse note "…" --day {session}`

## Tags
<!-- Uncomment / add as needed:
- fire_drill
- lockdown_drill
- tornado_drill
- early_release
- late_start
- graduation
- finals
- assembly
- bus_issue
- other: …
-->

## Timeline notes
<!-- Bullet what mattered and roughly when, e.g.:
- ~09:15 Fire drill (full building)
-->

## Freeform

"""


def context_md_path(session_dir: Path) -> Path:
    return Path(session_dir) / CONTEXT_MD


def context_json_path(session_dir: Path) -> Path:
    return Path(session_dir) / CONTEXT_JSON


def ensure_day_context(session_dir: Path, *, session_name: str | None = None) -> Path:
    """Create DAY_CONTEXT.md if missing. Returns path to the markdown file."""
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    name = session_name or session_dir.name
    md = context_md_path(session_dir)
    if not md.exists():
        md.write_text(_TEMPLATE.format(session=name), encoding="utf-8")
    js = context_json_path(session_dir)
    if not js.exists():
        payload = {
            "session": name,
            "tags": [],
            "notes": [],
            "created_iso": datetime.now().isoformat(timespec="seconds"),
            "updated_iso": datetime.now().isoformat(timespec="seconds"),
        }
        js.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return md


def _load_json(session_dir: Path) -> dict[str, Any]:
    js = context_json_path(session_dir)
    if not js.exists():
        ensure_day_context(session_dir)
    try:
        return json.loads(js.read_text(encoding="utf-8"))
    except Exception:
        return {
            "session": Path(session_dir).name,
            "tags": [],
            "notes": [],
            "updated_iso": datetime.now().isoformat(timespec="seconds"),
        }


def _save_json(session_dir: Path, data: dict[str, Any]) -> None:
    data["updated_iso"] = datetime.now().isoformat(timespec="seconds")
    context_json_path(session_dir).write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def append_note(
    session_dir: Path,
    note: str,
    *,
    tags: list[str] | None = None,
    when: str | None = None,
) -> Path:
    """Append a human note (+ optional tags) to the day's context files."""
    session_dir = Path(session_dir)
    ensure_day_context(session_dir)
    note = (note or "").strip()
    if not note:
        raise ValueError("empty note")

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    when_bit = f" ({when})" if when else ""
    line = f"- [{stamp}]{when_bit} {note}"

    md = context_md_path(session_dir)
    text = md.read_text(encoding="utf-8")
    marker = "## Timeline notes"
    if marker in text:
        parts = text.split(marker, 1)
        rest = parts[1]
        # Keep optional HTML comment, then append our bullet before Freeform / next H2
        m = re.match(r"(\n?(?:<!--.*?-->\n)?\n*)", rest, flags=re.S)
        head = m.group(1) if m else "\n"
        body = rest[len(head) :]
        # If body already starts with bullets, prepend ours among them
        text = parts[0] + marker + head + line + "\n" + body.lstrip("\n")
    else:
        text = text.rstrip() + "\n\n## Timeline notes\n" + line + "\n"
    md.write_text(text, encoding="utf-8")

    data = _load_json(session_dir)
    entry: dict[str, Any] = {"iso": datetime.now().isoformat(timespec="seconds"), "text": note}
    if when:
        entry["when"] = when
    data.setdefault("notes", []).append(entry)
    if tags:
        existing = {t.lower(): t for t in (data.get("tags") or [])}
        for t in tags:
            t = t.strip().lstrip("#")
            if t and t.lower() not in existing:
                existing[t.lower()] = t
        data["tags"] = sorted(existing.values(), key=str.lower)
        # Also mirror tags into markdown Tags section if still commented-only
        _ensure_tags_in_md(md, list(data["tags"]))
    _save_json(session_dir, data)
    return md


def _ensure_tags_in_md(md: Path, tags: list[str]) -> None:
    if not tags:
        return
    text = md.read_text(encoding="utf-8")
    marker = "## Tags"
    if marker not in text:
        return
    # Replace tags section content with active bullets (keep a short comment)
    new_block = "## Tags\n" + "\n".join(f"- {t}" for t in tags) + "\n"
    text2 = re.sub(
        r"## Tags\n(?:.*?)(?=\n## |\Z)",
        new_block + "\n",
        text,
        count=1,
        flags=re.S,
    )
    if text2 != text:
        md.write_text(text2, encoding="utf-8")


def load_day_context(session_dir: Path) -> dict[str, Any]:
    """Return merged context (json + path to markdown)."""
    session_dir = Path(session_dir)
    ensure_day_context(session_dir)
    data = _load_json(session_dir)
    data["markdown_path"] = str(context_md_path(session_dir))
    data["markdown"] = context_md_path(session_dir).read_text(encoding="utf-8")
    return data


def find_latest_session(captures_dir: Path | None = None) -> Path | None:
    root = Path(captures_dir or (Path.home() / "edupulse" / "captures"))
    if not root.is_dir():
        return None
    days = sorted(
        [p for p in root.iterdir() if p.is_dir() and list(p.glob("tx_*.wav"))],
        key=lambda p: p.name,
        reverse=True,
    )
    return days[0] if days else None


def resolve_session_dir(
    day: str | None = None,
    captures_dir: Path | None = None,
) -> Path:
    root = Path(captures_dir or (Path.home() / "edupulse" / "captures"))
    if day:
        # Accept full folder name or date prefix
        candidate = root / day
        if candidate.is_dir():
            return candidate
        matches = sorted(root.glob(f"{day}*"))
        dirs = [p for p in matches if p.is_dir()]
        if len(dirs) == 1:
            return dirs[0]
        if len(dirs) > 1:
            # Prefer exact date_school-day
            for p in dirs:
                if p.name == f"{day}_school-day":
                    return p
            return dirs[-1]
        # Create dated school-day folder for notes even before capture
        created = root / f"{day}_school-day"
        created.mkdir(parents=True, exist_ok=True)
        return created
    latest = find_latest_session(root)
    if latest is None:
        # Fall back to today's folder name
        today = datetime.now().strftime("%Y-%m-%d")
        created = root / f"{today}_school-day"
        created.mkdir(parents=True, exist_ok=True)
        return created
    return latest
