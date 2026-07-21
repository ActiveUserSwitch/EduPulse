#!/usr/bin/env python3
"""
Robust retro upgrade for all capture days to large-v3 transcription + sidecar + pyannote.

Run inside the edupulse-env:
  cd /home/joseph/Documents/GrokBuild
  source ~/edupulse-env/bin/activate
  PYTHONPATH=. python hardware/capture/retro_upgrade_sidecars.py --day 2026-06-05_last-day-2

It will:
- For WAVs whose sidecar is not yet large-v3 (or --force), run large-v3 transcription using the exact same audio prep + fingerprint logic as the project.
- Update the sidecar JSON in the capture dir with model, transcription, conf.
- Re-apply categorization and staff/role extraction from edupulse.analysis using the new heavy text.
- Call the pyannote enrichment (acoustic_features, primary_speaker, speaker_segments if --include-diar).
- Preserve original capture metadata (levels, start_iso, duration, old incident if any).
- After all files for a day dir have been processed, call batch_populate_information_scores
  (unless --skip-pyannote or --skip-batch-info-scores). This creates/populates the
  "information_score" (and acoustic_zscores) fields using the hand-coded-day-onward
  reference, exactly as requested: populate when we batch the day's files; later
  re-aggregate when more days reach "complete" sampling.

This brings every day up to the current standard (heavy trans + full pyannote data + batch information scores in sidecars next to the WAVs).
Scope note: information scores / z use only the clean 2026-06-05+ corpus as reference.
"""
import argparse
import glob
import json
import os
import re
import sys
import wave
from pathlib import Path

# Path setup so "import edupulse..." works when invoked as python hardware/capture/...
_here = Path(__file__).resolve()
for _ in range(8):
    if (_here / "edupulse" / "__init__.py").exists():
        if str(_here.parent.parent) not in sys.path:
            sys.path.insert(0, str(_here.parent.parent))
        break
    _here = _here.parent

from edupulse.analysis import (
    batch_populate_information_scores,
    build_enhanced_initial_prompt,
    categorize_transmission,
    extract_staff_mentions,
)
try:
    from edupulse.speaker import update_sidecar_with_pyannote, get_pyannote_enrichment
except Exception:
    update_sidecar_with_pyannote = None
    get_pyannote_enrichment = None

def load_non_comment_lines(p: Path):
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out

def get_wav_duration(wav: Path) -> float:
    try:
        with wave.open(str(wav), "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        m = re.search(r"_([\d.]+)s\.wav$", wav.name)
        return float(m.group(1)) if m else 0.0

def transcribe_large_v3(wav_path: Path, staff_names: list[str], common_words: list[str]) -> tuple[str, float]:
    """Perform the heavy transcription exactly like the project's test + recorder path."""
    try:
        from faster_whisper import WhisperModel
        import soundfile as sf
        import numpy as np
    except ImportError as e:
        raise RuntimeError(f"faster-whisper / soundfile not available in this env: {e}")

    effective_prompt = build_enhanced_initial_prompt(base=None, known_staff=staff_names, common_words=common_words)

    # Audio prep identical to test_whisper.py (dominant channel + normalize)
    audio, sr = sf.read(str(wav_path))
    if audio.ndim > 1 and audio.shape[1] > 1:
        rms_l = np.sqrt(np.mean(audio[:, 0]**2))
        rms_r = np.sqrt(np.mean(audio[:, 1]**2))
        audio = audio[:, 0] if rms_l > rms_r else audio[:, 1]
    peak = np.max(np.abs(audio))
    if peak > 1e-6:
        audio = audio / peak

    model = WhisperModel("large-v3", device="cpu", compute_type="int8")

    segments, info = model.transcribe(
        audio,
        beam_size=5,
        temperature=0.0,
        initial_prompt=effective_prompt,
        language="en",
        vad_filter=False,
        condition_on_previous_text=False,
    )

    text_parts = []
    confs = []
    for seg in segments:
        text_parts.append(seg.text.strip())
        confs.append(float(np.exp(seg.avg_logprob)))

    full = " ".join(text_parts).strip()
    avg_conf = sum(confs) / len(confs) if confs else 0.0
    return full, round(avg_conf, 4)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", default=str(Path.home() / "edupulse" / "captures"))
    ap.add_argument("--day", help="Process only this day subdir")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-pyannote", action="store_true")
    ap.add_argument("--include-diar", action="store_true")
    ap.add_argument("--skip-batch-info-scores", action="store_true",
                    help="Skip the batch information_score / acoustic_zscores population step (normally runs after pyannote when a day's files have been processed together).")
    args = ap.parse_args()

    base = Path(args.base_dir).expanduser().resolve()
    project = Path(__file__).resolve().parent.parent

    # Hardcoded for this environment (GrokBuild tree); the script will also work if run from project root with correct relative.
    staff_path = Path("/home/joseph/Documents/GrokBuild/hardware/capture/staff_names.txt")
    common_path = Path("/home/joseph/Documents/GrokBuild/hardware/capture/common_words.txt")
    staff_names = load_non_comment_lines(staff_path)
    common_words = load_non_comment_lines(common_path)
    print(f"[fingerprints] staff={len(staff_names)} common={len(common_words)}")

    # Discover day dirs
    day_dirs = []
    for p in sorted(base.iterdir()):
        if p.is_dir() and list(p.glob("tx_*.wav")):
            if args.day and p.name != args.day:
                continue
            day_dirs.append(p)

    processed = 0
    for ddir in day_dirs:
        wavs = sorted(ddir.glob("tx_*.wav"))
        if args.limit > 0:
            wavs = wavs[:args.limit]
        print(f"\n=== {ddir.name} ({len(wavs)} WAVs) ===")

        for wav in wavs:
            side = wav.with_suffix(".json")
            old = {}
            if side.exists():
                try:
                    old = json.loads(side.read_text())
                except Exception:
                    old = {}
            if old.get("model") == "large-v3" and not args.force:
                continue

            if args.dry_run:
                print(f"  [dry] {wav.name}")
                continue

            print(f"  {wav.name} ...", end=" ", flush=True)

            # 1. Heavy transcription
            try:
                trans, conf = transcribe_large_v3(wav, staff_names, common_words)
            except Exception as e:
                print(f"TRANS FAIL: {e}")
                continue

            # 2. Update meta (preserve old capture fields)
            meta = dict(old)
            meta["audio_file"] = wav.name
            meta["model"] = "large-v3"
            meta["transcription"] = trans
            meta["whisper_conf"] = conf
            if "duration_sec" not in meta or meta.get("duration_sec", 0) == 0:
                meta["duration_sec"] = round(get_wav_duration(wav), 2)

            # 3. Re-analyze with heavy text
            try:
                cat = categorize_transmission(trans)
                meta["category"] = cat["category"]
                meta["cat_conf"] = round(cat.get("confidence", 0), 4)
                mentions = extract_staff_mentions(trans, staff_names)
                students = [m for m in mentions if not any(tt in m for tt in ("Mr.", "Ms.", "Dr.", "Mrs.", "Miss", "Sergeant", "Captain", "Nurse", "Deputy", "Officer"))]
                roles = [m for m in mentions if m not in students]
                meta["students"] = students
                meta["roles"] = roles
            except Exception as e:
                print(f" (analysis warn: {e})", end="")

            # Write trans sidecar
            side.write_text(json.dumps(meta, indent=2), encoding="utf-8")

            # 4. Pyannote enrich (if available)
            if not args.skip_pyannote and update_sidecar_with_pyannote is not None:
                try:
                    update_sidecar_with_pyannote(str(wav), include_diar=args.include_diar, known_staff=staff_names, backup=False)
                except Exception as e:
                    print(f" (pyannote warn: {e})", end="")

            processed += 1
            print(f"OK (conf={conf:.2f})")

        # 5. Batch-populate information_score (and acoustic_zscores) for the day's files.
        #    This fulfills: create the field if missing and populate it when we have
        #    batched all (or the complete set of) the day's files. The reference is the
        #    current hand-coded onward "complete" set. Re-run later (manually or via
        #    retro on the set) when more days reach "complete" to re-aggregate.
        if not args.skip_pyannote and not args.skip_batch_info_scores:
            try:
                batch_populate_information_scores(str(ddir))
            except Exception as e:
                print(f" (batch-info warn: {e})", end="")

    print(f"\nDone. Processed {processed} clips this invocation.")
    print("Re-invoke for other --day or without --limit to finish the full set. Future live captures are already large-v3 + enriched.")
    print("information_score / z fields are populated only in batch mode at complete sampling (no live z-scores).")

if __name__ == "__main__":
    main()
