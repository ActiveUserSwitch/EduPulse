#!/usr/bin/env python3
"""
Quick post-run analyzer for a session_manifest.jsonl produced by record_with_transcribe.py.

Usage:
    python hardware/capture/analyze_manifest.py ~/edupulse/captures/2026-06-05_finals-day3/session_manifest.jsonl

Prints basic stats + top categories + INC distribution. Easy to extend with more pandas-less analysis.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_manifest.py path/to/session_manifest.jsonl")
        sys.exit(1)

    path = Path(sys.argv[1]).expanduser()
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    txs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    txs.append(json.loads(line))
                except Exception:
                    pass

    if not txs:
        print("No entries found.")
        return

    noise = [t for t in txs if t.get("is_noise")]
    real = [t for t in txs if not t.get("is_noise")]
    print(f"Manifest: {path}")
    print(f"Transmissions: {len(txs)}  (noise/halluc: {len(noise)}, usable: {len(real)})")

    total_dur = sum(t.get("duration_sec", 0) for t in txs)
    print(f"Total speech seconds: {total_dur:.1f}")

    cats = Counter(t.get("category", "Other / Unclear") for t in txs)
    print("\nBy category:")
    for cat, cnt in cats.most_common():
        print(f"  {cnt:4d}  {cat}")

    inc_counts = Counter(t.get("incident_id") for t in real if t.get("incident_id"))
    print(f"\nUnique INC-xxx (excluding NOISE): {len(inc_counts)}")
    print("Longest conversations (tx count per INC, real only):")
    for inc, cnt in inc_counts.most_common(10):
        print(f"  {inc}: {cnt}")

    # Student mentions
    all_students = []
    for t in real:
        all_students.extend(t.get("students", []))
    if all_students:
        print("\nMost mentioned students (from full-name extraction, real tx only):")
        for name, cnt in Counter(all_students).most_common(10):
            print(f"  {cnt:3d}  {name}")

    # Roles
    all_roles = []
    for t in real:
        all_roles.extend(t.get("roles", []))
    if all_roles:
        print("\nMost seen roles/titles (incl. JROTC/Athletic tags, real tx only):")
        for role, cnt in Counter(all_roles).most_common(15):
            print(f"  {cnt:3d}  {role}")

    # Data Quality summary — critical for the compressed last-two-days timeline + 3-month break
    total = len(txs)
    usable = len(real)
    noise = len(noise)
    usable_pct = (100 * usable / total) if total else 0
    meaningful = [t for t in real if t.get("students") or t.get("category") not in ("Other / Unclear", "Noise / Squelch / Hallucination")]
    print("\n=== DATA QUALITY SUMMARY (for rapid go/no-go on remaining runs) ===")
    print(f"Usable transmissions: {usable} / {total} ({usable_pct:.1f}%)")
    print(f"  Noise-flagged: {noise}")
    print(f"  'Meaningful' (had student mention or non-Other category): {len(meaningful)}")
    real_incs = [t["incident_id"] for t in real if t.get("incident_id") and not str(t.get("incident_id")).startswith("NOISE")]
    inc_with_content = len(set(real_incs))
    print(f"Real INC-xxx with at least one usable tx: {inc_with_content}")
    if usable_pct < 70:
        print("  >>> WARNING: High noise rate. Focus next run on gain staging (watch q~ in live line) before full day.")
    elif len(meaningful) < 20:
        print("  >>> Low meaningful yield. Good for raw audio collection, but limited for immediate analysis.")
    else:
        print("  Looks solid for both collection and quick post-run review.")
    print("==================================================================")

    print("\n(For deeper analysis load the jsonl + sidecar .json files into pandas or your notebook.)")
    print("For the 3-month break: the .wav files + reprocessed manifest are your main assets for offline heavier models + rule tuning.")
    print("See hardware/capture/LAST_TWO_DAYS_AND_BREAK_PLAN.md for the explicit remaining schedule and offline iteration guidance.")


if __name__ == "__main__":
    main()
