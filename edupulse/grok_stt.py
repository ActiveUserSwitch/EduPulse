"""Transcribe WAV files via the same xAI STT stack as Grok Build voice dictation.

Spacebar / Ctrl+Space in the TUI captures mic audio and POSTs it to xAI speech-to-text.
This module does the same for an on-disk ``.wav`` using your Grok Build OIDC token from
``~/.grok/auth.json`` (no separate ``XAI_API_KEY`` required for that auth path).

Endpoint: ``POST https://api.x.ai/v1/stt`` (model ``grok-stt``).

Keyterms (``keyterm`` form field, max 100 × ≤50 chars) bias proper-noun orthography —
feed ``radio_staff.txt`` so school radio names compete with "deli" / "Franklin".

Implementation note: repeated ``keyterm`` fields must be sent via ``requests`` multipart
(list-of-tuples ``data=``). Plain ``curl -F keyterm=...`` was observed to be ignored
by the API in A/B tests (2026-09-04 captures).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests

STT_URL = "https://api.x.ai/v1/stt"
DEFAULT_AUTH = Path.home() / ".grok" / "auth.json"
MAX_KEYTERMS = 100
MAX_KEYTERM_CHARS = 50

# Short radio carriers / titles that show up on-air (not full staff lines).
# Keep this short — lone titles can over-bias (e.g. Captain+Marvel → "Captain Marvel").
_RADIO_CARRIERS = (
    "Go for",
    "Office",
    "10-4",
)

# Roster title ≠ on-air form. Add explicit aliases (still ≤50 chars).
_ON_AIR_ALIASES = (
    "Coach Erdelyi",
    "Sergeant Marvel",
    "Coach Richar",
)


@dataclass
class SttResult:
    text: str
    language: str | None = None
    duration: float | None = None
    raw: dict[str, Any] | None = None
    error: str | None = None
    keyterms_used: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_grok_build_token(auth_path: Path | None = None) -> str:
    path = (auth_path or DEFAULT_AUTH).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Grok Build auth not found: {path} (run: grok login)")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise RuntimeError(f"Unexpected auth.json shape in {path}")
    entry = next(iter(data.values()))
    token = entry.get("key") or entry.get("access_token")
    if not token:
        raise RuntimeError("No OIDC access token in auth.json — run: grok login")
    return str(token)


def _default_radio_staff_path() -> Path:
    return Path(__file__).resolve().parents[1] / "hardware" / "capture" / "radio_staff.txt"


def load_radio_staff_lines(path: Path | None = None) -> list[str]:
    p = (path or _default_radio_staff_path()).expanduser()
    if not p.is_file():
        return []
    out: list[str] = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def build_stt_keyterms(
    staff_lines: Sequence[str] | None = None,
    *,
    extra: Iterable[str] | None = None,
    include_carriers: bool = True,
    max_terms: int = MAX_KEYTERMS,
) -> list[str]:
    """Pack radio-staff names into Grok STT keyterms (≤100, each ≤50 chars).

    Prefers full ``Title First Last`` lines, then Title+Last and bare lasts so
    short on-air forms like ``Coach Erdelyi`` still bias.
    """
    lines = list(staff_lines) if staff_lines is not None else load_radio_staff_lines()
    seen: set[str] = set()
    ordered: list[str] = []

    def _add(term: str) -> None:
        t = " ".join(term.split())
        if not t or len(t) > MAX_KEYTERM_CHARS:
            return
        key = t.casefold()
        if key in seen:
            return
        seen.add(key)
        ordered.append(t)

    # Aliases first — on-air forms that differ from roster titles.
    for alias in _ON_AIR_ALIASES:
        _add(alias)

    # Title + Last (readable, matches Whisper fingerprint style). Skip bloating
    # with full First names; those dilute keyterm bias on short radio clips.
    for line in lines:
        parts = line.split()
        if len(parts) >= 2:
            _add(f"{parts[0]} {parts[-1]}")
        elif parts:
            _add(parts[0])

    for line in lines:
        parts = line.split()
        if parts:
            _add(parts[-1])

    # Keep full roster lines if budget remains (rare with 28 staff).
    for line in lines:
        _add(line)

    if include_carriers:
        for c in _RADIO_CARRIERS:
            _add(c)

    if extra:
        for e in extra:
            _add(str(e))

    return ordered[: max(0, max_terms)]


def transcribe_wav(
    wav_path: str | Path,
    *,
    language: str = "en",
    token: str | None = None,
    timeout_sec: int = 120,
    keyterms: Sequence[str] | None = None,
    use_radio_staff_keyterms: bool = True,
    radio_staff_path: Path | None = None,
) -> SttResult:
    """Send a WAV to Grok STT (same family as TUI voice dictation).

    When ``keyterms`` is None and ``use_radio_staff_keyterms`` is True, loads
    ``hardware/capture/radio_staff.txt`` and passes each name as a ``keyterm``.
    Pass ``keyterms=[]`` or ``use_radio_staff_keyterms=False`` for an unbiased baseline.
    """
    wav = Path(wav_path).expanduser().resolve()
    if not wav.is_file():
        return SttResult(text="", error=f"missing wav: {wav}")

    try:
        tok = token or load_grok_build_token()
    except Exception as e:
        return SttResult(text="", error=str(e))

    if keyterms is not None:
        terms = build_stt_keyterms([], extra=keyterms, include_carriers=False)
    elif use_radio_staff_keyterms:
        terms = build_stt_keyterms(load_radio_staff_lines(radio_staff_path))
    else:
        terms = []

    form_data: list[tuple[str, str]] = [("language", language)]
    for term in terms:
        form_data.append(("keyterm", term))

    try:
        with wav.open("rb") as fh:
            resp = requests.post(
                STT_URL,
                headers={"Authorization": f"Bearer {tok}"},
                files={"file": (wav.name, fh, "audio/wav")},
                data=form_data,
                timeout=timeout_sec,
            )
    except Exception as e:
        return SttResult(text="", error=str(e), keyterms_used=terms)

    try:
        data = resp.json()
    except Exception:
        return SttResult(
            text="",
            error=f"http_{resp.status_code}: {resp.text[:500]}",
            keyterms_used=terms,
        )

    if resp.status_code >= 400:
        return SttResult(
            text="",
            error=f"http_{resp.status_code}: {data if isinstance(data, dict) else resp.text[:500]}",
            raw=data if isinstance(data, dict) else None,
            keyterms_used=terms,
        )

    if isinstance(data, dict) and data.get("code") and not data.get("text"):
        return SttResult(text="", error=str(data), raw=data, keyterms_used=terms)

    text = (data.get("text") or "").strip() if isinstance(data, dict) else ""
    return SttResult(
        text=text,
        language=(data.get("language") if isinstance(data, dict) else None),
        duration=(data.get("duration") if isinstance(data, dict) else None),
        raw=data if isinstance(data, dict) else None,
        keyterms_used=terms,
    )
