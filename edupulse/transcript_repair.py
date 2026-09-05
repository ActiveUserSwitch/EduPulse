"""Second-pass repair of Whisper transcripts.

Backends (pick one — billing matters):

  ollama  (default)  Local models via Ollama — **no per-token API bill**.
                     Uses whatever you already run (e.g. llama3.1).

  xai                Metered SpaceXAI / xAI developer API (``XAI_API_KEY`` /
                     ``api.x.ai``). **Separate from SuperGrok / Grok Build.**
                     Opt-in only.

  queue               Write a JSONL job file you (or a Grok Build / grokbot
                     session) can process under the subscription you already pay for.

Whisper fingerprint ≤223 tokens; this layer may use the full school lexicon.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from edupulse.lexicon import SchoolLexicon, build_lexicon

# Default: local Ollama — NOT the metered xAI developer API.
DEFAULT_BACKEND = os.environ.get("EDUPULSE_REPAIR_BACKEND", "ollama").strip().lower()
DEFAULT_OLLAMA_MODEL = os.environ.get("EDUPULSE_OLLAMA_MODEL", "llama3.1:latest")
DEFAULT_XAI_MODEL = os.environ.get("EDUPULSE_REPAIR_MODEL", "grok-4.5")
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
XAI_BASE_URL = "https://api.x.ai/v1"
DEFAULT_QUEUE_PATH = Path.home() / "edupulse" / "repair_queue.jsonl"


@dataclass
class RepairResult:
    original: str
    corrected: str
    changed: bool
    model: str
    backend: str = ""
    rationale: str = ""
    skipped: bool = False
    skip_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_SYSTEM = """You repair short school radio ASR transcripts.

You will receive:
1) A lexicon of staff names, radio users, places, and common phrases.
2) One Whisper transcript that may contain phonetic errors.

Rules:
- Prefer corrections that are phonetically close to the ASR text AND appear in the lexicon
  (example: "Codes for Shar" → "Coach Richard" when Coach Richard is listed).
- Keep the same speech act (call, go-for, question, ack). Do not invent new events.
- Output JSON only: {"corrected": "...", "changed": true/false, "rationale": "brief"}.
- If unsure, set changed=false and corrected to the original text unchanged.
- Do not add quotes around the whole transcript unless they were in the original.
- One transmission only; no multi-sentence essays.
"""


def _parse_model_json(raw: str, original: str) -> tuple[str, bool, str, str]:
    """Return corrected, changed, rationale, skip_reason."""
    corrected = original
    changed = False
    rationale = ""
    try:
        blob = raw
        m = re.search(r"\{[\s\S]*\}", blob)
        if m:
            blob = m.group(0)
        data = json.loads(blob)
        corrected = str(data.get("corrected") or original).strip() or original
        changed = bool(data.get("changed")) and corrected != original
        if corrected == original:
            changed = False
        rationale = str(data.get("rationale") or "")
        return corrected, changed, rationale, ""
    except Exception:
        plain = (raw or "").strip().strip('"')
        if plain and plain != original and len(plain) < max(200, 3 * len(original)):
            return plain, True, "plain_text_fallback", ""
        return original, False, (raw or "")[:200], "unparseable_response"


def _user_payload(original: str, lex: SchoolLexicon) -> str:
    return (
        "LEXICON:\n"
        f"{lex.as_prompt_block()}\n\n"
        "WHISPER_TRANSCRIPT:\n"
        f"{original}\n\n"
        "Return JSON only."
    )


def _repair_ollama(
    original: str,
    lex: SchoolLexicon,
    model: str,
) -> RepairResult:
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _user_payload(original, lex)},
        ],
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return RepairResult(
            original=original,
            corrected=original,
            changed=False,
            model=model,
            backend="ollama",
            skipped=True,
            skip_reason=f"ollama_unreachable: {e}",
        )
    except Exception as e:
        return RepairResult(
            original=original,
            corrected=original,
            changed=False,
            model=model,
            backend="ollama",
            skipped=True,
            skip_reason=f"ollama_error: {e}",
        )

    raw = ((data.get("message") or {}).get("content") or "").strip()
    corrected, changed, rationale, skip = _parse_model_json(raw, original)
    if skip:
        return RepairResult(
            original=original,
            corrected=original,
            changed=False,
            model=model,
            backend="ollama",
            skipped=True,
            skip_reason=skip,
            rationale=rationale,
        )
    return RepairResult(
        original=original,
        corrected=corrected,
        changed=changed,
        model=model,
        backend="ollama",
        rationale=rationale,
    )


def _repair_xai(
    original: str,
    lex: SchoolLexicon,
    model: str,
) -> RepairResult:
    """Metered developer API — opt-in only. Not SuperGrok / Grok Build."""
    api_key = os.environ.get("XAI_API_KEY", "").strip()
    if not api_key:
        return RepairResult(
            original=original,
            corrected=original,
            changed=False,
            model=model,
            backend="xai",
            skipped=True,
            skip_reason="XAI_API_KEY not set (metered api.x.ai — not used by default)",
        )
    try:
        from openai import OpenAI
    except ImportError:
        return RepairResult(
            original=original,
            corrected=original,
            changed=False,
            model=model,
            backend="xai",
            skipped=True,
            skip_reason="openai package not installed",
        )

    client = OpenAI(api_key=api_key, base_url=XAI_BASE_URL)
    try:
        corrected_raw = ""
        if hasattr(client, "responses"):
            resp = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": _user_payload(original, lex)},
                ],
                temperature=0.0,
            )
            corrected_raw = (getattr(resp, "output_text", None) or "").strip()
        if not corrected_raw:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": _user_payload(original, lex)},
                ],
                temperature=0.0,
            )
            corrected_raw = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return RepairResult(
            original=original,
            corrected=original,
            changed=False,
            model=model,
            backend="xai",
            skipped=True,
            skip_reason=f"api_error: {e}",
        )

    corrected, changed, rationale, skip = _parse_model_json(corrected_raw, original)
    if skip:
        return RepairResult(
            original=original,
            corrected=original,
            changed=False,
            model=model,
            backend="xai",
            skipped=True,
            skip_reason=skip,
            rationale=rationale,
        )
    return RepairResult(
        original=original,
        corrected=corrected,
        changed=changed,
        model=model,
        backend="xai",
        rationale=rationale,
    )


def _repair_queue(
    original: str,
    lex: SchoolLexicon,
    *,
    queue_path: Path,
    meta: dict[str, Any] | None = None,
) -> RepairResult:
    """Enqueue for Grok Build / grokbot (subscription you already pay for)."""
    queue_path = queue_path.expanduser()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    job = {
        "original": original,
        "lexicon_stats": lex.stats(),
        "lexicon": lex.as_prompt_block(),
        "system": _SYSTEM,
        "meta": meta or {},
    }
    with queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(job, ensure_ascii=False) + "\n")
    return RepairResult(
        original=original,
        corrected=original,
        changed=False,
        model="queue",
        backend="queue",
        skipped=True,
        skip_reason=f"queued:{queue_path}",
        rationale="Process with Grok Build / grokbot under your subscription; no api.x.ai charges.",
    )


def repair_transcript(
    text: str,
    lexicon: SchoolLexicon | None = None,
    *,
    backend: str | None = None,
    model: str | None = None,
    dry_run: bool = False,
    queue_path: Path | None = None,
    queue_meta: dict[str, Any] | None = None,
) -> RepairResult:
    """Repair one Whisper transcript.

    Default backend is **ollama** (local, free). Pass ``backend='xai'`` only if you
    intentionally want the metered developer API.
    """
    original = (text or "").strip()
    be = (backend or DEFAULT_BACKEND).strip().lower()
    if be in ("spacexai", "grok-api", "api"):
        be = "xai"
    if be in ("grokbuild", "grok-build", "grokbot", "bot"):
        be = "queue"

    if be == "ollama":
        use_model = model or DEFAULT_OLLAMA_MODEL
    elif be == "xai":
        use_model = model or DEFAULT_XAI_MODEL
    else:
        use_model = model or "queue"

    if not original:
        return RepairResult(
            original="",
            corrected="",
            changed=False,
            model=use_model,
            backend=be,
            skipped=True,
            skip_reason="empty",
        )

    lex = lexicon or build_lexicon()
    if dry_run:
        return RepairResult(
            original=original,
            corrected=original,
            changed=False,
            model=use_model,
            backend=be,
            skipped=True,
            skip_reason="dry_run",
            rationale="dry_run",
        )

    if be == "ollama":
        return _repair_ollama(original, lex, use_model)
    if be == "xai":
        return _repair_xai(original, lex, use_model)
    if be == "queue":
        return _repair_queue(
            original,
            lex,
            queue_path=queue_path or DEFAULT_QUEUE_PATH,
            meta=queue_meta,
        )
    return RepairResult(
        original=original,
        corrected=original,
        changed=False,
        model=use_model,
        backend=be,
        skipped=True,
        skip_reason=f"unknown_backend:{be} (use ollama|queue|xai)",
    )
