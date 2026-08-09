#!/usr/bin/env python3
"""
EduPulse - Shared Analysis (categorization + incident linking)

This module contains the core "analysis" pieces that are used both by
live capture tools and by the offline test scripts. It is intentionally
kept lightweight (no audio/ML imports here) so it can be imported early.

- Rudimentary keyword-based transmission categorization (user's exact 12 categories).
- Radio-protocol aware IncidentTracker for grouping related transmissions
  into INC-xxx conversation/incident IDs.
- Audio fingerprint support via known_staff_names (full teaching staff names)
  passed to IncidentTracker and build_enhanced_initial_prompt(known_staff=..., common_words=...).
  This lets you "fingerprint" the specific radio environment (staff voices + most
  frequent words/phrases) for much better Whisper transcription and accurate
  role vs. student name extraction.

The logic encodes the radio format the user described (caller addresses
receiver by role/name, acknowledgments, student names as strong anchors,
role calls (Nurse, Officer, Mr./Coach/etc.) usually start new incidents
unless tied by student, JROTC and Athletic special handling, full-name
student priority + mismatch penalties, low-conf garbage filtering, etc.).

Used by:
  - hardware/capture/record_with_transcribe.py (and future capture tools)
  - test/test_realtime_transcribe.py
  - test/test_whisper.py

Keep this file as the single source of truth. When you improve categorization
or linking rules, update here and the tests/capture will benefit.

To use the fingerprint feature: collect full staff names + the most common
words heard on the air, then either pass them at CLI (--known-staff-file,
--common-words-file) or construct the prompt / tracker manually.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# =============================================================================
# RUDIMENTARY TRANSMISSION CATEGORIZATION
# =============================================================================
# This is a simple keyword-based classifier for school administrative radio.
# It is intentionally rudimentary (as requested) to provide immediate value
# during live testing while we iterate on better ML-based classification later.
#
# These categories were provided by the user for this school radio analysis project.
# They map to common types of administrative radio transmissions in a school setting.
#
# You can easily extend the keyword lists below. Matches are case-insensitive.
# A transmission can match multiple, but we report the highest-scoring one.
# =============================================================================

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


# =============================================================================
# INCIDENT / CONVERSATION LINKING
# =============================================================================
# Based on typical school radio protocol:
#   Caller A: "Receiver B [Caller A]"
#   Receiver B: "Go ahead / Yes / Copy"
#   Caller A: message
#   Receiver B: question / confirm / clarify
#
# Key rules (per user):
# - Student names (especially full "First Last" like "Emily Rodriguez" or "Ricky Bobby") are *very strong anchors*.
#   Mentioning the same student (by full name) is a safe bet for continuation of the same event.
#   Different full student names almost always means a separate incident. Single names are weaker.
# - Role calls (Nurse, Officer, Sergeant, Captain, Custodian, Mr./Mrs./Ms./Miss/Mister/Coach etc.)
#   usually start *new* incidents unless clearly tied to a student.
# - JROTC officers (Sergeant Marvel, Captain Hatfield, etc.) are grouped together when JROTC context is present.
# - Coaches are tagged for the Athletic Department (treated as role/teacher-or-admin).
# Full student names take precedence and prevent cross-student over-linking of unrelated
# early dismissals, nurse calls, etc.
# Low-conf or "Other / Unclear" segments skip name extraction for linking.
# =============================================================================


class IncidentTracker:
    def __init__(self, max_age_seconds: float = 300, max_open: int = 30, known_staff_names: list[str] | None = None):
        self.incidents: list[dict[str, Any]] = []
        self.next_id = 1
        self.max_age = max_age_seconds
        self.max_open = max_open
        self.known_staff_full: set[str] = set(known_staff_names or [])
        self.known_staff_firsts: set[str] = {n.split()[0].lower() for n in (known_staff_names or []) if n.strip()}

    def _cleanup_old(self, now: float) -> None:
        cutoff = now - self.max_age
        self.incidents = [i for i in self.incidents if i["last_time"] > cutoff]

    def _extract_names(self, text: str) -> dict[str, list[str]]:
        """Rudimentary name / title extraction from radio speech.
        Returns dict with:
          - 'students': list of full names preferred (e.g. "Ricky Bobby", "Emily Rodriguez"), then single first names.
          - 'roles': titled staff and JROTC roles (e.g. "Captain Hatfield", "Sergeant Marvel", "Officer Tyson", "JROTC").
            Includes Mr./Mister/Mrs./Misses/Ms./Miss/Coach (teachers/admin per user request); Coach also tags Athletic Department.
        Student full names (first + last) are treated as strong unique anchors for incidents.
        """
        students: list[str] = []
        roles: set[str] = set()

        # Role starters (first word of titles) so we never misclassify "Coach Jones", "Mr. Smith", "Sergeant Marvel" as students
        role_starters = {
            "officer",
            "deputy",
            "sergeant",
            "captain",
            "nurse",
            "principal",
            "dr",
            "doctor",
            "mr",
            "mrs",
            "ms",
            "miss",
            "mister",
            "misses",
            "coach",
            "custodian",
            "janitor",
            "admin",
            "test",          # "Test Monitoring" during finals
            "monitoring",
            "chromebook",    # equipment, not a person
        }
        # Incorporate known staff from fingerprint (provided full names of teaching staff)
        role_starters.update(self.known_staff_firsts)

        # 1. Titled names (Captain Hatfield, Sergeant Marvel, Officer Tyson, Mr. Smith, Coach Jones, etc.) as roles -- FIRST
        role_titles = (
            r"(Officer|Deputy|Mr\.|Mrs\.|Ms\.|Miss|Mister|Misses|Dr\.|Principal|Assistant Principal|Nurse|Counselor|Admin|Deputy|Custodian|Janitor|Sergeant|Captain|Coach)"
        )
        role_last_names: set[str] = set()
        for m in re.finditer(role_titles + r"\s+([A-Z][a-zA-Z]+)", text, re.IGNORECASE):
            role_name = m.group(0).strip()
            roles.add(role_name)
            # Add context for JROTC or Athletic dept
            lname = role_name.lower()
            if "sergeant" in lname or "captain" in lname:
                roles.add("JROTC")
            if "coach" in lname:
                roles.add("Athletic Department")
            parts = [p.strip(".,") for p in role_name.split()]
            if len(parts) > 1:
                role_last_names.add(parts[-1])

        # Fingerprint: known staff full names (e.g. "Ms. Chandler") are always roles, never students
        for staff in self.known_staff_full:
            if staff.lower() in text.lower():
                roles.add(staff)

        # 2. Standalone known roles (including JROTC officers, coaches, Mr/Mrs etc. as teachers/admin)
        known_roles = {
            "nurse",
            "officer",
            "deputy",
            "principal",
            "custodian",
            "janitor",
            "office",
            "admin",
            "sergeant",
            "captain",
            "jrotc",
            "coach",
            "mister",
            "misses",
            "mr",
            "mrs",
            "ms",
            "miss",
        }
        words = re.findall(r"\b([A-Za-z]+)\b", text)
        for w in words:
            if w.lower() in known_roles:
                roles.add(w.capitalize())

        # 3. Standalone "JROTC" or "Athletic"
        if re.search(r"\bjrotc\b", text, re.IGNORECASE):
            roles.add("JROTC")
        if re.search(r"\bathletic\b", text, re.IGNORECASE):
            roles.add("Athletic Department")

        # 4. Capture full names for students (First Last) - these are strong unique identifiers
        # Common patterns: "Ricky Bobby", "Emily Rodriguez". Skip any that start with role titles (e.g. Coach Jones).
        full_name_pattern = r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b"
        for m in re.finditer(full_name_pattern, text):
            first = m.group(1)
            full_name = f"{m.group(1)} {m.group(2)}"
            if full_name.lower() in {s.lower() for s in self.known_staff_full}:
                roles.add(full_name)
                continue
            if first.lower() in role_starters:
                continue
            if full_name not in students:
                students.append(full_name)

        # 5. Plain capitalized first names as students ONLY if not already part of a captured full name
        # and not a known role or the lastname of a role title (e.g. do not treat "Smith" from "Mr. Smith" as student)
        common_non_names = {
            "The",
            "This",
            "That",
            "For",
            "And",
            "Yes",
            "No",
            "Go",
            "All",
            "Can",
            "You",
            "We",
            "They",
            "Copy",
            "Roger",
            "Affirmative",
            "Standing",
            "Office",
            "Gym",
            "Cafeteria",
            "Hallway",
            "Bus",
            "Nurse",
            "Officer",
            "Deputy",
            "Principal",
            "Custodian",
            "Sergeant",
            "Captain",
            "JROTC",
            "Mister",
            "Misses",
            "Coach",
            "Mr",
            "Mrs",
            "Ms",
            "Miss",
            # Halluc/garbage + common short radio ack words + exam logistics terms (June 3/4 runs)
            "Hello", "Thank", "Sorry", "Okay", "What", "How", "Let", "Just", "She", "He", "It",
            "One", "Two", "Three", "First", "Next", "Please", "Thanks", "Good", "Bad", "Over", "Out",
            "Are", "Yeah", "Hey", "Did", "Not", "Give", "Been", "Working", "Today", "Very", "Much",
            "John", "Lund", "Sure", "Minute", "Wait", "Take", "Again",
            "Chromebook", "Test", "Monitoring", "Bio", "Biology", "Retake", "Exam", "Final", "Finals",
            "Log", "Path", "Forward",  # from "log in", "path forward" in test monitoring chatter
        }
        captured_full_firsts = {s.split()[0] for s in students}
        captured_full_names = set(students)
        for m in re.finditer(r"\b([A-Z][a-z]{2,})\b", text):
            word = m.group(1)
            if word not in common_non_names and word not in captured_full_firsts:
                if word not in roles and word not in role_last_names:
                    if word.lower() in self.known_staff_firsts:
                        roles.add(word.capitalize())
                        continue
                    # Do not add fragments of already captured full names (e.g. "Bobby" when "Ricky Bobby" exists)
                    is_fragment_of_full = any(word in fn for fn in captured_full_names)
                    if not is_fragment_of_full and word not in students:
                        students.append(word)

        return {"students": students[:5], "roles": list(roles)[:5]}

    def _looks_like_call_initiation(self, text: str) -> bool:
        """Heuristic based on the radio format the user described.
        Even if the segment transcript includes the full exchange (name? go ahead. message. yes ma'am),
        if it contains a clear new role/name call (especially "Name?"), treat as initiation of a (potentially new) call.
        """
        t = text.lower().strip()
        words = t.split()

        # Clear initiation patterns: starts with or contains "Role Name?" or "Role Name," at beginning
        initiation_patterns = [
            "officer ",
            "deputy ",
            "sergeant ",
            "captain ",
            "nurse ",
            "principal ",
            "dr. ",
            "mr. ",
            "mrs. ",
            "ms. ",
            "mister ",
            "misses ",
            "coach ",
            "mr ",
            "mrs ",
            "ms ",
            "miss ",
        ]
        for p in initiation_patterns:
            if t.startswith(p) or f"{p.strip()}?" in t or f"{p.strip()}," in t[:20]:
                return True

        # Acknowledgments suggest response, but only return False if no new call pattern above
        ack = ["go ahead", "yes ma'am", "yes sir", "yeah", "copy", "roger", "10-4", "affirmative", "standing by", "yes"]
        if any(a in t for a in ack):
            # If there's also a clear name call, still initiation
            if any(p.strip() in t for p in initiation_patterns):
                return True
            return False

        # Very short + role
        if len(words) <= 5 and any(
            x in t for x in ["officer", "deputy", "mr.", "mrs.", "ms.", "principal", "nurse", "office", "mister", "misses", "coach", "mr", "mrs", "ms", "miss"]
        ):
            return True

        # "X for dismissal" etc.
        if "for dismissal" in t or "to the office" in t or "for pickup" in t:
            return True

        return False

    def get_incident_id(
        self,
        text: str,
        timestamp: float | datetime,
        category: str,
        whisper_conf: float | None = None,
        cat_conf: float | None = None,
    ) -> str:
        """Returns an incident ID for this transmission.

        Key new heuristic (per user guidance):
        - If a *student* is referenced (preferably full First Last name), this is a very strong signal that it belongs to
          an existing incident involving that student (or starts one keyed on the student).
          A single student is unlikely to be the subject of two unrelated radio events close in time.
        - Role-based calls (Nurse, Officer, Custodian, Mr./Coach/Dr. etc.) are treated as likely *new* incidents
          unless they are clearly tied to a specific student or other strong linking evidence.
        - Low-confidence or "Other / Unclear" segments do not pollute the name sets used for future linking.
        """
        if isinstance(timestamp, datetime):
            now = timestamp.timestamp()
        else:
            now = float(timestamp)

        self._cleanup_old(now)

        # Skip name extraction from low-quality or unclear segments to prevent garbage names
        # (e.g. "Depth half-year-old.", "Captain Happield") from polluting student sets.
        use_names_for_linking = True
        if whisper_conf is not None and whisper_conf < 0.40:
            use_names_for_linking = False
        if category == "Other / Unclear" and (cat_conf is not None and cat_conf < 0.30):
            use_names_for_linking = False

        if use_names_for_linking:
            extracted = self._extract_names(text)
            students: set[str] = set(extracted.get("students", []))
            roles: set[str] = set(extracted.get("roles", []))
        else:
            students = set()
            roles = set()

        is_initiation = self._looks_like_call_initiation(text)
        is_response = any(a in text.lower() for a in ["go ahead", "yes", "yeah", "copy", "roger", "10-4", "affirmative"])

        best: dict[str, Any] | None = None
        best_score = -1

        for inc in self.incidents:
            score = 0

            # Time proximity (radio conversations are usually quick back-and-forth)
            gap = now - inc["last_time"]
            if gap < 15:
                score += 5
            elif gap < 45:
                score += 3
            elif gap < 90:
                score += 1

            inc_students = set(inc.get("students", []))
            inc_roles = set(inc.get("roles", []))

            # === STUDENT ANCHOR LOGIC (user's main point) ===
            # Full student names (First Last) are the strongest possible anchor.
            # Only link on full name match for students. Different full names = different incidents.
            current_full_students = {s for s in students if " " in s}
            inc_full_students = {s for s in inc_students if " " in s}
            shared_full_students = current_full_students & inc_full_students
            if shared_full_students:
                score += 15 + (len(shared_full_students) * 5)  # extremely high weight

            full_name_conflict = bool(current_full_students and inc_full_students and not shared_full_students)
            if full_name_conflict:
                # Different full student names mentioned → this is almost certainly a new incident
                score -= 25

            # Single name students still give a boost, but weaker, and only if no full-name conflict
            if not current_full_students:
                shared_single_students = (set(students) - current_full_students) & (set(inc_students) - inc_full_students)
                if shared_single_students:
                    score += 6 + (len(shared_single_students) * 2)

            # Role overlap (JROTC officers etc.) is useful for linking within JROTC context
            shared_roles = roles & inc_roles
            if shared_roles:
                if "JROTC" in shared_roles or shared_full_students:
                    score += 6  # strong for JROTC or with student
                elif shared_full_students:
                    score += 4
                else:
                    score += 1  # generic role calls are weak by themselves

            # Category continuity (secondary)
            if inc.get("last_category") == category:
                score += 1

            # Strong bias for responses/acknowledgments toward the most recent incident
            if is_response and inc is self.incidents[-1] if self.incidents else False:
                score += 4

            if score > best_score:
                best_score = score
                best = inc

        # Additional check: if the best previous is student-anchored but current has NO students at all,
        # do not link. This is a new role-based call (office, Dr., Mr., Coach, etc.) unrelated to the prior student event.
        if best:
            best_students = set(best.get("students", []))
            if best_students and len(students) == 0:
                best = None
                best_score = -1

        # Linking decision
        # Compute conflict for the best match
        best_full_students = {s for s in (best.get("students", []) if best else []) if " " in s}
        current_full = {s for s in students if " " in s}
        full_name_conflict = bool(current_full and best_full_students and not (current_full & best_full_students))

        shared_students = students & (best.get("students", set()) if best else set())

        min_score = 4
        if roles and not students:
            min_score = 7

        should_link = False
        if best and best_score >= min_score:
            if full_name_conflict:
                should_link = False
            elif not is_initiation:
                should_link = True
            elif shared_students:
                should_link = True
            elif "JROTC" in roles and best and "JROTC" in best.get("roles", set()):
                # Allow JROTC officers (sgt/captain) to continue the same INC even across call-style initiations
                # (per user request to connect JROTC), while non-JROTC roles (Mr/Coach/Dr/Nurse) start fresh unless student-linked.
                should_link = True

        if should_link:
            # Link
            best["last_time"] = now  # type: ignore[index]
            best["last_category"] = category  # type: ignore[index]
            best["students"] = best.get("students", set()) | students  # type: ignore[index]
            best["roles"] = best.get("roles", set()) | roles  # type: ignore[index]
            best["count"] = best.get("count", 0) + 1  # type: ignore[index]
            return best["id"]  # type: ignore[index]
        else:
            # Start fresh incident
            inc_id = f"INC-{self.next_id:03d}"
            self.next_id += 1
            new_inc: dict[str, Any] = {
                "id": inc_id,
                "start_time": now,
                "last_time": now,
                "last_category": category,
                "students": students,
                "roles": roles,
                "count": 1,
            }
            self.incidents.append(new_inc)
            if len(self.incidents) > self.max_open:
                self.incidents.pop(0)
            return inc_id


# Convenience: a module-level default tracker for simple live scripts
# (capture tools usually create their own for the session).
default_tracker = IncidentTracker()


def extract_staff_mentions(text: str, known_staff: list[str] | None = None) -> list[str]:
    """Lightweight, high-precision extraction of known staff / role mentions.

    Intended primarily for weak supervision in speaker identification:
    clips whose transcript mentions *exactly one* staff member are excellent
    enrollment examples for that voice (the whole short PTT clip is almost
    always that one person speaking).

    Reuses the same title + known-staff matching rules as IncidentTracker._extract_names
    so behavior is consistent with the rest of the system. Returns canonical
    "Title First Last" forms from the known_staff list whenever possible.

    Extra radio-friendly matching:
    - Last-name only ("Strickland", "Go for Simmeth", "Medlin") resolves to the
      single matching staff when the last name is unique in the list.
    - Common title variants ("Dr. Strickland" vs "Ms. Tracy Strickland" in the file)
      are tolerated via last-name resolution + title context.
    - Spelling variants observed in real gold (Goltsch / Goldsch / Goble) still
      only match if a close last name exists; we stay conservative.

    Safe to call with no torch/pyannote; pure stdlib.
    """
    if not text or not known_staff:
        return []

    known_map = {s.lower(): s for s in known_staff if s and s.strip()}
    text_lower = text.lower()
    mentions: list[str] = []

    # 1. Direct full-name / strong substring matches from the authoritative list
    for low, canon in known_map.items():
        if low in text_lower:
            if canon not in mentions:
                mentions.append(canon)

    # Build last-name -> list of canons (for radio "last name only" calls)
    last_to_canons: dict[str, list[str]] = {}
    for canon in known_staff:
        if not canon:
            continue
        last = canon.split()[-1].lower().strip(".,")
        last_to_canons.setdefault(last, []).append(canon)

    # 2. Titled patterns — resolve by last name to canonical full form
    role_titles = (
        r"(Officer|Deputy|Mr\.?|Mrs\.?|Ms\.?|Miss|Mister|Misses|Dr\.?|Principal|"
        r"Assistant Principal|Nurse|Counselor|Admin|Custodian|Janitor|"
        r"Sergeant|Captain|Coach)"
    )
    titled_re = re.compile(role_titles + r"\s+([A-Z][a-zA-Z][a-zA-Z'-]+)", re.IGNORECASE)
    for m in titled_re.finditer(text):
        last = m.group(2).lower().strip(".,:;")
        resolved = False
        for canon in last_to_canons.get(last, []):
            if canon not in mentions:
                mentions.append(canon)
            resolved = True
        if not resolved:
            surface = m.group(0).strip().rstrip(".,:;")
            if surface not in mentions:
                mentions.append(surface)

    # 3. Bare last-name mentions common in radio ("Medlin", "Simmeth", "Strickland")
    #    Only resolve when the last name maps to *exactly one* staff (safe).
    #    Look for capitalized words that are known lasts.
    word_re = re.compile(r"\b([A-Z][a-zA-Z][a-zA-Z'-]+)\b")
    for m in word_re.finditer(text):
        w = m.group(1).lower()
        canons = last_to_canons.get(w, [])
        if len(canons) == 1:
            canon = canons[0]
            if canon not in mentions:
                mentions.append(canon)

    # Dedup while preserving first-seen order, case-insensitive
    seen: set[str] = set()
    out: list[str] = []
    for m in mentions:
        key = m.lower()
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


# =============================================================================
# Probabilistic Language Modeling Stubs (Roadmap Implementation Start)
# See ROADMAP.md "Probabilistic Language Modeling Roadmap" for full plan.
# Current semantic map (co-occurrence) is a useful starting point but not
# a true sequence model. These stubs will evolve into n-gram then neural LMs
# trained only on the hand-coded day (2026-06-05) + onward corpus.
# All modeling remains strictly post-accumulation.
# =============================================================================

from typing import Any, Optional

def load_hand_coded_onward_corpus() -> list[dict]:
    """Return list of {"text": ..., "acoustic": ..., "critical": ..., "tx": ...}
    strictly from 2026-06-05 + graduation + validation CSVs (large-v3 + human gold).
    This is the ONLY data used for "normal" radio traffic modeling.
    Earlier days are excluded to avoid light-model noise.

    Used for future n-gram LM training, semantic baselines, and "complete"
    sampling re-aggregation. Called post-accumulation only.
    """
    import glob
    import json
    import os

    ref_dirs = [
        "/home/joseph/edupulse/captures/2026-06-05_last-day-2",
        "/home/joseph/edupulse/captures/2026-06-09_2026-06-08_graduation",
    ]
    items: list[dict] = []
    for d in ref_dirs:
        for j in glob.glob(os.path.join(d, "tx_*.json")):
            try:
                with open(j) as f:
                    m = json.load(f)
                if m.get("model") != "large-v3":
                    continue
                tags = m.get("tags", []) or []
                is_crit = bool(m.get("critical_baseline")) or ("fight_report" in tags)
                text = (m.get("transcription") or "").strip()
                if not text:
                    continue
                # light filter: skip obvious noise unless it is a known critical
                if not is_crit and is_likely_noise(text, float(m.get("duration_sec", 0) or 0), m.get("whisper_conf")):
                    continue
                ac = m.get("acoustic_features") or {}
                items.append({
                    "text": text,
                    "acoustic": ac,
                    "critical": is_crit,
                    "tx": os.path.basename(j).replace(".json", ""),
                    "duration_sec": m.get("duration_sec"),
                    "category": m.get("category"),
                    "dir": os.path.basename(d),
                })
            except Exception:
                continue

    # TODO (phase 1/2): also ingest validation/*.csv (human gold + large-v3 columns)
    # for additional clean transcripts when building n-gram counts.
    # For now the hand-coded day + grad sidecars provide the primary clean corpus.
    return items


def compute_lexical_surprisal(
    text: str,
    normal_lm: Optional[Any] = None,
    smoothing: str = "add1",
    **kwargs,
) -> dict[str, float]:
    """Return surprisal metrics for the transcript under a "normal" radio LM.

    When normal_lm is None or not yet implemented, falls back to a simple
    entity-rarity proxy (inspired by the current build_radio_semantic_map and
    fight-report seeds). Future (phase 2+) will use n-gram (or neural) LM
    trained ONLY on load_hand_coded_onward_corpus() and return real
    mean -log2(p) per token or total sequence surprisal.

    The resulting "lexical_surprisal" is combined with acoustic z-scores
    (see compute_information_score) for the multi-modal field stored in
    sidecars during batch-at-complete-sampling.

    This is deliberately post-accumulation only. No live z / surprisal.
    """
    if not text or not text.strip():
        return {"lexical_surprisal": 0.0}

    # Phase-1 proxy (until n-gram LM): use crisis/event seeds + protocol deviation
    # drawn from the same seeds as build_radio_semantic_map + the fight report anchor.
    # This gives the bookmarked fight clip a visibly higher lexical component immediately.
    # Real implementation will replace with:
    #   counts from normal corpus -> p(w) -> -log2(p + eps) averaged over tokens.
    t = " " + text.lower() + " "
    tokens = [w for w in re.findall(r"\b[a-z']+\b", text.lower()) if len(w) > 1]

    # High-surprisal seeds for school radio "normal" (logistics, prowords, routine)
    # vs. rare crisis/urgent content.
    crisis_seeds = {
        "fighting", "fight", "administrator", "admin", "backup", "emergency",
        "media center", "theyre", "they're", "now", "help",
    }
    protocol_common = {
        "copy", "roger", "10-4", "go for", "on my way", "thank you",
        "standing by", "yes", "no", "affirmative",
    }

    rare_hits = sum(1 for tok in tokens if tok in crisis_seeds)
    # Penalize very short routine acks a little; boost longer or crisis-containing.
    base = 0.8
    if any(p in t for p in protocol_common):
        base -= 0.3
    if rare_hits:
        base += 4.0 * (rare_hits / max(1, len(tokens)))

    # scale roughly toward bits-like range for the fight example (~4-9)
    surp = max(0.0, round(base + 1.5 * (rare_hits > 0), 3))

    notes = "phase-1 proxy (crisis seeds + protocol deviation); replace with n-gram -log2(p) from hand-coded onward corpus"
    if normal_lm is not None:
        notes = "normal_lm provided but n-gram/neural not yet wired; using proxy"

    return {
        "lexical_surprisal": surp,
        "notes": notes,
    }


def compute_acoustic_zscores(
    clip_features: dict[str, float],
    baseline_stats: Optional[dict[str, tuple[float, float]]] = None,
    **kwargs,
) -> dict[str, float]:
    """Return z-scores for acoustic features vs. a "normal" baseline.

    clip_features: dict from compute_transmission_features or sidecar
                   (rms, speech_ratio, onset_rate, duration_sec, active_speech_sec, ...)
    baseline_stats: {feature: (mean, std), ...}  — can be pre-computed from
                    the hand-coded day onward corpus or maintained as
                    running per-day / exponential moving averages for
                    near-real-time use.

    This is the direct extension of the z-score analysis performed on the
    fight report clip (rms z=+6.65, speech_ratio z=+5.90, etc. vs. 06-05 baselines).
    It is already feasible "near real time" per clip (after heavy transcription
    and feature extraction complete).

    Returns e.g. {"rms_z": 6.65, "speech_ratio_z": 5.90, "composite_z": ...}
    """
    if baseline_stats is None:
        # In a real implementation this would come from a persisted
        # reference computed on the restricted (06-05 + grad) corpus,
        # or be updated online.
        return {"notes": "No baseline_stats provided — z-scores not computed (stub)."}

    out = {}
    composite_parts = []
    for feat, (mu, sigma) in baseline_stats.items():
        if feat in clip_features and sigma > 0:
            z = (clip_features[feat] - mu) / sigma
            out[f"{feat}_z"] = round(z, 3)
            composite_parts.append(z)
    if composite_parts:
        out["acoustic_composite_z"] = round(sum(composite_parts) / len(composite_parts), 3)
    return out


def compute_acoustic_zscores_from_running(
    clip_features: dict[str, float],
    running_baseline: "RunningNormalBaseline",
) -> dict[str, float]:
    """Convenience wrapper: compute z-scores using a RunningNormalBaseline.

    This gives you the *causal* (live) z-score for the current clip,
    based only on normal clips that arrived before it.
    """
    baseline_stats = running_baseline.to_baseline_stats()
    return compute_acoustic_zscores(clip_features, baseline_stats=baseline_stats)


class RunningNormalBaseline:
    """Maintains running mean and variance (Welford's method) for acoustic features.

    This directly solves the problem: "live Z-scores would only be based on files
    collected before the current clip, and would become inaccurate later when
    the dataset grows."

    - zscores() always returns values computed from *previous* normal clips only
      (causal / what you would have seen live for this clip).
    - You only call update() on clips that are *later classified as normal*.
      This way the baseline never gets polluted by the high-surprisal events
      themselves.

    Two common ways to use it:
    1. Pure live/causal: never recompute old z-scores. Each clip keeps the number
       it had when it arrived (based on data before it).
    2. Live provisional + final reference: use the causal numbers for immediate
       awareness during the day, then at end-of-day (or after review) compute
       stable z-scores against the day's final normal stats (or against a
       long-term reference like the complete 2026-06-05 hand-coded day) for
       the semantic map and permanent analysis. The live numbers don't have to
       match the final ones.

    Typical causal usage during a day:
        baseline = RunningNormalBaseline()
        for clip in day_clips_in_order:
            live_z = baseline.zscores(clip["acoustic_features"])
            # ... decide is_normal using live_z + lexical surprisal etc. ...
            if is_normal:
                baseline.update(clip["acoustic_features"])

    At end of day:
        final_reference = baseline.to_baseline_stats()   # only normals
        # or load a long-term reference from previous clean days
    """
    def __init__(self):
        import math
        self._count = 0
        self._mean: dict[str, float] = {}
        self._m2: dict[str, float] = {}   # sum of squares of differences

    def update(self, features: dict[str, float]):
        """Incorporate a clip that has been classified as normal."""
        self._count += 1
        for k, v in features.items():
            if k not in self._mean:
                self._mean[k] = 0.0
                self._m2[k] = 0.0
            delta = v - self._mean[k]
            self._mean[k] += delta / self._count
            delta2 = v - self._mean[k]
            self._m2[k] += delta * delta2

    def zscores(self, features: dict[str, float]) -> dict[str, float]:
        """Z-scores using the statistics from *previous* normal clips only.
        This is the value you would have seen "live" for this clip.
        """
        import math
        out = {}
        if self._count < 2:
            return {k: 0.0 for k in features}

        for k, v in features.items():
            if k in self._mean:
                var = self._m2[k] / (self._count - 1)
                sigma = math.sqrt(var) if var > 0 else 0.0
                out[f"{k}_z"] = round((v - self._mean[k]) / sigma, 3) if sigma > 0 else 0.0

        if out:
            vals = [out[k] for k in out if k.endswith("_z")]
            if vals:
                out["composite_z"] = round(sum(vals) / len(vals), 3)
        return out

    def to_baseline_stats(self) -> dict[str, tuple[float, float]]:
        """Current (mean, std) suitable for passing to compute_acoustic_zscores."""
        import math
        out = {}
        for k in self._mean:
            if self._count > 1:
                var = self._m2[k] / (self._count - 1)
                sigma = math.sqrt(var) if var > 0 else 0.0
                out[k] = (self._mean[k], sigma)
        return out

    @property
    def count(self) -> int:
        return self._count


def compute_information_score(
    transcript: str,
    acoustic_features: dict[str, float],
    normal_lm: Optional[Any] = None,
    acoustic_baselines: Optional[dict[str, tuple[float, float]]] = None,
    weights: Optional[dict[str, float]] = None,
) -> dict[str, float]:
    """Combine lexical surprisal (future LM) with acoustic z-scores into one score.

    This is the concrete realization of using both content and signal features
    for high -log₂(p) detection, as discussed in the fight report analysis.
    Weights default to balanced; can be tuned using the fight report (and future
    labeled critical clips) as anchor points where both components are high.
    """
    weights = weights or {"lexical": 0.5, "acoustic": 0.5}
    lex = compute_lexical_surprisal(transcript, normal_lm=normal_lm)
    ac_z = compute_acoustic_zscores(acoustic_features, baseline_stats=acoustic_baselines)

    # Simple combination for now (will become weighted sum of normalized terms)
    info = {
        "lexical_surprisal": lex.get("lexical_surprisal", 0.0),
        "acoustic_composite_z": ac_z.get("acoustic_composite_z", 0.0),
    }
    info["information_score"] = (
        weights["lexical"] * info["lexical_surprisal"]
        + weights["acoustic"] * info["acoustic_composite_z"]
    )
    return info


def batch_populate_acoustic_zscores(
    day_dir: str,
    reference_dirs: list[str] | None = None,
    exclude_critical: bool = True,
    field_name: str = "acoustic_zscores",
) -> None:
    """Batch compute and attach z-scores (and the richer information_score) to
    all sidecars in day_dir.

    Uses a reference "normal" baseline computed from the hand-coded day (06-05)
    and onward (graduation), excluding critical clips (tagged fight_report or
    critical_baseline=True). This implements the user's request:
      "create a field for it if we dont have one and populate it when we batch
       all the days files. Then we can aggrigate all of them when we have a
       'Complete' sampling."

    This is strictly the batch/post-day (or post-complete-set) way.
    No live / causal z-scores or information_score are written by this path
    (RunningNormalBaseline remains available for optional future use but is
    not invoked here).

    Call this (or batch_populate_information_scores) after the day's files
    have all been upgraded (large-v3 + pyannote acoustic_features present).

    Adds / updates on each qualifying sidecar:
      "acoustic_zscores": {"rms_z": ..., "speech_ratio_z": ..., "acoustic_composite_z": ...}
      "zscores_reference": "hand_coded_day_onward"
      "information_score": {
          "value": <blended>,
          "lexical_surprisal": <proxy or future -logp>,
          "acoustic_composite_z": <...>,
          "reference": "...",
          "computed_at": "..."
      }
      "lexical_surprisal": <top-level convenience copy>

    "Complete" sampling definition:
      - A day reaches "complete" when all its transmissions have been captured,
        heavy-transcribed, pyannote-enriched, optionally human-reviewed, and
        criticals (fight_report, etc.) have been tagged.
      - At that point, run batch population for the day (populates using the
        current declared complete reference set).
      - When additional days reach complete, extend the reference_dirs list
        (or the defaults inside this func) with their paths and re-invoke
        batch_populate_* on *all* participating complete days. This re-aggregates
        the baseline stats from the larger "normal" pool and refreshes every
        sidecar's information_score with stable, comparable numbers.
      - The hand-coded day (2026-06-05) + graduation currently define the
        initial complete reference. Earlier days are deliberately excluded.
    """
    import glob
    import json
    import os
    from datetime import datetime
    from pathlib import Path

    if reference_dirs is None:
        reference_dirs = [
            "/home/joseph/edupulse/captures/2026-06-05_last-day-2",
            "/home/joseph/edupulse/captures/2026-06-09_2026-06-08_graduation",
        ]

    # 1. Collect reference acoustic features for "normal" clips
    ref_features = []
    for d in reference_dirs:
        for j in glob.glob(os.path.join(d, "tx_*.json")):
            try:
                with open(j) as f:
                    m = json.load(f)
                if m.get("model") != "large-v3":
                    continue
                if exclude_critical:
                    tags = m.get("tags", [])
                    if m.get("critical_baseline") or "fight_report" in tags:
                        continue
                ac = m.get("acoustic_features") or {}
                if ac and all(k in ac for k in ["rms", "speech_ratio"]):  # at least key ones
                    ref_features.append(ac)
            except Exception:
                continue

    if not ref_features:
        print(f"No reference features found for z-scores from {reference_dirs}")
        return

    # Compute baseline_stats (mean, std)
    feats = ["rms", "peak", "approx_dbfs", "onset_rate", "speech_ratio", "active_speech_sec", "duration_sec"]
    baseline_stats = {}
    for feat in feats:
        vals = [f[feat] for f in ref_features if feat in f and f[feat] is not None]
        if vals:
            n = len(vals)
            mu = sum(vals) / n
            var = sum((x - mu) ** 2 for x in vals) / n
            sigma = var ** 0.5
            baseline_stats[feat] = (mu, sigma)

    # 2. For the day_dir, for each sidecar, compute z + full information_score and attach
    day_path = Path(day_dir)
    updated = 0
    for j in glob.glob(str(day_path / "tx_*.json")):
        try:
            with open(j) as f:
                m = json.load(f)
            ac = m.get("acoustic_features") or {}
            if not ac:
                continue
            z = compute_acoustic_zscores(ac, baseline_stats=baseline_stats)
            m[field_name] = z
            m["zscores_reference"] = "hand_coded_day_onward"

            # Create the requested information_score field (batch only, at complete sampling time).
            # Uses the just-computed baseline + current (phase-1 proxy) lexical surprisal.
            trans = m.get("transcription", "") or ""
            info = compute_information_score(trans, ac, acoustic_baselines=baseline_stats)
            m["information_score"] = {
                "value": round(info.get("information_score", 0.0), 3),
                "lexical_surprisal": round(info.get("lexical_surprisal", 0.0), 3),
                "acoustic_composite_z": info.get("acoustic_composite_z", 0.0),
                "reference": "hand_coded_day_onward",
                "computed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            # Convenience top-level (mirrors what many reports will query first)
            m["lexical_surprisal"] = m["information_score"]["lexical_surprisal"]

            with open(j, "w") as f:
                json.dump(m, f, indent=2)
            updated += 1
        except Exception as e:
            print(f"  zscore/info attach failed for {j}: {e}")
            continue

    print(f"Populated {field_name} + information_score for {updated} clips in {day_dir} using hand-coded reference.")
    print(f"  Reference clips used for normal baseline: {len(ref_features)}")
    print("  (information_score is batch-only; re-run after adding more complete days to re-aggregate)")


def batch_populate_information_scores(
    day_dir: str,
    reference_dirs: list[str] | None = None,
    exclude_critical: bool = True,
) -> None:
    """Primary entry point for the user's batch-at-complete-sampling request.

    Creates (if missing) and populates the "information_score" (and supporting
    acoustic_zscores / lexical_surprisal) fields for every large-v3 sidecar in
    the given day_dir.

    - Populated only when batch-processing all (or the complete set of) a day's files.
    - Baseline always drawn from the current "complete" reference (hand-coded day
      2026-06-05 + graduation, excluding tagged criticals).
    - When more days become "complete", update the reference list and re-invoke
      on the full set of complete days to re-aggregate.

    Delegates to the acoustic batch (which now also writes the information_score
    field). Safe to call multiple times; idempotent for already-processed clips
    (overwrites with fresh reference stats).
    """
    batch_populate_acoustic_zscores(
        day_dir,
        reference_dirs=reference_dirs,
        exclude_critical=exclude_critical,
    )


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


# =============================================================================
# OPTIONAL SPEAKER / VOICE RECOGNITION (pyannote.audio skeleton)
# =============================================================================
# This is the integration point for speaker diarization and identification.
#
# Everything lives in edupulse/speaker.py so that this file (analysis.py) stays
# lightweight and has no mandatory audio/ML imports.
#
# Recommended usage from test scripts or the capture worker:
#
#     from edupulse.speaker import enrich_with_speaker, get_speaker_database
#
#     # After you have a transcript + wav_path
#     speaker_info = enrich_with_speaker(
#         wav_path=wav_path,
#         transcript=transcription,
#         known_staff=known_staff_list,   # from staff_names.txt
#         diarize=False,                  # set True if you want within-clip segments
#     )
#
#     # Then put into the sidecar:
#     # meta["primary_speaker"] = speaker_info["primary_speaker"]
#     # meta["speaker_conf"]    = speaker_info["speaker_conf"]
#     # meta["speaker_segments"] = speaker_info["speaker_segments"]
#
# The SpeakerDatabase can mine weak labels from transcripts that mention
# exactly one known staff member (very useful with the gold human_transcripts
# and the large-v3 transcripts we already have).
#
# Use edupulse.analysis.extract_staff_mentions for high-quality weak supervision
# when building enrollment sets (preferred over naive substring checks).
#
# See test/test_speaker.py for a complete, runnable example that works on the
# existing graduation data and the hand-coded validation transcripts.
# =============================================================================

# Safe re-export of the main convenience function (never pulls in torch/pyannote
# unless someone actually calls it).
try:
    from .speaker import enrich_with_speaker  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    enrich_with_speaker = None  # type: ignore
