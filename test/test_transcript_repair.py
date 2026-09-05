"""Tests for lexicon + transcript repair (mocked API)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from edupulse.lexicon import SchoolLexicon, build_lexicon  # noqa: E402
from edupulse.transcript_repair import repair_transcript  # noqa: E402


def test_lexicon_includes_full_staff_and_coach_richard():
    lex = build_lexicon()
    assert lex.stats()["n_staff"] >= 50
    assert any("Yannett" in s for s in lex.staff)
    assert any("Richard" in s for s in lex.staff)
    block = lex.as_prompt_block()
    assert "Coach Richard" in block
    assert len(block) > 500  # far beyond Whisper's tiny prompt


def test_xai_backend_skips_without_api_key():
    import os

    os.environ.pop("XAI_API_KEY", None)
    r = repair_transcript("Codes for Shar.", backend="xai")
    assert r.skipped
    assert "XAI_API_KEY" in r.skip_reason
    assert r.corrected == "Codes for Shar."


def test_queue_backend_appends_job(tmp_path: Path | None = None):
    from pathlib import Path as P

    q = P("/tmp/edupulse_repair_test_queue.jsonl")
    if q.exists():
        q.unlink()
    lex = SchoolLexicon(staff=["Coach Richard"], radio_staff=["Coach Richard"])
    r = repair_transcript("Codes for Shar.", lex, backend="queue", queue_path=q)
    assert r.skipped and str(r.skip_reason).startswith("queued:")
    assert q.exists() and "Codes for Shar" in q.read_text()
    q.unlink(missing_ok=True)


def test_ollama_parse_path_mocked():
    lex = SchoolLexicon(
        staff=["Coach Richard", "Ms. Cheryl Yannett", "Mr. Aaron Mayes"],
        radio_staff=["Coach Richard"],
        common_words=["go for", "10-4"],
    )
    payload = {
        "message": {
            "content": json.dumps(
                {
                    "corrected": "Coach Richard.",
                    "changed": True,
                    "rationale": "phonetic match to Coach Richard",
                }
            )
        }
    }

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode()

    with patch("urllib.request.urlopen", return_value=_Resp()):
        r = repair_transcript("Codes for Shar.", lex, backend="ollama")
    assert r.changed
    assert r.corrected == "Coach Richard."
    assert r.backend == "ollama"


if __name__ == "__main__":
    test_lexicon_includes_full_staff_and_coach_richard()
    test_xai_backend_skips_without_api_key()
    test_queue_backend_appends_job()
    test_ollama_parse_path_mocked()
    print("ok")
