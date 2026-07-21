#!/usr/bin/env python3
"""
Helper to organize re-transcribed sidecars into the processed/ model hierarchy.

Usage:
  python validation/organize_model_outputs.py \
    --source-dir /tmp/retranscribed_largev3 \
    --day 2026-06-05_last-day-2 \
    --model large-v3 \
    --copy-wavs   # optional

It will copy matching tx_*.json (and optionally .wav) into
~/edupulse/processed/<day>/<model>/
"""
import argparse, os, shutil, glob, json
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source-dir", required=True, help="Directory containing new tx_*.json from test_whisper.py")
    p.add_argument("--day", required=True, help="e.g. 2026-06-05_last-day-2")
    p.add_argument("--model", required=True, choices=["tiny","base","medium","large-v3"])
    p.add_argument("--copy-wavs", action="store_true")
    p.add_argument("--processed-root", default=os.path.expanduser("~/edupulse/processed"))
    args = p.parse_args()

    dest = os.path.join(args.processed_root, args.day, args.model)
    os.makedirs(dest, exist_ok=True)

    src_jsons = glob.glob(os.path.join(args.source_dir, "tx_*.json"))
    print(f"Found {len(src_jsons)} json in source")

    copied = 0
    for j in src_jsons:
        base = os.path.basename(j)
        shutil.copy2(j, os.path.join(dest, base))
        if args.copy_wavs:
            wav = j.replace(".json", ".wav")
            if os.path.exists(wav):
                shutil.copy2(wav, os.path.join(dest, os.path.basename(wav)))
        copied += 1
    print(f"Copied {copied} files into {dest}")

    # Optional: update a manifest in the manifests/ dir if you want to track
    print("Done. Next: run retag_session.py on the day if you want updated categories/incidents.")

if __name__ == "__main__":
    main()
