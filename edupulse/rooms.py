"""Room → teacher assignments for soft speaker inference.

When a teacher radios admin for a phone pickup tied to their room, the
speaker is often that room's assigned teacher.

Live file (gitignored): hardware/capture/room_assignments.txt
Template: hardware/capture/room_assignments.example.txt
"""
from __future__ import annotations

import re
from pathlib import Path

_PHONE_PICKUP = re.compile(
    r"\b(phone\s*pick\s*up|pickup|pick\s*up|phone\s*call|call\s+on\s+line|"
    r"parent\s+on\s+(the\s+)?phone|front\s+office|admin)\b",
    re.I,
)
_ROOM = re.compile(
    r"\b(?:room|rm\.?)\s*([0-9]{2,4}[a-z]?)\b|\b([0-9]{3,4}[a-z]?)\s+(?:needs|need|for|to)\b",
    re.I,
)


def default_room_assignments_path() -> Path:
    return Path(__file__).resolve().parents[1] / "hardware" / "capture" / "room_assignments.txt"


def load_room_assignments(path: Path | None = None) -> dict[str, str]:
    """Return {room_id_lower: canonical staff name}."""
    path = Path(path) if path else default_room_assignments_path()
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            continue
        room, name = line.split("|", 1)
        room = room.strip().lower()
        name = name.strip()
        if room and name:
            out[room] = name
    return out


def rooms_mentioned(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for m in _ROOM.finditer(text):
        r = (m.group(1) or m.group(2) or "").strip().lower()
        if r and r not in found:
            found.append(r)
    return found


def is_phone_pickup_context(text: str) -> bool:
    return bool(text and _PHONE_PICKUP.search(text))


def infer_speaker_from_room(
    text: str,
    room_map: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """If phone-pickup + room mentioned, return (teacher_name, room_id).

    Soft hint only — does not enroll voice by itself.
    """
    if not text or not is_phone_pickup_context(text):
        return None, None
    room_map = room_map if room_map is not None else load_room_assignments()
    if not room_map:
        return None, None
    for room in rooms_mentioned(text):
        if room in room_map:
            return room_map[room], room
    return None, None
