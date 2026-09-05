"""Post-hoc co-occurrence semantic map and speaker-from-text heuristics."""
from __future__ import annotations

import re
from typing import Any

from .incidents import extract_staff_mentions

def build_radio_semantic_map(
    transcripts_with_meta: list[dict],
    known_staff: list[str] | None = None,
    min_cooc: int = 1,
) -> dict:
    """Build a post-hoc semantic map from accumulated radio traffic data.

    Input: list of dicts, each with at least:
        "text": str (the large-v3 or human transcript)
        "acoustic": dict (optional, from pyannote features)
        "critical": bool (optional, e.g. fight report bookmark)
        "speaker": str | None
        "tx": str (for traceability)

    This function is *deliberately* only for post-accumulation analysis.
    It is never called during live recording, transcription, or prompting.
    The resulting map (nodes + co-occurrence edges) is excellent raw material
    for dissertation work on school radio as institutional discourse:
    - staff-location semantic fields
    - lexical + prosodic markers of urgency (layer acoustic_features)
    - protocol response pairs ("10-4" + "on my way")
    - crisis language clusters seeded from bookmarked events

    Returns a JSON-serializable graph dict.
    """
    if not transcripts_with_meta:
        return {"nodes": [], "edges": [], "meta": {"total": 0}}

    from collections import Counter
    nodes: Counter[str] = Counter()
    edges: Counter[tuple[str, str]] = Counter()
    critical_nodes: Counter[str] = Counter()
    critical_edges: Counter[tuple[str, str]] = Counter()

    staff = known_staff or []
    staff_lower = {s.lower() for s in staff}

    location_seeds = {"media center", "hallway", "classroom", "gym", "500", "bio", "office", "nurse"}
    event_seeds = {"fighting", "fight", "administrator", "admin", "backup", "nurse", "emergency", "need admin"}
    protocol_seeds = {"10-4", "go for", "on my way", "thank you", "i'll be right there", "copy"}

    all_seeds = staff_lower | location_seeds | event_seeds | protocol_seeds

    def _extract(text: str) -> set[str]:
        ents: set[str] = set()
        t = text.lower()
        for s in extract_staff_mentions(t, staff):
            ents.add(s.lower())
        for seed in location_seeds | event_seeds | protocol_seeds:
            if seed in t:
                ents.add(seed)
        # bare last names
        for last in {s.split()[-1].lower() for s in staff if len(s.split()) > 1}:
            if re.search(r"\b" + re.escape(last) + r"\b", t):
                ents.add(last)
        return ents

    for item in transcripts_with_meta:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        ents = _extract(text)
        if len(ents) < 2:
            continue
        is_crit = bool(item.get("critical"))
        for e in ents:
            nodes[e] += 1
            if is_crit:
                critical_nodes[e] += 1
        for a in ents:
            for b in ents:
                if a < b:
                    edges[(a, b)] += 1
                    if is_crit:
                        critical_edges[(a, b)] += 1

    node_list = [
        {"term": t, "count": c, "critical_count": critical_nodes.get(t, 0)}
        for t, c in nodes.most_common()
    ]
    edge_list = [
        {"a": a, "b": b, "count": c, "critical_count": critical_edges.get((a, b), 0)}
        for (a, b), c in edges.most_common()
        if c >= min_cooc
    ]

    return {
        "nodes": node_list,
        "edges": edge_list,
        "meta": {
            "total_transcripts_processed": len(transcripts_with_meta),
            "unique_entities": len(nodes),
            "unique_associations": len(edges),
            "note": "Post-accumulation only. Built from heavy-model + human gold transcripts. Not used for recognition, transcription, prompting, or real-time categorization. Rich source for dissertation work on radio as institutional communication, crisis signaling, and distributed leadership.",
        },
    }


_NAME_STOPWORDS = frozenset(
    {
        "go",
        "for",
        "to",
        "the",
        "a",
        "an",
        "and",
        "or",
        "yeah",
        "yes",
        "no",
        "hey",
        "hi",
        "ok",
        "okay",
        "copy",
        "here",
        "this",
        "is",
        "please",
        "will",
        "you",
        "me",
        "my",
        "your",
        "ahead",
        "ten",
        "four",
    }
)

# Common Whisper / radio nicknames → last-name keys matched against staff_names.txt.
# Kept in sync with edupulse.name_codebook.HAND_ASR_ALIASES (codebook is source of truth
# when active; this table remains for resolver use before/without a codebook).
from edupulse.name_codebook import HAND_ASR_ALIASES as _ASR_ALIASES  # noqa: E402
from edupulse.name_codebook import normalize_with_codebook  # noqa: E402


def _normalize_alias_token(tok: str) -> str:
    t = tok.lower().strip(" .,!'")
    mapped = normalize_with_codebook(t)
    if mapped:
        return mapped
    return _ASR_ALIASES.get(t, t)


_MALE_TITLES = frozenset({"mr", "mister", "captain", "coach", "sergeant", "deputy", "officer"})
_FEMALE_TITLES = frozenset({"ms", "mrs", "miss", "mistress"})
# Coach can be either; don't hard-filter on coach alone unless sexed title also present


def _extract_title_hint(candidate: str) -> str | None:
    """Return 'male' | 'female' | None from an honorific in the candidate string."""
    raw = candidate.lower().replace(".", " ")
    toks = raw.split()
    if not toks:
        return None
    t0 = toks[0]
    if t0 in _MALE_TITLES:
        return "male"
    if t0 in _FEMALE_TITLES:
        return "female"
    return None


def _staff_title_sex(staff: str) -> str | None:
    raw = staff.lower().replace(".", " ").split()
    if not raw:
        return None
    t0 = raw[0]
    if t0 in _MALE_TITLES:
        return "male"
    if t0 in _FEMALE_TITLES or t0 == "dr":
        # Dr. is ambiguous; don't sex-filter
        return None if t0 == "dr" else "female"
    return None


def _resolve_staff_mention(candidate: str, known_staff: list[str]) -> str | None:
    """Map a free-text name fragment to a known staff line (Title First Last).

    Title-aware: "Mr. Chandler" prefers Mr./Captain Chandler over Ms. Chandler.
    """
    title_sex = _extract_title_hint(candidate)
    cand = candidate.strip(" .,!?").lower()
    if not cand or len(cand) < 3:
        return None
    # Drop leading stopwords ("go broome" should not start with go)
    parts_c = [
        _normalize_alias_token(p)
        for p in cand.replace(".", " ").split()
        if p and p not in _NAME_STOPWORDS and p not in _MALE_TITLES and p not in _FEMALE_TITLES
        and p != "dr"
    ]
    parts_c = [p for p in parts_c if p and p not in _NAME_STOPWORDS]
    if not parts_c:
        return None
    cand = " ".join(parts_c)
    if cand in _NAME_STOPWORDS or len(cand) < 3:
        return None
    # Prefer longer / more specific staff matches; boost title-sex agreement
    hits: list[tuple[int, int, str]] = []  # (sex_boost, length, staff)
    for staff in known_staff:
        if staff.strip().startswith("#"):
            continue
        staff_l = staff.lower()
        parts = [_normalize_alias_token(p) for p in staff_l.replace(".", "").split()]
        # drop title token from parts for matching
        name_parts = [
            p for p in parts
            if p not in _MALE_TITLES and p not in _FEMALE_TITLES and p != "dr"
        ]
        last = name_parts[-1] if name_parts else ""
        if len(last) < 3:
            continue
        matched = False
        if cand == " ".join(name_parts) or cand in " ".join(name_parts):
            matched = True
        elif last and (cand == last or cand.endswith(" " + last) or last in parts_c):
            matched = True
        elif any(p == cand for p in name_parts if len(p) > 2 and p not in _NAME_STOPWORDS):
            matched = True
        if not matched:
            continue
        sex = _staff_title_sex(staff)
        # If caller said Mr./Ms., require agreeing sex when staff title is sexed
        if title_sex and sex and title_sex != sex:
            continue
        sex_boost = 2 if (title_sex and sex and title_sex == sex) else (1 if not title_sex else 0)
        # Prefer exact "Mr. Chandler" style short entries when title matches
        hits.append((sex_boost, len(staff), staff))
    if not hits:
        return None
    # Last-name-only + both Mr. and Ms. Chandler → refuse to guess (avoid wrong enroll)
    if not title_sex and len(parts_c) == 1:
        sexes = set()
        for boost, _ln, staff in hits:
            sx = _staff_title_sex(staff)
            if sx:
                sexes.add(sx)
        if len(sexes) > 1:
            return None
    hits.sort(reverse=True)
    return hits[0][2]


def is_generic_radio_ack(text: str) -> bool:
    """True for short answer-style PTT with little content (go ahead / copy / 10-4).

    "Go for Mayes" is NOT generic — that is a named self-ID.
    """
    import re as _re

    if not text:
        return False
    t = text.lower().strip()
    t = _re.sub(r"[^a-z0-9\s]", " ", t)
    t = _re.sub(r"\s+", " ", t).strip()
    if len(t) > 48:
        return False
    if _re.fullmatch(
        r"(go ahead|go for me|go for it|copy|copy that|10 4|ten four|affirmative|yes|yeah|ok|okay|thanks|thank you)",
        t,
    ):
        return True
    # Bare "go for" / "go ahead" with no real name token
    m = _re.match(r"^go for\s+(.+)$", t)
    if m:
        rest = m.group(1).strip()
        if rest in {"me", "it", "you", "that"} or len(rest) < 3:
            return True
        return False  # "go for mays" etc. — named self-ID
    if _re.match(r"^(go ahead|copy|10 4|ten four)\b", t) and len(t.split()) <= 4:
        return True
    return False

def parse_radio_call(text: str, known_staff: list[str] | None = None) -> dict:
    """Parse school PTT protocol roles from a transcript.

    Typical sequence (gold standard):
      1) "Name1 to Name2"     → Name1 speaking; expect Name2 next
      2) "Go for Name2" / "Go ahead" → Name2 speaking (answer)

    Also: "Mr. Name2, what's your location?" addresses Name2 → expect Name2 next.

    Returns keys:
      caller, callee, addressed, self_id
      expect_next_speaker  (who should answer on the following TX)
      likely_speaker, likely_speaker_conf
      enrollments: list[{name, reason, weight}]
        reasons: self_id (1.0), caller_protocol (0.75), …
      is_generic_ack
    """
    import re as _re

    out: dict = {
        "caller": None,
        "callee": None,
        "addressed": None,
        "self_id": None,
        "expect_next_speaker": None,
        "likely_speaker": None,
        "likely_speaker_conf": "none",
        "enrollments": [],
        "is_generic_ack": is_generic_radio_ack(text or ""),
    }
    if not text or not known_staff:
        return out

    t = text.lower()
    title = (
        r"(?:captain|coach|nurse|sergeant|deputy|officer|dr\.|mr\.|ms\.|mrs\.|miss)?"
    )
    name_bit = rf"{title}\s*[a-z][a-z']+(?:\s+[a-z][a-z']+)?"

    def _add_enroll(name: str, reason: str, weight: float) -> None:
        if not name:
            return
        if any(e["name"] == name and e["reason"] == reason for e in out["enrollments"]):
            return
        out["enrollments"].append({"name": name, "reason": reason, "weight": weight})

    # --- Self-ID (answer / go-for Name) — gold when it matches expected callee ---
    strong_patterns = [
        rf"go for\s+({name_bit})",
        rf"this is\s+({name_bit})",
        rf"({name_bit})\s+(?:here|speaking)\b",
        rf"yeah[, ]+({name_bit})",
    ]
    for pat in strong_patterns:
        m = _re.search(pat, t)
        if m:
            resolved = _resolve_staff_mention(m.group(1), known_staff)
            if resolved:
                out["self_id"] = resolved
                out["likely_speaker"] = resolved
                out["likely_speaker_conf"] = "strong"
                _add_enroll(resolved, "self_id", 1.0)
                break

    # --- "Name1 to/for Name2" call initiation ---
    # Do NOT treat "go for X" / "this is X" as A-to-B (those are self-ID).
    if not _re.match(r"^\s*(?:go\s+for|this\s+is)\b", t):
        call = _re.search(
            rf"({name_bit})\s+(?:to|for)\s+({name_bit})",
            t,
        )
        if call:
            left, right = call.group(1), call.group(2)
            if left.strip().lower() not in _NAME_STOPWORDS and not left.strip().lower().startswith("go "):
                caller = _resolve_staff_mention(left, known_staff)
                callee = _resolve_staff_mention(right, known_staff)
                out["caller"] = caller
                out["callee"] = callee
                if callee:
                    out["expect_next_speaker"] = callee
                if caller:
                    if out["likely_speaker"] is None:
                        out["likely_speaker"] = caller
                        out["likely_speaker_conf"] = "protocol"
                    _add_enroll(caller, "caller_protocol", 0.75)

        if out["caller"] is None and out["callee"] is None:
            call2 = _re.search(
                r"((?:Captain|Coach|Nurse|Sergeant|Deputy|Officer|Dr\.|Mr\.|Ms\.|Mrs\.)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
                r"\s+(?:to|for)\s+"
                r"((?:Captain|Coach|Nurse|Sergeant|Deputy|Officer|Dr\.|Mr\.|Ms\.|Mrs\.)?\s*[A-Z][a-z]+)",
                text,
            )
            if call2:
                caller = _resolve_staff_mention(call2.group(1), known_staff)
                callee = _resolve_staff_mention(call2.group(2), known_staff)
                out["caller"] = caller
                out["callee"] = callee
                if callee:
                    out["expect_next_speaker"] = callee
                if caller and out["likely_speaker"] is None:
                    out["likely_speaker"] = caller
                    out["likely_speaker_conf"] = "protocol"
                    _add_enroll(caller, "caller_protocol", 0.75)

        # Vocative address: "Mr. Mays, what's your location?" → expect Mays next
        if out["expect_next_speaker"] is None:
            voc = _re.match(
                rf"^\s*({name_bit})\s*[,:]+\s+\S",
                t,
            )
            if voc:
                addressed = _resolve_staff_mention(voc.group(1), known_staff)
                if addressed:
                    out["addressed"] = addressed
                    out["expect_next_speaker"] = addressed

    return out


def infer_likely_speaker(text: str, known_staff: list[str] | None = None) -> tuple[str | None, str]:
    """Try to guess who is *speaking* (not who is being addressed) from the transcript.

    Prefer :func:`parse_radio_call` when you also need callee / enrollment hints.

    Returns: (best_guess_name or None, confidence_level)
        confidence_level is one of: "strong", "protocol", "weak", "none"
    """
    parsed = parse_radio_call(text, known_staff)
    conf = parsed["likely_speaker_conf"]
    # Map protocol → weak for older callers that only expect strong/weak/none
    if conf == "protocol":
        conf = "weak"
    return parsed["likely_speaker"], conf
