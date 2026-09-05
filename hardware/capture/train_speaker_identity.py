#!/usr/bin/env python3
"""Batch-train / reinforce EduPulse speaker identity from existing captures.

Walks ~/edupulse/captures (or --base-dir), and for each tx_*.wav with a usable
transcript:

  1. Parse radio protocol ("Name1 to Name2", "Go for Name2")
  2. Enroll voice embeddings into ~/edupulse/speaker_db.pkl
  3. Identify the clip and write primary_speaker / speaker_* into the sidecar

Prefer large-v3 transcripts; optionally include other models with --include-light
and a confidence floor (tiny garbage can poison enrollment).

Examples:
  PYTHONPATH=. python hardware/capture/train_speaker_identity.py
  PYTHONPATH=. python hardware/capture/train_speaker_identity.py --day 2026-08-26_school-day
  PYTHONPATH=. python hardware/capture/train_speaker_identity.py --include-light --min-conf 0.65
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_repo = Path(__file__).resolve().parents[2]
if (_repo / "edupulse" / "__init__.py").is_file() and str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from edupulse.speaker import (
    default_speaker_db_path,
    get_persistent_speaker_database,
    process_transmission_speaker,
)


def load_staff(path: Path) -> list[str]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def usable_transcript(meta: dict, *, include_light: bool, min_conf: float) -> bool:
    text = (meta.get("transcription") or "").strip()
    if not text:
        return False
    # Skip obvious multilingual junk
    if any(ord(ch) > 0x2E80 for ch in text):
        return False
    model = (meta.get("model") or "").strip()
    conf = meta.get("whisper_conf")
    try:
        conf_f = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf_f = None
    if model == "large-v3":
        return True
    if not include_light:
        return False
    if conf_f is None:
        return False
    return conf_f >= min_conf


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-dir", default=str(Path.home() / "edupulse" / "captures"))
    ap.add_argument("--day", help="Only this day subdirectory")
    ap.add_argument("--db-path", default=str(default_speaker_db_path()))
    ap.add_argument(
        "--staff-file",
        default=str(_repo / "hardware" / "capture" / "staff_names.txt"),
    )
    ap.add_argument(
        "--include-light",
        action="store_true",
        help="Also use non-large-v3 transcripts above --min-conf",
    )
    ap.add_argument("--min-conf", type=float, default=0.65)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-write-sidecars", action="store_true")
    ap.add_argument(
        "--enroll-sequential",
        action="store_true",
        help="Experimental: enroll next TX after a call as the callee. "
        "OFF by default — often wrong when others key up first.",
    )
    args = ap.parse_args()

    base = Path(args.base_dir).expanduser().resolve()
    staff = load_staff(Path(args.staff_file))
    print(f"[staff] {len(staff)} names from {args.staff_file}")
    print(f"[db] {args.db_path}")

    db = get_persistent_speaker_database(path=args.db_path)
    if db is None:
        print("ERROR: speaker embedder unavailable (pyannote embedding + HF token required)")
        sys.exit(1)
    print(f"[db] starting with {len(db.known_speakers())} profiles: {db.known_speakers()[:12]}")

    days = []
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        if args.day and p.name != args.day:
            continue
        if list(p.glob("tx_*.wav")):
            days.append(p)

    stats = Counter()
    enrolled_total = Counter()
    identified = 0
    processed = 0

    for ddir in days:
        wavs = sorted(ddir.glob("tx_*.wav"))
        print(f"\n=== {ddir.name} ({len(wavs)} WAVs) ===")
        pending_callee: str | None = None
        for wav in wavs:
            if args.limit and processed >= args.limit:
                break
            side = wav.with_suffix(".json")
            meta = {}
            if side.exists():
                try:
                    meta = json.loads(side.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            if not usable_transcript(meta, include_light=args.include_light, min_conf=args.min_conf):
                stats["skipped"] += 1
                # Still advance/clear pending? Skip without consuming pending —
                # only real candidate txs participate in the call/answer chain.
                continue

            text = (meta.get("transcription") or "").strip()
            stats["candidates"] += 1

            if args.dry_run:
                print(f"  [dry] {wav.name}: {text[:70]} | pending={pending_callee}")
                processed += 1
                continue

            spk = process_transmission_speaker(
                str(wav),
                text,
                staff,
                db=db,
                db_path=args.db_path,
                persist=False,  # save once at end / periodically
                pending_callee=pending_callee,
                enroll_sequential=bool(args.enroll_sequential),
            )
            pending_callee = spk.get("pending_callee_out")
            for name in spk.get("enrolled") or []:
                enrolled_total[name] += 1
                stats["enroll_events"] += 1
            if spk.get("likely_speaker_conf") == "gold":
                stats["gold_pairs"] += 1
            if spk.get("primary_speaker") and spk.get("speaker_source") == "voice":
                identified += 1
                stats["voice_id"] += 1
            elif spk.get("primary_speaker"):
                stats["text_or_protocol_id"] += 1

            if not args.no_write_sidecars:
                meta = dict(meta)
                meta["likely_speaker"] = spk.get("likely_speaker")
                meta["likely_speaker_conf"] = spk.get("likely_speaker_conf")
                meta["primary_speaker"] = spk.get("primary_speaker")
                meta["speaker_conf"] = spk.get("speaker_conf")
                meta["speaker_source"] = spk.get("speaker_source")
                meta["radio_caller"] = spk.get("caller")
                meta["radio_callee"] = spk.get("callee") or spk.get("addressed")
                if spk.get("enrolled"):
                    meta["speaker_enrolled"] = spk.get("enrolled")
                try:
                    side.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                except Exception as e:
                    print(f"  WARN sidecar write {wav.name}: {e}")

            processed += 1
            if processed % 50 == 0:
                try:
                    db.save_session(args.db_path)
                except Exception:
                    pass
                print(
                    f"  … {processed} clips | profiles={len(db.known_speakers())} "
                    f"| voice_ids={identified} | enroll_events={stats['enroll_events']} "
                    f"| gold={stats['gold_pairs']} seq={stats['sequential']}"
                )

        if args.limit and processed >= args.limit:
            break

    try:
        db.save_session(args.db_path)
    except Exception as e:
        print(f"WARN: final DB save failed: {e}")

    print("\n===== DONE =====")
    print(f"processed={processed} skipped={stats['skipped']} candidates={stats['candidates']}")
    print(f"enroll_events={stats['enroll_events']} voice_id={stats['voice_id']} "
          f"text/protocol_id={stats['text_or_protocol_id']}")
    print(f"gold_answer_pairs={stats['gold_pairs']} sequential_answers={stats['sequential']}")
    print(f"profiles={len(db.known_speakers())}: {db.known_speakers()}")
    if enrolled_total:
        print("top enroll reinforcements:")
        for name, n in enrolled_total.most_common(15):
            print(f"  {n:4d}  {name}")
    print(f"DB saved → {args.db_path}")


if __name__ == "__main__":
    main()
