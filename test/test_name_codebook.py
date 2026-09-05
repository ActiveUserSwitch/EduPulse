"""Tests for phonetic staff name codebook."""

from __future__ import annotations

import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from edupulse.name_codebook import (  # noqa: E402
    HAND_ASR_ALIASES,
    build_name_codebook,
    set_active_codebook,
)
from edupulse.categories import build_enhanced_initial_prompt  # noqa: E402
from edupulse.semantic_map import parse_radio_call  # noqa: E402
from edupulse.whisper_prompt_budget import STOCK_PROMPT_BUDGET, measure_prompt  # noqa: E402


STAFF = [
    "Ms. Cheryl Yannett",
    "Mr. Aaron Mayes",
    "Dr. Tracy Strickland",
    "Mr. Adrian Atkinson",
    "Ms. Shelley Broome",
    "Mr. Chandler",
    "Ms. Deborahk Chandler",
]


def test_min_chars_floor_no_single_letter_yannett():
    cb = build_name_codebook(STAFF, min_chars=4, tokenizer=None)
    by = {e.last_name: e for e in cb.entries}
    assert by["Yannett"].prompt_alias == "Yann" or len(by["Yannett"].prompt_alias) >= 4
    assert by["Yannett"].prompt_alias.lower() != "y"
    assert len(by["Mayes"].prompt_alias) >= 4


def test_aliases_uniquely_decodable():
    cb = build_name_codebook(STAFF, min_chars=4, tokenizer=None)
    aliases = [e.prompt_alias.lower() for e in cb.entries]
    assert len(aliases) == len(set(aliases))
    # no alias is another last name incorrectly
    decode = cb.decode_map()
    for e in cb.entries:
        assert decode[e.prompt_alias.lower()] == e.last_name.lower()


def test_hand_aliases_round_trip():
    cb = build_name_codebook(STAFF, min_chars=4, tokenizer=None)
    set_active_codebook(cb)
    assert cb.normalize_token("Deannette") == "yannett"
    assert cb.normalize_token("Mase") == "mayes"
    assert HAND_ASR_ALIASES["mason"] == "mayes"


def test_resolver_uses_codebook():
    cb = build_name_codebook(STAFF, min_chars=4, tokenizer=None)
    set_active_codebook(cb)
    parsed = parse_radio_call("Deannette to Mr. Mase.", STAFF)
    assert parsed["caller"] == "Ms. Cheryl Yannett"
    assert parsed["callee"] == "Mr. Aaron Mayes"


def test_expand_transcript_shows_canonical_not_codes():
    from edupulse.name_codebook import expand_transcript_names

    cb = build_name_codebook(STAFF, min_chars=4, tokenizer=None)
    set_active_codebook(cb)
    display, raw = expand_transcript_names("Yanne to Mr. Mase.")
    assert raw == "Yanne to Mr. Mase."
    assert display == "Yannett to Mr. Mayes."


def test_prompt_with_codebook_fits_budget():
    staff_path = _repo / "hardware" / "capture" / "staff_names.txt"
    words_path = _repo / "hardware" / "capture" / "common_words.txt"
    staff = [
        ln.strip()
        for ln in staff_path.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    words = [
        ln.strip()
        for ln in words_path.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    prompt = build_enhanced_initial_prompt(known_staff=staff, common_words=words, use_codebook=True)
    report = measure_prompt(prompt, budget=STOCK_PROMPT_BUDGET)
    assert report.tokens <= STOCK_PROMPT_BUDGET
    assert "Yannett" in prompt or "Yann" in prompt
    assert "Mayes" in prompt or "Maye" in prompt
    assert "Codes:" in prompt


if __name__ == "__main__":
    test_min_chars_floor_no_single_letter_yannett()
    test_aliases_uniquely_decodable()
    test_hand_aliases_round_trip()
    test_resolver_uses_codebook()
    test_expand_transcript_shows_canonical_not_codes()
    test_prompt_with_codebook_fits_budget()
    print("ok")
