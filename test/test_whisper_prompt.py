"""Unit checks for Whisper fingerprint prompt + ASR name aliases."""

from __future__ import annotations

import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from edupulse.categories import (  # noqa: E402
    _staff_title_last,
    build_enhanced_initial_prompt,
)
from edupulse.semantic_map import parse_radio_call  # noqa: E402


STAFF = [
    "Ms. Cheryl Yannett",
    "Mr. Aaron Mayes",
    "Dr. Tracy Strickland",
    "Mr. Adrian Atkinson",  # early alphabet — old [:25] kept these, dropped Yannett
]


def test_title_last_compression():
    assert _staff_title_last("Ms. Cheryl Yannett") == "Ms. Yannett"
    assert _staff_title_last("Mr. Chandler") == "Mr. Chandler"
    assert _staff_title_last("Captain Joseph Hatfield") == "Captain Hatfield"


def test_prompt_includes_yannett_and_hot_tail():
    prompt = build_enhanced_initial_prompt(known_staff=STAFF, common_words=["10-4", "go for"])
    assert "Yannett" in prompt
    assert "Mayes" in prompt
    # Hot phrases / call signs at the end (Whisper keeps the tail if ever truncated)
    assert "Yannett to Mayes" in prompt
    assert "Go for Mayes" in prompt
    # Must NOT be the old alphabetical full-name [:25] only
    assert "Cheryl" not in prompt  # title+last / last-name form


def test_prompt_fits_stock_budget():
    """Full live staff list must fit ≤223 tokens (no silent truncation)."""
    from edupulse.whisper_prompt_budget import STOCK_PROMPT_BUDGET, measure_prompt

    staff_path = Path(__file__).resolve().parents[1] / "hardware" / "capture" / "staff_names.txt"
    words_path = Path(__file__).resolve().parents[1] / "hardware" / "capture" / "common_words.txt"
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
    prompt = build_enhanced_initial_prompt(known_staff=staff, common_words=words)
    report = measure_prompt(prompt, budget=STOCK_PROMPT_BUDGET)
    assert report.tokens <= STOCK_PROMPT_BUDGET, (
        f"prompt is {report.tokens} tokens; stock budget is {STOCK_PROMPT_BUDGET}"
    )
    assert not report.truncated
    assert "Yannett" in prompt and "Mayes" in prompt


def test_asr_aliases_recover_gold_call():
    bad = "Deannette to Mr. Mase."
    parsed = parse_radio_call(bad, STAFF)
    assert parsed["caller"] == "Ms. Cheryl Yannett"
    assert parsed["callee"] == "Mr. Aaron Mayes"
    assert any(e["name"] == "Ms. Cheryl Yannett" for e in parsed["enrollments"])


def test_go_for_enrolls_mayes():
    parsed = parse_radio_call("Go for Mr. Mayes.", STAFF)
    assert parsed["self_id"] == "Mr. Aaron Mayes"
    assert any(e["reason"] == "self_id" for e in parsed["enrollments"])


if __name__ == "__main__":
    test_title_last_compression()
    test_prompt_includes_yannett_and_hot_tail()
    test_prompt_fits_stock_budget()
    test_asr_aliases_recover_gold_call()
    test_go_for_enrolls_mayes()
    print("ok")
