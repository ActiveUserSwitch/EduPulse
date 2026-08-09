#!/usr/bin/env python3
"""Retro (or post-capture) enrichment of tx_*.json sidecars with full pyannote data.

Usage (in edupulse-env):
  python hardware/capture/enrich_pyannote_sidecars.py \
    --dir /home/joseph/edupulse/captures/2026-06-05_last-day-2 \
    --staff hardware/capture/staff_names.txt \
    --diar   # optional, slow on many files

It will call update_sidecar_with_pyannote for every tx_*.wav that has a sidecar,
adding acoustic_features, speaker_* (if DB matches), and speaker_segments (if --diar).
Backups are created on first run per file.
"""
import argparse, glob, os, sys
from pathlib import Path

# allow running from anywhere
_here = Path(__file__).resolve()
for _ in range(6):
    if (_here / "edupulse" / "__init__.py").exists():
        sys.path.insert(0, str(_here.parent.parent))
        break
    _here = _here.parent

from edupulse.speaker import update_sidecar_with_pyannote

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="Capture day dir containing tx_*.wav + sidecars")
    ap.add_argument("--staff", default="hardware/capture/staff_names.txt")
    ap.add_argument("--diar", action="store_true", help="Include full diarization (slow; default False)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    staff = []
    if Path(args.staff).exists():
        for line in open(args.staff):
            line = line.strip()
            if line and not line.startswith("#"):
                staff.append(line)

    wavs = sorted(glob.glob(os.path.join(args.dir, "tx_*.wav")))
    if args.limit:
        wavs = wavs[:args.limit]
    print(f"Enriching {len(wavs)} clips in {args.dir} (diar={args.diar}) ...")
    updated = 0
    for w in wavs:
        if update_sidecar_with_pyannote(w, include_diar=args.diar, known_staff=staff or None, backup=True):
            updated += 1
            if updated % 20 == 0: print(f"  {updated}...")
    print(f"Done. Updated {updated} sidecars. Pyannote data (acoustic + speaker + optional segments) now in sidecars.")
    print("Use --diar on a small set or interesting clips for full speaker_segments.")

if __name__ == "__main__":
    main()
