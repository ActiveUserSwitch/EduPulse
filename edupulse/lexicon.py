"""Full-school lexicon for LLM transcript repair (not Whisper-budgeted).

Whisper ``initial_prompt`` is capped at ~223 BPE tokens. The repair LLM can
ingest the entire staff list, places, and radio phrases. See
``docs/transcript_repair.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _load_lines(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


@dataclass
class SchoolLexicon:
    staff: list[str] = field(default_factory=list)
    radio_staff: list[str] = field(default_factory=list)
    common_words: list[str] = field(default_factory=list)
    rooms: list[str] = field(default_factory=list)
    day_context: str = ""
    protocol_hints: list[str] = field(default_factory=list)

    def as_prompt_block(self) -> str:
        """Serialize lexicon for an LLM system/user context (no Whisper truncation)."""
        parts: list[str] = []
        parts.append(
            "Domain: US K-12 school administrative push-to-talk radio.\n"
            "Protocol examples: \"Name to Name\", \"Go for Name\", \"Coach X\", "
            "\"10-4\", \"thank you\", phone-call requests, room/office locations."
        )
        if self.radio_staff:
            parts.append(
                "Known radio users (high prior):\n- " + "\n- ".join(self.radio_staff)
            )
        if self.staff:
            parts.append("All staff (Title First Last):\n- " + "\n- ".join(self.staff))
        if self.rooms:
            parts.append("Rooms / places:\n- " + "\n- ".join(self.rooms))
        if self.common_words:
            parts.append(
                "Frequent channel terms: " + ", ".join(self.common_words)
            )
        if self.protocol_hints:
            parts.append("Extra protocol hints: " + "; ".join(self.protocol_hints))
        if self.day_context.strip():
            parts.append("Day context notes:\n" + self.day_context.strip())
        return "\n\n".join(parts)

    def stats(self) -> dict[str, Any]:
        block = self.as_prompt_block()
        return {
            "n_staff": len(self.staff),
            "n_radio_staff": len(self.radio_staff),
            "n_common_words": len(self.common_words),
            "n_rooms": len(self.rooms),
            "day_context_chars": len(self.day_context),
            "prompt_block_chars": len(block),
        }


_DEFAULT_PROTOCOL = [
    "Yannett to Mayes",
    "Go for Mayes",
    "Go for Mr. Mayes",
    "Coach Richard",
    "go ahead",
    "10-4",
    "thank you",
    "are you in your office",
]


def load_room_lines(path: Path | None) -> list[str]:
    """Parse room_assignments.txt lines like ``700|Mr. Aaron Mayes`` into place hints."""
    if path is None or not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            room, who = line.split("|", 1)
            out.append(f"Room {room.strip()}: {who.strip()}")
        else:
            out.append(line)
    return out


def build_lexicon(
    *,
    staff_file: Path | None = None,
    radio_staff_file: Path | None = None,
    words_file: Path | None = None,
    rooms_file: Path | None = None,
    day_context_md: Path | None = None,
    capture_root: Path | None = None,
) -> SchoolLexicon:
    """Load lexicon files from EduPulse capture hardware paths or explicit paths."""
    root = Path(__file__).resolve().parents[1]
    cap_hw = root / "hardware" / "capture"
    staff_file = staff_file or (cap_hw / "staff_names.txt")
    radio_staff_file = radio_staff_file or (cap_hw / "radio_staff.txt")
    words_file = words_file or (cap_hw / "common_words.txt")
    rooms_file = rooms_file or (cap_hw / "room_assignments.txt")

    day_text = ""
    if day_context_md and day_context_md.exists():
        day_text = day_context_md.read_text(encoding="utf-8", errors="ignore")
    elif capture_root and capture_root.exists():
        md = capture_root / "DAY_CONTEXT.md"
        if md.exists():
            day_text = md.read_text(encoding="utf-8", errors="ignore")

    return SchoolLexicon(
        staff=_load_lines(staff_file),
        radio_staff=_load_lines(radio_staff_file),
        common_words=_load_lines(words_file),
        rooms=load_room_lines(rooms_file),
        day_context=day_text,
        protocol_hints=list(_DEFAULT_PROTOCOL),
    )
