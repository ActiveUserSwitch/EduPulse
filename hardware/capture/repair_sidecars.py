#!/usr/bin/env python3
"""Offline LLM repair of Whisper transcripts on capture sidecars.

Uses the full school lexicon (not Whisper's 223-token budget) via SpaceXAI.

  PYTHONPATH=. python hardware/capture/repair_sidecars.py --day 2026-09-04_school-day
  edupulse repair-tx --day 2026-09-04_school-day --only-low-conf
  edupulse repair-tx --wav ~/edupulse/captures/.../tx_....wav --dry-run

Default backend is **local Ollama** (no api.x.ai token bill). Optional:
  --backend queue   enqueue for Grok Build / grokbot (subscription you already pay)
  --backend xai     metered developer API (needs XAI_API_KEY) — opt-in only

Skips noise sidecars by default.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[2]
if (_repo / "edupulse" / "__init__.py").is_file() and str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from edupulse.lexicon import build_lexicon  # noqa: E402
from edupulse.transcript_repair import (  # noqa: E402
    DEFAULT_BACKEND,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_XAI_MODEL,
    repair_transcript,
)


def _load_staff(path: Path) -> list[str]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def resolve_jsons(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    for w in args.wav or []:
        wav = Path(w).expanduser().resolve()
        paths.append(wav.with_suffix(".json"))
    if args.day:
        day = Path(args.captures).expanduser() / args.day
        found = sorted(day.glob("tx_*.json"))
        if args.limit and args.limit > 0:
            found = found[: args.limit]
        paths.extend(found)
    # dedupe
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", help="Capture day folder under --captures")
    ap.add_argument("--wav", action="append", help="WAV path (sidecar = same stem .json)")
    ap.add_argument("--captures", default=str(Path.home() / "edupulse" / "captures"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--backend",
        default=DEFAULT_BACKEND,
        choices=["ollama", "queue", "xai"],
        help="ollama=local free (default); queue=Grok Build/grokbot job file; xai=metered api.x.ai",
    )
    ap.add_argument(
        "--model",
        default=None,
        help=f"Model id (ollama default {DEFAULT_OLLAMA_MODEL}; xai default {DEFAULT_XAI_MODEL})",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="Re-repair even if transcription_repair already set")
    ap.add_argument("--only-low-conf", action="store_true", help="Only whisper_conf < --conf-threshold")
    ap.add_argument("--conf-threshold", type=float, default=0.55)
    ap.add_argument("--include-noise", action="store_true")
    ap.add_argument("--apply", action="store_true",
                    help="Write corrected text into transcription (default: only fill transcription_repair)")
    args = ap.parse_args()
    if not args.day and not args.wav:
        ap.error("Provide --day and/or --wav")

    jsons = resolve_jsons(args)
    if not jsons:
        print("No sidecars found.", file=sys.stderr)
        return 1

    day_dir = jsons[0].parent
    lex = build_lexicon(capture_root=day_dir)
    print(f"Lexicon: {lex.stats()}")
    print(f"Sidecars: {len(jsons)}  backend={args.backend}  model={args.model or '(default)'}  dry_run={args.dry_run}")
    if args.backend == "xai":
        print("WARNING: --backend xai uses metered api.x.ai (not SuperGrok / Grok Build).", file=sys.stderr)

    staff = _load_staff(_repo / "hardware" / "capture" / "staff_names.txt")
    n_changed = 0
    n_skip = 0
    n_err = 0

    for i, jp in enumerate(jsons, 1):
        if not jp.exists():
            print(f"[{i}] MISSING {jp}")
            n_err += 1
            continue
        side = json.loads(jp.read_text(encoding="utf-8"))
        if side.get("is_noise") and not args.include_noise:
            n_skip += 1
            continue
        if side.get("transcription_repair") and not args.force and not args.dry_run:
            n_skip += 1
            continue
        conf = side.get("whisper_conf")
        if args.only_low_conf and conf is not None and float(conf) >= args.conf_threshold:
            n_skip += 1
            continue

        text = (side.get("transcription") or side.get("transcription_raw") or "").strip()
        if not text:
            n_skip += 1
            continue

        result = repair_transcript(
            text,
            lex,
            backend=args.backend,
            model=args.model,
            dry_run=args.dry_run,
            queue_meta={"sidecar": str(jp), "whisper_conf": conf},
        )
        mark = "CHANGE" if result.changed else ("SKIP" if result.skipped else "same")
        print(f"[{i}/{len(jsons)}] {mark} {jp.name} conf={conf}")
        print(f"  in : {text!r}")
        if result.changed or result.skipped:
            print(f"  out: {result.corrected!r}  ({result.skip_reason or result.rationale})")

        if result.skipped and result.skip_reason not in ("dry_run",) and not str(result.skip_reason).startswith("queued:"):
            if args.backend == "xai" and (
                "XAI_API_KEY" in (result.skip_reason or "") or "openai" in (result.skip_reason or "")
            ):
                print(f"ABORT: {result.skip_reason}", file=sys.stderr)
                return 2
            if args.backend == "ollama" and "ollama_unreachable" in (result.skip_reason or ""):
                print(f"ABORT: {result.skip_reason}", file=sys.stderr)
                return 2
            n_err += 1
            continue

        if args.dry_run:
            if result.changed:
                n_changed += 1
            continue

        # Preserve whisper-era string once
        if not side.get("transcription_whisper"):
            side["transcription_whisper"] = text
        side["transcription_repair"] = result.as_dict()
        if args.apply and result.changed:
            side["transcription"] = result.corrected
            # Refresh protocol hints when possible
            try:
                from edupulse.semantic_map import parse_radio_call

                parsed = parse_radio_call(result.corrected, staff)
                if parsed.get("caller"):
                    side["radio_caller"] = parsed["caller"]
                if parsed.get("callee"):
                    side["radio_callee"] = parsed["callee"]
                if parsed.get("likely_speaker"):
                    side["likely_speaker"] = parsed["likely_speaker"]
                    side["likely_speaker_conf"] = parsed.get("likely_speaker_conf")
            except Exception:
                pass
            n_changed += 1
        elif result.changed:
            n_changed += 1

        jp.write_text(json.dumps(side, indent=2), encoding="utf-8")

    print(f"\nDone. changed={n_changed} skipped={n_skip} errors={n_err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
