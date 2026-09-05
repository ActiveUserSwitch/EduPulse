#!/usr/bin/env python3
"""Compare live sidecar transcripts vs isolated offline large-v3 on the same WAVs.

Purpose
-------
When EduPulse is idle, re-transcribe capture WAVs with the heaviest model under
the *current* fingerprint prompt (and optionally with no prompt), then diff
against the stored live `transcription` field.

This answers: does live/async load change ASR, or is it the prompt / audio?

Usage (edupulse-env, EduPulse repo root)::

  PYTHONPATH=. python hardware/capture/compare_live_offline_tx.py \\
      --day 2026-09-01_school-day --limit 20

  # Gold / named clips only:
  PYTHONPATH=. python hardware/capture/compare_live_offline_tx.py \\
      --wav ~/edupulse/captures/2026-09-01_school-day/tx_2026-09-01_08-39-24_3.5s.wav \\
      --wav ~/edupulse/captures/2026-09-01_school-day/tx_2026-09-01_08-39-28_3.3s.wav

Guards: refuses to start if record_with_transcribe.py appears to be running,
unless --force.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

_repo = Path(__file__).resolve().parents[2]
if (_repo / "edupulse" / "__init__.py").is_file() and str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from edupulse.categories import build_enhanced_initial_prompt  # noqa: E402


def _edupulse_live_running() -> bool:
    try:
        out = subprocess.check_output(
            ["pgrep", "-af", "record_with_transcribe"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return False
    # pgrep can match this script's own command line; ignore self
    for line in out.splitlines():
        if "record_with_transcribe" in line and "compare_live_offline_tx" not in line:
            return True
    return False


def load_non_comment_lines(p: Path) -> list[str]:
    if not p.exists():
        return []
    out: list[str] = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def prep_audio(wav: Path) -> np.ndarray:
    import soundfile as sf

    audio, _sr = sf.read(str(wav))
    if getattr(audio, "ndim", 1) > 1 and audio.shape[1] > 1:
        rms_l = float(np.sqrt(np.mean(audio[:, 0] ** 2)))
        rms_r = float(np.sqrt(np.mean(audio[:, 1] ** 2)))
        audio = audio[:, 0] if rms_l >= rms_r else audio[:, 1]
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if peak > 1e-6:
        audio = audio / peak
    return np.asarray(audio, dtype=np.float32)


def transcribe(model, audio: np.ndarray, prompt: str | None) -> tuple[str, float]:
    segments, _info = model.transcribe(
        audio,
        beam_size=5,
        temperature=0.0,
        language="en",
        initial_prompt=prompt,
        vad_filter=False,
        condition_on_previous_text=False,
    )
    segs = list(segments)
    if not segs:
        return "", 0.0
    text = " ".join(s.text.strip() for s in segs).strip()
    conf = float(np.mean([float(np.exp(s.avg_logprob)) for s in segs]))
    return text, conf


def resolve_wavs(args: argparse.Namespace) -> list[Path]:
    wavs: list[Path] = []
    for w in args.wav or []:
        wavs.append(Path(w).expanduser().resolve())
    if args.day:
        cap = Path(args.captures).expanduser() / args.day
        found = sorted(cap.glob("tx_*.wav"))
        if args.limit and args.limit > 0:
            found = found[: args.limit]
        wavs.extend(found)
    # de-dupe preserve order
    seen: set[Path] = set()
    out: list[Path] = []
    for w in wavs:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", help="Capture day folder name under --captures")
    ap.add_argument("--wav", action="append", help="Explicit WAV path (repeatable)")
    ap.add_argument("--captures", default=str(Path.home() / "edupulse" / "captures"))
    ap.add_argument("--limit", type=int, default=0, help="Max WAVs when using --day (0=all)")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--device", default=os.environ.get("EDUPULSE_WHISPER_DEVICE", "cpu"))
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--staff-file", type=Path, default=_repo / "hardware" / "capture" / "staff_names.txt")
    ap.add_argument("--words-file", type=Path, default=_repo / "hardware" / "capture" / "common_words.txt")
    ap.add_argument(
        "--also-no-prompt",
        action="store_true",
        help="Also run a no-prompt baseline (slower; isolates prompt bias)",
    )
    ap.add_argument("--force", action="store_true", help="Run even if live capture appears active")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report path (default: ~/edupulse/reports/live_vs_offline_<stamp>.json)",
    )
    args = ap.parse_args()

    if not args.day and not args.wav:
        ap.error("Provide --day and/or --wav")

    if _edupulse_live_running() and not args.force:
        print(
            "REFUSING: record_with_transcribe appears to be running.\n"
            "Stop live EduPulse first, or pass --force if you accept contention.",
            file=sys.stderr,
        )
        return 2

    wavs = resolve_wavs(args)
    if not wavs:
        print("No WAVs found.", file=sys.stderr)
        return 1

    staff = load_non_comment_lines(args.staff_file)
    words = load_non_comment_lines(args.words_file)
    live_prompt = build_enhanced_initial_prompt(known_staff=staff, common_words=words)

    print(f"WAVs: {len(wavs)}")
    print(f"Prompt len: {len(live_prompt)}  (Yannett in prompt: {'Yannett' in live_prompt})")
    print(f"Loading {args.model} ({args.device}/{args.compute_type})...", flush=True)

    from faster_whisper import WhisperModel

    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)

    rows: list[dict] = []
    n_diff = 0
    for i, wav in enumerate(wavs, 1):
        side_path = wav.with_suffix(".json")
        live_text = ""
        live_conf = None
        live_model = None
        if side_path.exists():
            side = json.loads(side_path.read_text(encoding="utf-8"))
            live_text = (side.get("transcription") or "").strip()
            live_conf = side.get("whisper_conf")
            live_model = side.get("model")
        audio = prep_audio(wav)
        off_text, off_conf = transcribe(model, audio, live_prompt)
        row: dict = {
            "wav": str(wav),
            "live_model": live_model,
            "live_text": live_text,
            "live_conf": live_conf,
            "offline_prompt_text": off_text,
            "offline_prompt_conf": round(off_conf, 4),
            "diff_vs_live": off_text.strip() != live_text.strip(),
        }
        if args.also_no_prompt:
            np_text, np_conf = transcribe(model, audio, None)
            row["offline_noprompt_text"] = np_text
            row["offline_noprompt_conf"] = round(np_conf, 4)
            row["diff_prompt_vs_noprompt"] = np_text.strip() != off_text.strip()
        if row["diff_vs_live"]:
            n_diff += 1
        rows.append(row)
        mark = "DIFF" if row["diff_vs_live"] else "same"
        print(f"[{i}/{len(wavs)}] {mark} {wav.name}")
        print(f"  LIVE    ({live_conf}): {live_text!r}")
        print(f"  OFFLINE ({off_conf:.3f}): {off_text!r}")
        if args.also_no_prompt:
            print(f"  NOPROMPT({row['offline_noprompt_conf']}): {row['offline_noprompt_text']!r}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or (Path.home() / "edupulse" / "reports" / f"live_vs_offline_{stamp}.json")
    out = out.expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "created_utc": stamp,
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "prompt_len": len(live_prompt),
        "yannett_in_prompt": "Yannett" in live_prompt,
        "n_wavs": len(rows),
        "n_diff_vs_live": n_diff,
        "rows": rows,
    }
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{n_diff}/{len(rows)} differ from live. Report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
