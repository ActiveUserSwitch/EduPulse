# Validation data (what belongs in Git)

## In this repository (safe for IT review)

| File | Purpose |
|------|---------|
| `demo_validation_sample.csv` | **Synthetic** rows only (fictional names/paths) |
| `validate_edupulse.py` | Metrics tooling |
| `organize_model_outputs.py` | Helpers |
| `*.md` | Definitions / metrics notes |

## Local only (gitignored — may contain real staff/student language)

Real hand-coded CSVs, consensus files, graduation samples, hand-coding logs, and semantic maps built from live radio stay **on the research machine**, never in Git:

- `aligned_validation_data*.csv`
- `human_consensus.csv`
- `validation_sample_*.csv`
- `focused_transcription_validation.csv`
- `graduation_vad_transcription_focused.csv`
- `hand_coding_log.txt`

Use the same column layout as `demo_validation_sample.csv` / prior local files when working offline.

## Why

School radio transcripts can include student and staff identifiers. Principal approval covers the research use of that data **locally**; it does not mean the public/code repository should hold it.
