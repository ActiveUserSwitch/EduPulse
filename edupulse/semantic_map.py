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


def infer_likely_speaker(text: str, known_staff: list[str] | None = None) -> tuple[str | None, str]:
    """Try to guess who is *speaking* (not who is being addressed) from the transcript.

    This is deliberately conservative because of school radio protocol:
    Most calls are in the form "Receiver, this is Caller" or "Mr. X to Dr. Y".
    The names you hear are often the *person being called*, not the person talking.

    Strong self-identification (high confidence):
        - "Go for X", "This is X", "X here", "X speaking", "Yeah, Strickland."

    Weaker heuristic (medium/low confidence):
        - In "A to B" style calls, the first named staff member is often the caller/speaker.
        - Still risky; voice embedding should be the tie-breaker.

    Returns: (best_guess_name or None, confidence_level)
        confidence_level is one of: "strong", "weak", "none"
    """
    if not text or not known_staff:
        return None, "none"

    t = text.lower()

    # 1. Strong self-identification patterns (speaker is naming themselves)
    strong_patterns = [
        r"go for\s+([a-z][a-z\s\.]+)",
        r"this is\s+([a-z][a-z\s\.]+)",
        r"\bhere\b.*([a-z][a-z\s\.]+)",
        r"([a-z][a-z\s\.]+)\s+(here|speaking)",
        r"yeah[, ]+([a-z][a-z\s\.]+)",
    ]

    for pat in strong_patterns:
        import re as _re
        m = _re.search(pat, t)
        if m:
            candidate = m.group(1).strip(" .,")
            # Try to resolve the captured phrase against known staff (last name or full)
            for staff in known_staff:
                staff_l = staff.lower()
                if candidate in staff_l or staff_l.split()[-1] in candidate:
                    return staff, "strong"

    # 2. "A to B" / call initiation style — first named staff is often the *caller* (speaker)
    #    This is the common pattern the user described.
    #    We treat it as weak evidence only.
    call_style = _re.search(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(to|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text
    )
    if call_style:
        first = call_style.group(1)
        # Resolve first name against known staff by last name (most reliable)
        first_l = first.lower()
        for staff in known_staff:
            if staff.lower().split()[-1] in first_l or first_l in staff.lower():
                return staff, "weak"

    # 3. Fallback: if there's exactly one strong self-mention we already caught via extract,
    #    but we didn't hit a pattern above, be honest and say we don't know.
    return None, "none"
