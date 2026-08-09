"""Incident linking (IncidentTracker) and staff mention extraction."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

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


# Convenience: a module-level default tracker for simple live scripts
default_tracker = IncidentTracker()
