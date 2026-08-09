#!/usr/bin/env python3
"""
Quick offline re-tagger for a previous session after you edit edupulse/analysis.py.

Usage (during the last two days or the 3-month break):
  python hardware/capture/retag_session.py ~/edupulse/captures/2026-06-03_finals-day3/session_manifest.reprocessed.jsonl [--known-staff-file staff.txt]

It will:
- Re-run categorize_transmission + IncidentTracker (fresh) on non-noise entries using the *current* rules in edupulse/analysis.py.
- Update the sidecar .json files with new category / incident_id / students / roles.
- Write a new session_manifest.retagged.jsonl (and .reprocessed if you point at the original).

Fingerprint support:
  You can also pass --known-staff-file and --common-words-file. The staff names
  will be passed to IncidentTracker so real staff are correctly roles (not students).
  (The common words mainly help if you later re-transcribe the .wav files.)

This is the main lever for iteration when you only have the saved .wav + old transcripts.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# Make sure we can import even if run from elsewhere
import sys as _sys
from pathlib import Path as _Path
_here = _Path(__file__).resolve()
for _ in range(5):
    if (_here / "edupulse" / "__init__.py").exists():
        _sys.path.insert(0, str(_here))
        break
    _here = _here.parent

from edupulse.analysis import categorize_transmission, IncidentTracker, is_likely_noise, build_enhanced_initial_prompt

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Re-tag a previous EduPulse session manifest using current analysis rules + optional fingerprint.")
    parser.add_argument("manifest", help="Path to session_manifest*.jsonl")
    parser.add_argument("--known-staff-file", type=Path, help="File with full staff names (one per line) for correct role vs student extraction")
    parser.add_argument("--common-words-file", type=Path, help="Common words file (mainly for documentation / future re-transcribe)")
    args = parser.parse_args()

    known_staff = []
    if args.known_staff_file and args.known_staff_file.exists():
        for line in args.known_staff_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                known_staff.append(line)

    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.exists():
        print(f"Not found: {manifest_path}")
        sys.exit(1)

    session_dir = manifest_path.parent
    print(f"Re-tagging session: {session_dir}")

    entries = []
    with open(manifest_path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    tracker = IncidentTracker(known_staff_names=known_staff)
    retagged = []
    updated_sidecars = 0

    for e in entries:
        tx = e.get("transcription", "") or ""
        dur = float(e.get("duration_sec", 0))
        conf = float(e.get("whisper_conf") or 0.0)

        if e.get("is_noise") or is_likely_noise(tx, dur, conf):
            e["is_noise"] = True
            e["category"] = "Noise / Squelch / Hallucination"
            e["cat_conf"] = 0.95
            e["incident_id"] = "NOISE"
            e["students"] = []
            e["roles"] = []
        else:
            e["is_noise"] = False
            cat = categorize_transmission(tx)
            e["category"] = cat["category"]
            e["cat_conf"] = cat["confidence"]

            # fresh incident linking with current rules
            wall_dt = datetime.fromisoformat(e["start_iso"])
            inc_id = tracker.get_incident_id(tx, wall_dt, cat["category"], whisper_conf=conf, cat_conf=cat["confidence"])
            e["incident_id"] = inc_id

            ex = tracker._extract_names(tx)
            e["students"] = ex.get("students", [])
            e["roles"] = ex.get("roles", [])

        retagged.append(e)

        # Patch the sidecar if it exists
        sidecar = session_dir / e["audio_file"].replace(".wav", ".json")
        if sidecar.exists():
            try:
                with open(sidecar) as sf:
                    meta = json.load(sf)
                meta["category"] = e["category"]
                meta["cat_conf"] = e.get("cat_conf", 0.0)
                meta["incident_id"] = e["incident_id"]
                meta["students"] = e["students"]
                meta["roles"] = e["roles"]
                # keep the original real-time transcription; we didn't re-transcribe the audio
                with open(sidecar, "w") as sf:
                    json.dump(meta, sf, indent=2)
                updated_sidecars += 1
            except Exception as ex:
                print(f"  Warning: could not update {sidecar.name}: {ex}")

    out_path = manifest_path.with_name(manifest_path.stem + ".retagged.jsonl")
    with open(out_path, "w") as f:
        for e in retagged:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"Wrote {out_path}")
    print(f"Updated {updated_sidecars} sidecar JSONs with current rules.")
    print("Run the analyzer on the .retagged.jsonl to see the effect of your rule changes.")

if __name__ == "__main__":
    main()
