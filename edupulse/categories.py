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
    "Emergency Drill (Fire, Lockdown, Tornado, etc.)": [
        "fire drill", "lockdown drill", "tornado drill", "emergency drill", "drill",
        "evacuate", "evacuation", "shelter in place", "lockdown", "secure the building",
        "pull the alarm", "fire alarm", "alarm", "all clear", "return to class",
        "danger zone", "staging area", "accountability",
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


def _staff_title_last(full_name: str) -> str:
    """Compress 'Ms. Cheryl Yannett' → 'Ms. Yannett' (keep 2-token lines as-is)."""
    parts = [p for p in full_name.strip().split() if p]
    if len(parts) <= 2:
        return " ".join(parts)
    return f"{parts[0]} {parts[-1]}"


def _staff_last_name(full_name: str) -> str:
    parts = [p for p in full_name.strip().split() if p]
    return parts[-1] if parts else ""


# High-traffic call signs — always included; sit near the end of the prompt.
_HOT_LAST_KEYS = (
    "yannett",
    "mayes",
    "strickland",
    "chandler",
    "klepfer",
    "hatfield",
    "simmeth",
    "medlin",
    "boyes",
    "richar",
    "richard",
    "steffler",
    "worsham",
    "tyson",
    "marvel",
    "moore",
)

# Always-on radio terms (merged with common_words.txt, then capped).
_PRIORITY_TERMS = (
    "10-4",
    "go for",
    "go ahead",
    "thank you",
    "chromebook",
    "media center",
    "phone call",
    "my office",
    "headed to",
    "bus lot",
    "bathroom",
    "nurse",
)

# Stock Whisper / faster-whisper prompt slice (see docs/whisper_prompt_budget.md).
_DEFAULT_PROMPT_TOKEN_BUDGET = 223


def _prompt_token_count(text: str, tokenizer=None) -> int:
    """Exact BPE count when tokenizer available; else ~chars/4 heuristic."""
    if tokenizer is not None:
        from edupulse.whisper_prompt_budget import measure_prompt

        return measure_prompt(text, tokenizer=tokenizer).tokens
    # Conservative heuristic (Whisper BPE is often denser than 4 chars/token on names).
    return max(1, (len(text) + 3) // 3)


def _pack_name_aliases(
    ordered_aliases: list[str],
    head: str,
    tail: str,
    budget: int,
    tokenizer=None,
    sep: str = " ",
) -> tuple[str, int]:
    """Greedily pack as many name aliases as fit under budget.

    Use ``sep=' '`` for single-token phonetic codes, ``sep=', '`` for Title+Last.
    Returns ``(prompt, n_packed)``.
    """
    if not ordered_aliases:
        return " ".join(p for p in (head, tail) if p).strip(), 0

    lo, hi = 0, len(ordered_aliases)
    best_mid = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        names = ("Codes: " + sep.join(ordered_aliases[:mid]) + ".") if mid else ""
        full = " ".join(p for p in (head, names, tail) if p).strip()
        if _prompt_token_count(full, tokenizer) <= budget:
            best_mid = mid
            lo = mid + 1
        else:
            hi = mid - 1
    names = ("Codes: " + sep.join(ordered_aliases[:best_mid]) + ".") if best_mid else ""
    return " ".join(p for p in (head, names, tail) if p).strip(), best_mid


def build_enhanced_initial_prompt(
    base: str | None = None,
    known_staff: list[str] | None = None,
    common_words: list[str] | None = None,
    extra_context: str | None = None,
    max_tokens: int | None = None,
    use_codebook: bool | None = None,
) -> str:
    """Build a Whisper initial_prompt fingerprint that **fits the ~223-token budget**.

    Prefer a short **radio-user** list (``radio_staff.txt``) as ``known_staff`` so we
    can ship readable Title+Last names without phonetic codes. Full ``staff_names.txt``
    should still drive IncidentTracker / enrollment resolve separately.

    Packing order:
      1. Short base + compact channel terms
      2. Staff names — Title+Last if they fit; else phonetic codebook aliases
      3. Hot call signs + gold protocol phrases at the **end**
    """
    budget = max_tokens if max_tokens is not None else _DEFAULT_PROMPT_TOKEN_BUDGET
    base = (base or "School radio.").strip()

    clean_staff = [
        n for n in (known_staff or [])
        if n and n.strip() and not n.strip().startswith("#")
    ]
    title_last = sorted({_staff_title_last(n) for n in clean_staff})
    last_names = sorted({_staff_last_name(n) for n in clean_staff if _staff_last_name(n)})
    hot = [
        t for t in title_last
        if any(key in t.lower() for key in _HOT_LAST_KEYS)
    ]
    hot_lasts = sorted({t.split()[-1] for t in hot})

    # Merge priority + user terms; keep unique, short list.
    term_set: list[str] = []
    for w in list(_PRIORITY_TERMS) + list(common_words or []):
        wl = w.lower().strip()
        if wl and wl not in term_set:
            term_set.append(wl)
    # Keep terms short so a full radio-carrier Title+Last roster can fit ≤223 tokens.
    terms = term_set[:10]

    head_parts = [base]
    if terms:
        head_parts.append("Terms: " + ", ".join(terms) + ".")
    if extra_context:
        head_parts.append(extra_context.strip())
    head = " ".join(head_parts)

    phrases_tail = (
        "Phrases: Yannett to Mayes, Go for Mayes, Go for Coach Richar, go ahead, 10-4."
    )

    tokenizer = None
    try:
        from edupulse.whisper_prompt_budget import get_whisper_tokenizer

        tokenizer = get_whisper_tokenizer()
    except Exception:
        tokenizer = None

    # Prefer readable Title+Last when the radio roster is small enough to fit.
    hot_tl = [t for t in title_last if t.split()[-1] in set(hot_lasts)]
    rest_tl = [t for t in title_last if t not in set(hot_tl)]
    ordered_title_last = hot_tl + rest_tl

    # Title+Last path: skip duplicate Call: block (names already in Codes) to save budget.
    trial_full, n_packed = _pack_name_aliases(
        ordered_title_last, head, phrases_tail, budget, tokenizer=tokenizer, sep=", "
    )

    need_codebook = use_codebook
    if need_codebook is None:
        # Auto: codebook only if we cannot fit most Title+Last names
        need_codebook = bool(clean_staff) and (
            not title_last or n_packed < max(1, int(0.85 * len(title_last)))
        )

    if need_codebook and clean_staff:
        from edupulse.name_codebook import build_name_codebook, set_active_codebook

        codebook = build_name_codebook(clean_staff, tokenizer=tokenizer)
        set_active_codebook(codebook)
        ordered = codebook.prompt_aliases(hot_lasts=hot_lasts)
        try:
            from pathlib import Path

            codebook.save(Path.home() / "edupulse" / "name_codebook.json")
        except Exception:
            pass
        # Codebook path: keep Call: with full Title+Last hot names (codes are abbreviated).
        call_tail = ""
        if hot:
            call_tail = "Call: " + ", ".join(hot) + ". "
        tail = call_tail + phrases_tail
        prompt, _n = _pack_name_aliases(
            ordered, head, tail, budget, tokenizer=tokenizer, sep=" "
        )
    else:
        # Still activate codebook decode (hand aliases) for expand/resolve
        if clean_staff:
            try:
                from edupulse.name_codebook import build_name_codebook, set_active_codebook

                set_active_codebook(build_name_codebook(clean_staff, tokenizer=None))
            except Exception:
                pass
        prompt = trial_full

    # Final safety: never ship over budget (exact fit when tokenizer works).
    if tokenizer is not None:
        from edupulse.whisper_prompt_budget import fit_prompt_to_budget

        prompt = fit_prompt_to_budget(prompt, budget=budget, tokenizer=tokenizer)
    else:
        while _prompt_token_count(prompt) > budget and "Codes:" in prompt:
            before, after = prompt.split("Codes:", 1)
            names_part, rest = after.split(".", 1)
            # Drop last comma-separated entry (Title+Last) or space token
            if ", " in names_part:
                bits = [b.strip() for b in names_part.split(",") if b.strip()]
                sep = ", "
            else:
                bits = names_part.strip().split()
                sep = " "
            if len(bits) <= 1:
                prompt = (before + rest).strip()
                break
            prompt = (before + "Codes: " + sep.join(bits[:-1]) + "." + rest).strip()

    return prompt.strip()

