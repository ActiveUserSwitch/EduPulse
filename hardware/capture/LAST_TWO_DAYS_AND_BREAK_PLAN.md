# LAST_TWO_DAYS_AND_BREAK_PLAN.md (Historical)

This file contains the working notes from the final push of data collection.

**It is no longer the active document.**

For the current state of the project and the recommended workflow, read:

- `README.md` (root) — the essential single-page overview
- `ROADMAP.md` (root) — the only roadmap you need after the break

The old live-run checklists and cold-start protocol details that were here have
been summarized in the root docs. Keep this file only for historical context if
you ever want to see the exact commands and thinking from the last two days of
collection.

4. **Iterate the rules using real data** (the best part of the break):
   - Expand TRANSMISSION_CATEGORIES with actual phrases heard in finals (chromebook
     returns, test monitoring handoffs, bio retakes, building numbers, specific
     call signs).
   - Strengthen `is_likely_noise` with more patterns observed (video sign-offs like
     "Thanks for watching" / "Thank you for watching" were the classic
     tiny-Whisper hallucination on the last day's marginal tails; we added them
     and the short sign-off guard — they now get auto-flagged as Noise).
   - Refine name extraction / common_non_names from the actual staff and ack language
     in the transcripts.
   - The fingerprint files (staff_names.txt + common_words.txt) are now your living
     "channel profile" — keep growing them.

5. **Build real metrics and validation**:
   - Response bandwidth: time between related tx in an INC, busiest categories/times
     during finals stress.
   - Role usage (Dr. Strickland etc. on air), student mention rate, longest vs
     shortest INCs.
   - Validation set: randomly pick 40-60 real tx from the last two days, listen to
     the .wav + read the best transcript + category + INC. Score transcription
     accuracy, cat correctness, linking quality. This drives everything else.

6. **Long-term prep**:
   - Any lessons for the Pi return (VAD params that worked best, storage layout,
     one-channel handling).
   - Consider a small "reprocess_session.py" that walks a whole day dir and produces
     a fully validated manifest + report.

The raw .wav files are the treasure. Everything else (light transcripts, initial
cats/INCs) is scaffolding that gets replaced/improved during the break.

**High-value work during the break (no live radio needed)**:
- Re-transcribe promising/useful tx_*.wav files with `test/test_whisper.py --model
  base` or `medium` / `large-v3` (use the enriched initial prompt).
- Update sidecars or produce a "validated" manifest with better transcripts +
  re-run categorization + IncidentTracker.
- Iterate heavily on `edupulse/analysis.py`:
  - Add real phrases heard in the final days (e.g. "room 4 of 4", specific parent
    language, "Ms. Chandler", "civil creation" garbles that are actually
    something, "Test Monitoring", building numbers, etc.).
  - Refine student full-name vs role logic with real examples.
  - Improve is_likely_noise with new hallucination patterns seen on the last runs.
  - Possibly add simple ML (even just TF-IDF + small classifier) on the collected
    labeled data once you have enough validated transcripts.
- Build metrics: response time per INC, busiest categories during "finals stress",
  student mention rate, role participation (Athletic vs JROTC vs admin), longest
  conversations, etc.
- Validation: randomly sample 50-100 real tx, listen + score transcription
  accuracy, category correctness, INC linking quality. This drives the next
  version.
- Prepare for return to Pi: any lessons on VAD params, device handling, storage
  layout, etc.

**Practical tips for the break**:
- Immediately after the last run, `rsync -a ~/edupulse/captures/
  /backup-drive/edupulse-captures-$(date +%Y-%m-%d)/` or similar.
- Keep the entire GrokBuild checkout + the (edupulse-env) venv (or re-create from
  requirements.txt).
- The reprocessed manifests already have `is_noise` flags and cleaned INC/category
  fields — use those as starting point.
- Use the new `hardware/capture/retag_session.py`:
    ```
    python hardware/capture/retag_session.py ~/edupulse/captures/2026-06-XX_last-day-2/session_manifest.reprocessed.jsonl
    ```
  This re-runs the *current* rules from edupulse/analysis.py over the old
  transcripts, updates sidecars, and produces a .retagged.jsonl. Edit the rules,
  re-run this, re-analyze — repeat as much as you want over the summer with zero
  new live data.

- **Audio fingerprint** (the feature you asked about): collect a list of full
  teaching staff names and the most common words/phrases heard on the radio. Then
  for any re-processing or future runs:
    ```
    python hardware/capture/record_with_transcribe.py ... --known-staff-file staff.txt --common-words-file words.txt
    ```
  Or for offline:
    python test/test_whisper.py --file tx_....wav --known-staff-file staff.txt
    --common-words-file words.txt
  This builds the "fingerprint" into the Whisper prompt and makes IncidentTracker
  treat real staff names correctly as roles (not fake students). The more complete
  the lists, the better the dial-in for this specific environment.

- You can write small loops that walk a session dir, call the functions from
  `edupulse.analysis`, and patch the .json sidecars.

## Current Code State (what you have right now for the last runs)

- Continuous quiet-floor adaptation (`q~` / `thr~` in live line) — directly
  addresses short/bursty PTTs.
- Noise is auto-bucketed and does not pollute real INCs or stats.
- "Testing" category is live.
- Enriched initial prompt recommended.
- `analyze_manifest.py` now prints a "DATA QUALITY SUMMARY" tailored for go/no-go
  decisions under time pressure.
- All the Mr./Coach/Dr./student anchoring / JROTC / Athletic logic from earlier.

If Day 1 reveals a new specific failure mode (after you correct gain) that is easy
to patch without risking the second day, we will do the minimal change + quick
re-test using retag.

**Success for the live phase**: Two sessions with high usable % (>70-80% ideal),
  low noise, Testing + Logistics + other real categories appearing, reasonable INC
  grouping on the actual traffic, and — most importantly — a large set of clean
  per-tx .wav files with sidecar metadata.

Everything else (perfect real-time transcripts, perfect categories, perfect
linking) can be improved offline over the break using the data you collect in the
next ~48 hours.

Copy this plan (or the relevant parts) into your notes. After Day 1, paste the
analyzer "DATA QUALITY SUMMARY" output (plus a note on when you were able to
correct the gain) here and we'll decide any minimal tweak for the final day.

Good luck — the next two runs are the last live data for a while. Make them count
for collection.
