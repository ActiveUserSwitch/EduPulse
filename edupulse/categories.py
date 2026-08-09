"""Transmission categorization, noise heuristics, and Whisper fingerprint prompts."""
from __future__ import annotations

import re
from typing import Any

TRANSMISSION_CATEGORIES: dict[str, list[str]] = {
    "Discipline (Student Conflict, Defiance, etc.)": [
        "fight", "fighting", "defiance", "defiant", "conflict", "argue", "arguing", "argument",
        "disrespect", "disobey", "disruption", "disruptive", "student conflict", "misbehave",
        "misbehavior", "detention", "suspension", "referral", "defiant student"
    ],
    "Request for Backup / Admin Support": [
        "backup", "admin support", "need admin", "request backup", "send admin", "principal",
        "assistant principal", "come to", "need help", "support", "admin", "request for backup"
    ],
    "Medical / Health Emergency": [
        "medical", "nurse", "injury", "hurt", "sick", "emergency", "health", "bleeding",
        "unconscious", "seizure", "allergic", "overdose", "faint", "chest pain", "breathing",
        "medical emergency", "health emergency"
    ],
    "Logistics / Movement / Hallway": [
        "hallway", "hall", "movement", "logistics", "class change", "passing period",
        "hall pass", "roam", "roaming", "in the hall", "hallway supervision", "student movement",
        "500", "headed to", "retake", "exam", "bio", "chromebook", "bathroom", "media center",
        "building", "room", "go to", "send to",
        "returning chromebook", "turn in chromebook", "chromebooks", "distributing chromebook",
        "test monitoring", "monitoring", "proctor", "finals", "final exam", "bio retake"
    ],
    "Parent / Visitor Issue": [
        "parent", "visitor", "mom", "dad", "guardian", "mother", "father", "parent in",
        "visitor in", "parent issue", "visitor issue", "parent conference"
    ],
    "Maintenance / Facilities": [
        "maintenance", "facilities", "broken", "leak", "light", "door", "lock", "janitor",
        "custodian", "repair", "plumbing", "electrical", "cleaning", "facility"
    ],
    "Student Relocation": [
        "relocate", "relocation", "move student", "student move", "go to room", "room change",
        "send to", "relocate student", "student relocation", "send student", "alternative classroom",
        "move to", "send them to", "relocate to"
    ],
    "Early Dismissal": [
        "early dismissal", "early release", "dismiss early", "early dismiss", "early dismissal",
        "for dismissal", "for early dismissal", "student for dismissal", "dismissal", "early pickup"
    ],
    "Student Walkouts": [
        "walkout", "walk out", "walkouts", "protest", "leaving school", "students leaving",
        "student walkout", "walk out of school"
    ],
    "Request for Information": [
        "information", "info", "what is", "where is", "need to know", "update", "status",
        "request information", "need info", "request for information", "for sure", "just a minute",
        "let me", "give me", "one moment", "check it"
    ],
    "Law Enforcement (Deputy, Officer Tyson, police involvement, etc.)": [
        "deputy", "officer tyson", "police", "sheriff", "law enforcement", "cop", "officer",
        "deputy sheriff", "trooper", "state police", "deputy", "police officer"
    ],
    "Testing (radio checks, mic checks, system tests, counting, etc.)": [
        "testing", "test", "radio check", "mic check", "check one", "check two", "1 2 3",
        "copy", "roger", "can you hear", "can you copy", "hello", "this is a test",
        "squelch", "counting", "one two three", "test test", "loud and clear", "weak",
        "how do you read", "read you", "over", "standing by",
        "test monitoring", "monitoring", "proctor", "finals monitoring"
    ],
    "Other / Unclear": [],
}


def _phrase_in_text(text: str, phrase: str) -> bool:
    """Rudimentary phrase match requiring consecutive words (prevents 'in the hall' matching 'in the hallway')."""
    # normalize to spaces only alnum+space
    t = " " + " ".join("".join(c if c.isalnum() or c.isspace() else " " for c in text.lower()).split()) + " "
    p = " " + " ".join(phrase.lower().split()) + " "
    return p in t


def categorize_transmission(text: str) -> dict[str, Any]:
    """
    Rudimentary categorization of a radio transmission transcript.

    Returns a dict with:
      - category: str (best match or "Other / Unclear")
      - confidence: float (0.0-1.0, very rough)
      - matched_keywords: list
    """
    if not text or not text.strip():
        return {"category": "Other / Unclear", "confidence": 0.0, "matched_keywords": []}

    scores: dict[str, int] = {}
    all_matched: dict[str, list[str]] = {}

    for category, keywords in TRANSMISSION_CATEGORIES.items():
        matched: list[str] = []
        score = 0
        for kw in keywords:
            if _phrase_in_text(text, kw):
                matched.append(kw)
                score += 1
        scores[category] = score
        all_matched[category] = matched

    max_score = max(scores.values()) if scores else 0

    if max_score == 0:
        return {"category": "Other / Unclear", "confidence": 0.0, "matched_keywords": []}

    # Pick the category with highest score (first one if tie, per dict order)
    best_category = max(scores, key=scores.get)  # type: ignore[arg-type]
    matched = all_matched[best_category]

    # Very rough confidence: more matches + longer text = higher
    # (this is intentionally simple)
    text_len = max(1, len(text.split()))
    conf = min(1.0, (max_score * 2) / max(3, text_len / 3))

    return {
        "category": best_category,
        "confidence": round(conf, 2),
        "matched_keywords": matched,
    }


def is_likely_noise(transcript: str, duration_sec: float, whisper_conf: float | None = None) -> bool:
    """Heuristic to detect Whisper hallucinations on radio static/squelch (common with tiny on noisy feeds).

    Used by capture tools and offline reprocessing to flag or skip bad segments for incident linking
    and categorization stats. We still keep the raw .wav for later heavier-model inspection.
    Short clear protocol ("Thank you", "Go for me?", "Hey I'm X") should NOT be treated as noise.
    """
    if not transcript or not transcript.strip():
        return True
    t = transcript.strip().lower()
    t_clean = ''.join(c for c in t if c.isalnum() or c.isspace()).strip()
    words = t.split()

    # Short segments that are basically just video sign-offs are almost always noise on radio tails.
    # Do this early, before the "very short keep them" guard.
    signoff_phrases = ["thanks for watching", "thank you for watching", "thank you for watching!"]
    if duration_sec < 3.5 and any(p in t_clean for p in signoff_phrases):
        return True

    # Very short transmissions are almost never the long repetitive hallucinations — keep them
    # (but we already handled the common sign-off case above)
    if duration_sec < 1.5 or len(words) <= 4:
        return False

    # Very repetitive output (the "I'm sorry...", "1, 2, 3, 4, 5...", "... ... ..." loops seen in real run)
    if len(words) >= 6:
        uniq_ratio = len(set(words)) / len(words)
        if uniq_ratio < 0.22:
            return True

    # Known hallucination patterns observed on this hardware + tiny model (June 3/4/5 runs)
    # Includes video sign-offs that Whisper loves to add on short/low-SNR radio tails.
    halluc_markers = [
        "i'm sorry", "this is the first time i've seen this", "in the next video",
        "i don't know what you're talking about", "i'm going to take a look at what i'm going to do",
        "1, 2, 3, 4, 5, 5, 5", "… … …", "... ... ...",
        "thanks for watching", "thank you for watching", "like and subscribe",
        "end of the video", "that's all for today", "see you next time",
    ]
    if any(m in t or m in t_clean for m in halluc_markers):
        return True

    # Long max-length segment that is mostly dots or very low lexical variety
    if duration_sec >= 25 and ("..." in transcript or "…" in transcript or len(set(words)) < 5):
        return True

    return False


def build_enhanced_initial_prompt(
    base: str | None = None,
    known_staff: list[str] | None = None,
    common_words: list[str] | None = None,
    extra_context: str | None = None,
) -> str:
    """Build a Whisper initial_prompt that includes a 'fingerprint' of the school radio environment.

    This helps the model with domain terms, staff names (for better recognition of roles),
    and common broadcast vocabulary (e.g. "chromebook", "test monitoring", building numbers,
    exam logistics phrases, etc.).

    Used by record_with_transcribe.py (and can be used in test scripts) when the user
    provides lists of teaching staff full names and/or most common radio words.
    """
    base = base or (
        "School administrative radio traffic, logistics, dismissals, hallway movement, "
        "staff roles (Mr, Mrs, Coach, Nurse, Officer, etc.):"
    )
    parts = [base.strip()]

    if known_staff:
        # Limit to avoid making prompt too long; Whisper prompt is best when concise but specific.
        staff_list = ", ".join(sorted(set(known_staff))[:25])
        parts.append(f"Known staff and roles include: {staff_list}.")

    if common_words:
        vocab = ", ".join(sorted(set(w.lower() for w in common_words if w.strip()))[:40])
        parts.append(f"Frequent terms on this channel: {vocab}.")

    if extra_context:
        parts.append(extra_context.strip())

    return " ".join(p for p in parts if p).strip()

