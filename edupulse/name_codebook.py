"""Phonetic short-code codebook for staff names under Whisper's ~223-token budget.

Treats the Whisper ``initial_prompt`` as a rate-limited channel whose cost unit is
**BPE tokens**, not Shannon bits. Opaque binary codes are not viable (Whisper will
not emit ``0x4F`` when someone says "Yannett"). Instead we assign **constrained
shortest unique prefixes** (min length, prefix of the real spelling) that:

  1. Fit more names into the prompt budget
  2. Bias ASR toward spellings we can map
  3. Expand uniquely on the backend to canonical staff last names

See ``docs/name_codebook.md``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# Hand / observed ASR confusions → canonical last name (lowercase).
# Merged into every codebook's decode map.
HAND_ASR_ALIASES: dict[str, str] = {
    "mays": "mayes",
    "mayse": "mayes",
    "maze": "mayes",
    "mase": "mayes",
    "mason": "mayes",
    "broom": "broome",
    "stricklan": "strickland",
    "stricklin": "strickland",
    "yannette": "yannett",
    "yanette": "yannett",
    "yanett": "yannett",
    "deannette": "yannett",
    "deanette": "yannett",
    "annette": "yannett",
    "annett": "yannett",
    "richar": "richar",
    "richard": "richar",
    "rochard": "richar",
    "rashar": "richar",

}

DEFAULT_MIN_CHARS = 4


def _staff_last_name(full_name: str) -> str:
    parts = [p for p in full_name.strip().split() if p]
    return parts[-1] if parts else ""


def _bpe_cost(text: str, tokenizer=None) -> int:
    if tokenizer is not None:
        try:
            from edupulse.whisper_prompt_budget import measure_prompt

            return measure_prompt(text, tokenizer=tokenizer).tokens
        except Exception:
            pass
    # Heuristic fallback (no model loaded)
    return max(1, (len(text) + 2) // 3)


@dataclass
class CodebookEntry:
    last_name: str
    prompt_alias: str
    decode_keys: list[str]
    bpe_full: int
    bpe_alias: int
    staff_lines: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "last_name": self.last_name,
            "prompt_alias": self.prompt_alias,
            "decode_keys": list(self.decode_keys),
            "bpe_full": self.bpe_full,
            "bpe_alias": self.bpe_alias,
            "staff_lines": list(self.staff_lines),
        }


@dataclass
class NameCodebook:
    """Uniquely decodable phonetic aliases for staff last names."""

    entries: list[CodebookEntry]
    min_chars: int = DEFAULT_MIN_CHARS
    meta: dict[str, Any] = field(default_factory=dict)

    def decode_map(self) -> dict[str, str]:
        """alias/variant (lowercase) → canonical last name (lowercase)."""
        out = dict(HAND_ASR_ALIASES)
        for e in self.entries:
            canon = e.last_name.lower()
            out[canon] = canon
            out[e.prompt_alias.lower()] = canon
            for k in e.decode_keys:
                out[k.lower()] = canon
        return out

    def prompt_aliases(self, hot_lasts: Iterable[str] | None = None) -> list[str]:
        """Ordered aliases for the fingerprint (hot lasts first, then the rest)."""
        hot = {h.lower() for h in (hot_lasts or [])}
        hot_aliases: list[str] = []
        rest: list[str] = []
        for e in self.entries:
            if e.last_name.lower() in hot:
                hot_aliases.append(e.prompt_alias)
            else:
                rest.append(e.prompt_alias)
        # stable: hot in hot-set order preference already via entries sort; keep sorted rest
        return hot_aliases + rest

    def normalize_token(self, tok: str) -> str:
        t = tok.lower().strip(" .,!'")
        return self.decode_map().get(t, t)

    def metrics(self) -> dict[str, Any]:
        n = len(self.entries)
        full = sum(e.bpe_full for e in self.entries)
        alias = sum(e.bpe_alias for e in self.entries)
        return {
            "n_last_names": n,
            "bpe_sum_full": full,
            "bpe_sum_alias": alias,
            "bpe_saved": full - alias,
            "shannon_bits_uniform": round(math.log2(n), 3) if n else 0.0,
            "min_chars": self.min_chars,
            **self.meta,
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "min_chars": self.min_chars,
            "meta": self.meta,
            "metrics": self.metrics(),
            "entries": [e.as_dict() for e in self.entries],
        }

    def save(self, path: str | Path) -> Path:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")
        return p

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "NameCodebook":
        entries = [
            CodebookEntry(
                last_name=e["last_name"],
                prompt_alias=e["prompt_alias"],
                decode_keys=list(e.get("decode_keys") or []),
                bpe_full=int(e.get("bpe_full") or 0),
                bpe_alias=int(e.get("bpe_alias") or 0),
                staff_lines=list(e.get("staff_lines") or []),
            )
            for e in data.get("entries") or []
        ]
        return cls(
            entries=entries,
            min_chars=int(data.get("min_chars") or DEFAULT_MIN_CHARS),
            meta=dict(data.get("meta") or {}),
        )

    @classmethod
    def load(cls, path: str | Path) -> "NameCodebook":
        return cls.from_json(json.loads(Path(path).expanduser().read_text(encoding="utf-8")))


def _unique_prefix(last: str, all_lasts: list[str], min_chars: int) -> str:
    """Shortest prefix of `last` with length ≥ min_chars that no other last shares."""
    low = last.lower()
    others = [o for o in all_lasts if o.lower() != low]
    for k in range(min(min_chars, len(last)), len(last) + 1):
        pref = last[:k]
        plow = pref.lower()
        if any(o.lower().startswith(plow) for o in others):
            continue
        return pref
    return last


def _min_bpe_unique_prefix(
    last: str,
    all_lasts: list[str],
    min_chars: int,
    tokenizer=None,
) -> tuple[str, int, int]:
    """Among unique prefixes ≥ min_chars, pick minimum BPE cost (tie → longer/closer)."""
    low = last.lower()
    others = [o for o in all_lasts if o.lower() != low]
    candidates: list[tuple[int, int, str]] = []  # (bpe, -len, prefix)
    full_cost = _bpe_cost(last, tokenizer)
    for k in range(min(min_chars, len(last)), len(last) + 1):
        pref = last[:k]
        plow = pref.lower()
        if any(o.lower().startswith(plow) for o in others):
            continue
        cost = _bpe_cost(pref, tokenizer)
        candidates.append((cost, -k, pref))
    if not candidates:
        return last, full_cost, full_cost
    candidates.sort()
    best = candidates[0][2]
    return best, full_cost, _bpe_cost(best, tokenizer)


def build_name_codebook(
    known_staff: list[str],
    min_chars: int = DEFAULT_MIN_CHARS,
    tokenizer=None,
) -> NameCodebook:
    """Build a phonetic short-code codebook from Title First Last staff lines."""
    clean = [n for n in known_staff if n and n.strip() and not n.strip().startswith("#")]
    by_last: dict[str, list[str]] = {}
    for line in clean:
        last = _staff_last_name(line)
        if not last:
            continue
        by_last.setdefault(last, []).append(line)

    all_lasts = sorted(by_last.keys(), key=lambda s: s.lower())

    # Load tokenizer once if possible (exact BPE costs).
    if tokenizer is None:
        try:
            from edupulse.whisper_prompt_budget import get_whisper_tokenizer

            tokenizer = get_whisper_tokenizer()
        except Exception:
            tokenizer = None

    entries: list[CodebookEntry] = []
    for last in all_lasts:
        alias, bpe_full, bpe_alias = _min_bpe_unique_prefix(
            last, all_lasts, min_chars=min_chars, tokenizer=tokenizer
        )
        keys = {last.lower(), alias.lower()}
        # Pull hand aliases that target this last
        for alias_k, canon in HAND_ASR_ALIASES.items():
            if canon == last.lower():
                keys.add(alias_k)
        # Also add a few intermediate prefixes as decode keys (robustness)
        for k in range(min_chars, len(last) + 1):
            keys.add(last[:k].lower())
        entries.append(
            CodebookEntry(
                last_name=last,
                prompt_alias=alias,
                decode_keys=sorted(keys),
                bpe_full=bpe_full,
                bpe_alias=bpe_alias,
                staff_lines=list(by_last[last]),
            )
        )

    cb = NameCodebook(
        entries=entries,
        min_chars=min_chars,
        meta={"tokenizer": "whisper" if tokenizer is not None else "heuristic"},
    )
    return cb


# Process-wide codebook for resolver integration (set when building the live prompt).
_ACTIVE: NameCodebook | None = None


def set_active_codebook(cb: NameCodebook | None) -> None:
    global _ACTIVE
    _ACTIVE = cb


def get_active_codebook() -> NameCodebook | None:
    return _ACTIVE


def normalize_with_codebook(tok: str) -> str | None:
    """Return canonical last name if codebook (or hand aliases) know this token."""
    t = tok.lower().strip(" .,!'")
    if not t:
        return None
    if t in HAND_ASR_ALIASES:
        return HAND_ASR_ALIASES[t]
    if _ACTIVE is not None:
        mapped = _ACTIVE.decode_map().get(t)
        if mapped:
            return mapped
    return None


# Lowercase English words that collide with short aliases — only expand if capitalized.
_EXPAND_AMBIGUOUS_ENGLISH = frozenset(
    {
        "may",
        "maybe",
        "fund",
        "bright",
        "horn",
        "hill",
        "ford",
        "gill",
        "barr",
        "bern",
        "davis",
        "johns",
        "sale",
        "pass",
        "mark",
        "will",
        "rich",
    }
)


def expand_transcript_names(
    text: str,
    codebook: NameCodebook | None = None,
) -> tuple[str, str]:
    """Expand phonetic codes / ASR aliases to canonical last names for display.

    Returns ``(display_text, raw_text)``.

    Codes belong in the Whisper *prompt* only. Terminal printout and sidecar
    ``transcription`` should show real staff last names (e.g. ``Yannett``, not
    ``Yanne``). Ambiguous lowercase English (``fund``, ``bright``) is left alone
    unless capitalized like a name.
    """
    import re

    raw = text or ""
    cb = codebook if codebook is not None else get_active_codebook()
    if not raw.strip():
        return raw, raw

    # key(lower) -> canonical Last Name spelling from staff list
    key_to_last: dict[str, str] = {}
    if cb is not None:
        for e in cb.entries:
            key_to_last[e.last_name.lower()] = e.last_name
            key_to_last[e.prompt_alias.lower()] = e.last_name
            for k in e.decode_keys:
                if len(k) >= 3:
                    key_to_last[k.lower()] = e.last_name
    for alias, canon_last in HAND_ASR_ALIASES.items():
        if cb is not None:
            for e in cb.entries:
                if e.last_name.lower() == canon_last:
                    key_to_last[alias] = e.last_name
                    break
        else:
            key_to_last[alias] = canon_last.title()

    if not key_to_last:
        return raw, raw

    keys = sorted(key_to_last.keys(), key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b", re.IGNORECASE)

    def _repl(m: re.Match[str]) -> str:
        word = m.group(0)
        key = word.lower()
        canon = key_to_last.get(key)
        if not canon:
            return word
        if key in _EXPAND_AMBIGUOUS_ENGLISH and word[:1].islower():
            return word
        # Already canonical spelling
        if word == canon or word.lower() == canon.lower():
            return canon
        return canon

    display = pattern.sub(_repl, raw)
    return display, raw
