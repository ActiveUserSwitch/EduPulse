# hardware/capture/

Scripts for capturing and post-processing school radio traffic.

**This is the active directory for the capture + offline iteration tools.**

See the root `README.md` and `ROADMAP.md` for the current overall status and
recommended workflow.

## Primary Tools (use these)

- `record_with_transcribe.py` — The tool used for the final full-day runs.
  Produces one raw `.wav` per transmission + sidecar JSON +
  `session_manifest.jsonl`.
- `retag_session.py` — Re-apply current rules (categorization + IncidentTracker +
  fingerprint) to any previous session. Updates sidecars. Run this after any
  change to `edupulse/analysis.py` or the fingerprint files.
- `analyze_manifest.py` — Quick stats + "Data Quality Summary" from a `.retagged.jsonl`.
- `staff_names.txt` + `common_words.txt` — The live audio fingerprint files (one
  full staff name or common word/phrase per line). These are the highest-leverage
  things you maintain.

## Supporting / Historical

- `record_session.py` — Earlier tool for short/controlled bring-up sessions (has
  `--preview` / `--label`).
- Old checklists (`DAY1_UCA222_CHECKLIST.md`, `FIRST_LONG_RUN_CHECKLIST.md`, etc.)
  are kept for historical reference only. The active process is described in the
  root docs.
- `test_px650.py`, `record_continuous.py`, etc. — early experiments.

## Wiring & Hardware Notes

See `../wiring/Cobra_PX650_UCA222.md`.

For the current recommended way to launch a capture or re-process data, read the
root `README.md`.
