#!/usr/bin/env python3
"""
EduPulse Speaker / Voice Recognition Explorer (skeleton)

Important reality for this project:
On these radio calls, people usually say the *other person's* name ("Dr. Strickland,
this is Moore" or "Mr. Moore to Dr. Strickland"). The speaker is often the caller,
not the person named in the transcript.

Therefore:
- Text is used *only* for rare high-confidence self-identification moments
  ("Go for Strickland", "This is X").
- The main signal for figuring out who is speaking must come from the voice
  itself (acoustic embedding / parameters from pyannote).

After you run:
    sudo apt update && sudo apt install ffmpeg
    pip install pyannote.audio     # inside the edupulse venv

You still need to accept the gated models:
    https://huggingface.co/pyannote/embedding
    https://huggingface.co/pyannote/speaker-diarization-3.1

Provide the token either by:
    export HF_TOKEN=hf_...
or (recommended for this project) save it to a file named HuggingFaceToken.txt
in the GrokBuild root, your home dir, or hardware/capture/.

This script (and the whole speaker skeleton) will auto-discover the token file,
just like it auto-discovers staff_names.txt. It will then use real voice
embeddings for identification and clustering.

Safe to run without models (falls back to text-only stats). The code prints
clear instructions the first time a model load fails.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

# Make "import edupulse..." work when running the script directly (python test/test_speaker.py)
# without requiring installation or PYTHONPATH hacks.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# We import from the skeleton so the whole thing stays optional.
try:
    from edupulse.speaker import (
        SpeakerDiarizer,
        SpeakerDatabase,
        get_speaker_database,
        get_speaker_diarizer,
        build_speaker_feasibility_report,
        SpeakerEmbedder,
    )
except Exception as e:
    print(f"Could not import edupulse.speaker: {e}")
    raise


def load_staff_names(path: str | Path | None = None) -> list[str]:
    """Load the authoritative Title First Last list.

    Searches a few sensible locations (CLI arg, CWD, script-relative upward,
    hardware/capture inside the source tree) so normal usage needs zero flags.
    """
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    # Common relative + repo locations
    candidates.extend([
        Path.cwd() / "hardware/capture/staff_names.txt",
        Path.cwd() / "staff_names.txt",
        Path(__file__).resolve().parent.parent / "hardware" / "capture" / "staff_names.txt",
    ])
    for p in candidates:
        if p.exists():
            names = []
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    names.append(line)
            if names:
                return names
    print("WARNING: no staff_names.txt found in searched locations; using empty list.")
    return []


def load_transcripts_for_dir(wav_dir: str | Path | None, transcripts_txt: str | Path | None = None) -> dict[str, str]:
    """Return {wav_basename: transcript}.

    Priority sources:
    1. Explicit --transcripts txt (the clean graduation_largev3_transcripts.txt style)
    2. Sidecar tx_*.json under wav_dir (prefers "transcription"; only trusts heavy model if present)
    3. Validation CSVs present in the tree (focused_transcription_validation.csv and
       graduation_vad_transcription_focused.csv) — perfect for demo runs with no external data.
    """
    mapping: dict[str, str] = {}

    # 1. Clean transcripts txt (user-produced after large-v3 batch)
    if transcripts_txt and Path(transcripts_txt).exists():
        current = None
        buf: list[str] = []
        for line in Path(transcripts_txt).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.rstrip()
            if line.startswith("tx_") and ".wav" in line:
                if current:
                    mapping[current] = " ".join(buf).strip()
                current = line.strip()
                buf = []
            elif current and line.strip() and not line.startswith("  ") and not line.startswith("="):
                buf.append(line.strip())
        if current:
            mapping[current] = " ".join(buf).strip()
        if mapping:
            return mapping

    # 2. Sidecars in a capture/processed dir (heavy-model only policy respected at write time)
    if wav_dir:
        wd = Path(wav_dir)
        for j in sorted(glob.glob(str(wd / "tx_*.json"))):
            try:
                with open(j, encoding="utf-8", errors="ignore") as f:
                    d = json.load(f)
                wav = d.get("audio_file") or Path(j).with_suffix(".wav").name
                model = d.get("model", "")
                txt = d.get("transcription", "") or ""
                # Prefer heavy; still accept if no model field (old sidecars) but warn later
                if txt:
                    mapping[wav] = txt
            except Exception:
                pass
        if mapping:
            return mapping

    # 3. Demo sources inside the repo (validation focused CSVs have real human + large3 transcripts)
    #    This lets you exercise the full skeleton + report writer with zero external files.
    demo_csvs = [
        Path(__file__).resolve().parent.parent / "validation" / "focused_transcription_validation.csv",
        Path(__file__).resolve().parent.parent / "validation" / "graduation_vad_transcription_focused.csv",
        Path.cwd() / "validation" / "focused_transcription_validation.csv",
    ]
    for csvp in demo_csvs:
        if csvp.exists():
            try:
                # Very small parser: look for human_transcript or transcription / large3_transcript columns
                text = csvp.read_text(encoding="utf-8", errors="ignore")
                lines = [ln for ln in text.splitlines() if ln.strip()]
                if not lines:
                    continue
                header = [h.strip().lower() for h in lines[0].split(",")]
                # Find likely wav id col and transcript col
                wav_idx = next((i for i, h in enumerate(header) if "wav" in h or "transmission" in h), 0)
                # Prefer human gold, then large3, then plain transcription
                txt_idx = None
                for pref in ("human_transcript", "large3_transcript", "transcription"):
                    if pref in header:
                        txt_idx = header.index(pref)
                        break
                if txt_idx is None:
                    # last resort: any col with "transcript" in name
                    txt_idx = next((i for i, h in enumerate(header) if "transcript" in h), None)
                if txt_idx is None:
                    continue
                for ln in lines[1:]:
                    parts = [p.strip() for p in ln.split(",")]
                    if len(parts) <= max(wav_idx, txt_idx):
                        continue
                    wav = parts[wav_idx]
                    if not wav or not wav.startswith("tx_"):
                        continue
                    if wav not in mapping:  # first source wins
                        mapping[wav] = parts[txt_idx].strip('"').strip()
                if mapping:
                    print(f"(using demo transcripts from {csvp.name})")
                    return mapping
            except Exception:
                pass

    return mapping


def canonicalize_name(raw: str, known_staff: list[str]) -> str:
    """Map whatever the user typed ('Mr. Moore', 'Moore', 'eldridge moore') to the
    authoritative 'Title First Last' entry from staff_names.txt when possible.
    Falls back to the raw string with simple title normalization.
    """
    if not raw:
        return raw
    r = raw.strip()
    rlow = r.lower()

    # exact
    for n in known_staff:
        if n.lower() == rlow:
            return n

    # last name with or without title
    last = r.split()[-1].lower()
    title = ""
    for tok in ("mr.", "mr", "ms.", "ms", "mrs.", "mrs", "miss", "dr.", "dr", "deputy", "officer", "sergeant", "sgt", "captain", "capt", "nurse"):
        if rlow.startswith(tok):
            title = tok.title().replace(".", "") + ". " if tok.endswith(".") or tok in ("mr","ms","dr") else tok.title() + " "
            break
    for n in known_staff:
        if n.lower().endswith(" " + last) or n.lower().split()[-1] == last:
            # keep the title from the authoritative list
            return n

    # fallback: if user gave "Mr. Moore" keep it, else try to pretty it
    if any(rlow.startswith(t) for t in ("mr.", "ms.", "dr.", "mr ", "ms ", "dr ")):
        return r
    return r


def load_transcript_lookup() -> dict[str, str]:
    """Build a best-effort {tx_basename: transcript} from the focused validation CSVs.
    Prefers human_transcript when present, falls back to large3 / transcription.
    """
    lookup: dict[str, str] = {}
    csvs = [
        Path(__file__).resolve().parent.parent / "validation" / "focused_transcription_validation.csv",
        Path(__file__).resolve().parent.parent / "validation" / "graduation_vad_transcription_focused.csv",
        Path.cwd() / "validation" / "focused_transcription_validation.csv",
        Path.cwd() / "validation" / "graduation_vad_transcription_focused.csv",
    ]
    for csvp in csvs:
        if not csvp.exists():
            continue
        try:
            text = csvp.read_text(encoding="utf-8", errors="ignore")
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if not lines:
                continue
            header = [h.strip().lower() for h in lines[0].split(",")]
            # find wav col
            wav_idx = next((i for i, h in enumerate(header) if "wav" in h or "transmission" in h), 0)
            # transcript preference
            txt_idx = None
            for pref in ("human_transcript", "large3_transcript", "transcription", "transcript"):
                if pref in header:
                    txt_idx = header.index(pref)
                    break
            if txt_idx is None:
                txt_idx = next((i for i, h in enumerate(header) if "transcript" in h), None)
            if txt_idx is None:
                continue
            for ln in lines[1:]:
                parts = [p.strip() for p in ln.split(",")]
                if len(parts) <= max(wav_idx, txt_idx):
                    continue
                wav = parts[wav_idx]
                if not wav or not wav.startswith("tx_"):
                    continue
                txt = parts[txt_idx].strip('"').strip()
                if wav not in lookup or "human" in header[txt_idx]:  # human wins
                    lookup[wav] = txt
        except Exception:
            pass
    return lookup


def load_day_cache(label: str) -> dict[str, "np.ndarray | None"]:
    """Load a precomputed day embedding cache (created by earlier runs or test code)."""
    import pickle

    candidates = [
        f"/tmp/edupulse_embeddings_{label}.pkl",
        f"/tmp/edupulse_{label}_embeddings.pkl",
    ]
    for p in candidates:
        if os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    data = pickle.load(f)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return {}


def search_and_report(
    db: SpeakerDatabase,
    query_name: str,
    day_caches: dict[str, dict[str, "np.ndarray"]],
    transcript_lookup: dict[str, str],
    high_threshold: float = 0.70,
    mid_threshold: float = 0.55,
) -> None:
    """Print a human-friendly report of clips whose voice is similar to the query speaker."""
    print(f"\n=== Voice search for '{query_name}' (mean profile from {len(db._db.get(query_name, []))} samples) ===")
    profile = db.mean_embedding_for(query_name)
    if profile is None:
        print("No profile for that speaker yet.")
        return

    all_hits: list[tuple[str, str, float]] = []  # (day, tx, score)
    for day_label, clip_embs in day_caches.items():
        hits = db.search_clips(
            query_name,
            clip_embs,
            threshold=mid_threshold,
            top_k=25,
            exclude=set(),  # caller can pass the anchor if desired
        )
        for tx, sc in hits:
            all_hits.append((day_label, tx, sc))

    all_hits.sort(key=lambda x: x[2], reverse=True)

    high = [(d, t, s) for (d, t, s) in all_hits if s >= high_threshold]
    mid = [(d, t, s) for (d, t, s) in all_hits if mid_threshold <= s < high_threshold]

    print(f"High-confidence (cos >= {high_threshold}): {len(high)}")
    for day, tx, sc in high[:8]:
        txt = transcript_lookup.get(tx, transcript_lookup.get(tx.replace(".wav", ""), "(no transcript in lookup)"))
        print(f"  {sc:.3f}  [{day}] {tx}")
        print(f"         {txt[:110]}")

    print(f"\nNext-tier candidates (cos {mid_threshold}-{high_threshold}): {len(mid)}")
    for day, tx, sc in mid[:12]:
        txt = transcript_lookup.get(tx, transcript_lookup.get(tx.replace(".wav", ""), ""))
        print(f"  {sc:.3f}  [{day}] {tx}")
        if txt:
            print(f"         {txt[:100]}")

    if not high and not mid:
        print("  (no clips crossed the thresholds in the cached days)")
    print("\n(These are cosine similarities on pyannote embeddings. Voice is the primary signal; text is only used for the rare self-ID anchors.)")


def main():
    p = argparse.ArgumentParser(
        description="Explore speaker identification for EduPulse radio. "
                    "Text is weak because people name the recipient more than themselves. "
                    "Voice embeddings (pyannote) are the primary signal. "
                    "Works with no extra packages installed using your existing transcripts."
    )
    p.add_argument(
        "--wav-dir",
        default=None,
        help="Directory with tx_*.wav + sidecars (or omit to auto-use demo transcripts from validation/ CSVs).",
    )
    p.add_argument(
        "--transcripts",
        default=None,
        help="Optional clean *_largev3_transcripts.txt (or similar) for best weak labels.",
    )
    p.add_argument(
        "--staff-file",
        default=None,
        help="staff_names.txt (Title First Last). Auto-discovered if omitted.",
    )
    p.add_argument("--diarize", action="store_true", help="Also run full diarization (slower; needs pyannote pipeline + HF token).")
    p.add_argument("--limit", type=int, default=0, help="Limit to first N clips (0 = all).")
    p.add_argument(
        "--report-file",
        default="speaker_feasibility_report.md",
        help="Where to write the markdown feasibility report (default: speaker_feasibility_report.md).",
    )
    p.add_argument("--demo", action="store_true", help="Force use of built-in validation transcripts (hand-coded + large-v3) even if wav-dir exists.")

    # Interactive human-in-the-loop labeling (the main workflow after "Accepted Segmentation")
    p.add_argument("--force-enroll", metavar="TX_BASENAME",
                   help="Enroll this transmission's voice directly under --name (bypasses transcript). "
                        "Example: --force-enroll tx_2026-06-05_10-24-31_3.1s.wav --name 'Mr. Moore'")
    p.add_argument("--name", metavar="SPEAKER_NAME",
                   help="Canonical or short speaker name for --force-enroll (will be canonicalized against staff_names.txt when possible).")
    p.add_argument("--search-speaker", metavar="SPEAKER_NAME",
                   help="After loading the session DB, search the cached day embeddings for other clips that sound like this speaker and print top matches + transcripts.")
    p.add_argument("--session-pkl", default="/tmp/edupulse_speaker_db_session.pkl",
                   help="Path for the accumulating speaker DB session (default /tmp/edupulse_speaker_db_session.pkl).")
    args = p.parse_args()

    staff = load_staff_names(args.staff_file)
    print(f"Loaded {len(staff)} known staff names (from staff_names.txt).")

    # Auto-detect HF token (env or HuggingFaceToken.txt file)
    try:
        from edupulse.speaker import _discover_hf_token
        hf_token = _discover_hf_token()
    except Exception:
        hf_token = os.environ.get("HUGGINGFACE_HUB_TOKEN") or os.environ.get("HF_TOKEN")

    if hf_token:
        print("HF token detected (env or HuggingFaceToken.txt) — real pyannote embeddings will be used if models are accepted.")
    else:
        print("No HF token found — will fall back to text-only analysis (see guidance in edupulse/speaker.py).")

    # ------------------------------------------------------------------
    # Interactive voice labeling loop (user says "tx_xxx is Mr. Y" after listening)
    # ------------------------------------------------------------------
    if args.force_enroll or args.search_speaker:
        try:
            from edupulse.speaker import SpeakerDatabase
            import numpy as np  # for type checks only
        except Exception as e:
            print(f"Speaker features not available: {e}")
            return

        db = SpeakerDatabase.load_session(args.session_pkl, hf_token=hf_token)
        if db is None or not db.is_available():
            print("Embedder not available — cannot do voice enrollment/search.")
            return

        transcript_lookup = load_transcript_lookup()
        day_caches = {
            "2026-06-05": load_day_cache("2026-06-05"),
            "graduation": load_day_cache("graduation"),
        }
        total_cached = sum(len(c) for c in day_caches.values())
        print(f"Loaded day caches: 2026-06-05={len(day_caches['2026-06-05'])}, graduation={len(day_caches['graduation'])} (total {total_cached} clips)")

        if args.force_enroll:
            tx = args.force_enroll if args.force_enroll.endswith(".wav") else args.force_enroll + ".wav"
            raw_name = args.name or "Unknown"
            canon = canonicalize_name(raw_name, staff)
            print(f"\nForce-enrolling: {tx}  -->  '{canon}' (raw: '{raw_name}')")

            # Prefer the vector from the already-computed day cache (works even without the raw wav present)
            vec = None
            for label, cache in day_caches.items():
                if tx in cache:
                    vec = cache[tx]
                    print(f"  Using pre-cached embedding from {label} day cache (no wav read needed).")
                    break
                # also try without .wav suffix in key
                alt = tx.replace(".wav", "")
                if alt in cache:
                    vec = cache[alt]
                    print(f"  Using pre-cached embedding from {label} day cache (key match).")
                    break

            if vec is None:
                # last resort: try to embed from a real wav if the user gave --wav-dir or we can guess
                guess_paths = []
                if args.wav_dir:
                    guess_paths.append(os.path.join(args.wav_dir, tx))
                for base in (".", "hardware/capture", "/tmp"):
                    guess_paths.append(os.path.join(base, tx))
                for gp in guess_paths:
                    if os.path.isfile(gp):
                        print(f"  Computing fresh embedding from {gp}")
                        vec = db.embedder.embed(gp)
                        break

            if vec is None:
                print("  ERROR: could not obtain an embedding for that tx (neither in caches nor on disk).")
            else:
                ok = db.force_enroll(canon, embedding=vec)
                if ok:
                    print(f"  Enrolled successfully. Now has {len(db._db.get(canon, []))} sample(s) for '{canon}'.")
                    db.save_session(args.session_pkl)
                    print(f"  Session saved to {args.session_pkl}")
                else:
                    print("  Enrollment failed (bad vector?).")

        # Always (re)load a fresh view for reporting
        db = SpeakerDatabase.load_session(args.session_pkl, hf_token=hf_token)

        print("\n--- Current speaker DB (voice profiles) ---")
        for name in db.known_speakers():
            n = len(db._db.get(name, []))
            print(f"  {name}: {n} sample(s)")

        if args.search_speaker:
            qname = canonicalize_name(args.search_speaker, staff)
            search_and_report(db, qname, day_caches, transcript_lookup)
        elif args.force_enroll:
            # After a force-enroll, auto-search the newly enrolled speaker
            qname = canonicalize_name(args.name or "", staff)
            if qname in db.known_speakers():
                search_and_report(db, qname, day_caches, transcript_lookup)

        print("\nDone with force-enroll / search. (Run again with new --force-enroll to continue labeling.)")
        return   # do not fall through to the old feasibility report

    wav_dir = args.wav_dir
    if args.demo or not wav_dir:
        # Force demo path so the skeleton is always exercisable inside this workspace
        wav_dir = None
        print("Using built-in demo transcripts (validation focused CSVs with human gold + large-v3).")

    trans_map = load_transcripts_for_dir(wav_dir, args.transcripts)
    if not trans_map:
        print("ERROR: No transcripts loaded from any source (sidecars, txt, or demo CSVs).")
        return

    print(f"Loaded {len(trans_map)} transcripts for weak supervision / mention mining.")

    # Durations: the graduation focused csv has them; sidecars have duration_sec. For demo we can leave empty.
    durations: dict[str, float] = {}
    # (If a real wav_dir with sidecars is present the report can be extended later to slurp durations.)

    limited_map = trans_map
    if args.limit and args.limit > 0:
        # deterministic order
        for k in sorted(trans_map)[: args.limit]:
            limited_map = {k: trans_map[k] for k in sorted(trans_map)[: args.limit]}

    print(f"\n=== Running speaker feasibility (pyannote skeleton) ===")
    report = build_speaker_feasibility_report(
        wav_dir=wav_dir,
        transcripts=limited_map,
        known_staff=staff,
        durations=durations or None,
        run_identification=True,
        diarize=args.diarize,
        report_path=args.report_file,
        hf_token=hf_token,
    )

    # Pretty console summary (works whether or not embeddings were present)
    tstats = report["transcript_stats"]
    print("\n--- Transcript anchors (text only — often names the recipient, not speaker) ---")
    print(f"Clips: {tstats['total_clips']}")
    print(f"Clips with any staff name mentioned: {tstats.get('clips_with_any_staff_mention', 0)}")
    print(f"Strong self-ID anchors (speaker clearly named *themselves*): {tstats.get('clips_with_strong_self_id', 0)}")
    print(f"Unique staff appearing in transcripts: {tstats['unique_staff_mentioned']}")

    if tstats.get("per_staff_mention_counts"):
        print("Staff mentioned (note: frequently the person being called):")
        for name, cnt in list(tstats["per_staff_mention_counts"].items())[:8]:
            print(f"  {name}: {cnt}")

    summ = report.get("summary", {})
    print("\n--- Voice embedding layer (the real signal) ---")
    print(f"Embeddings available: {report['embedding_available']}")
    print(f"Diarization available: {report['diarization_available']}")
    print(f"Clips labeled via voice similarity: {summ.get('clips_identified_by_voice', 0)}")
    if summ.get("mean_identification_conf"):
        print(f"Mean conf on voice-labeled clips: {summ['mean_identification_conf']}")

    print("\n--- Feasibility notes ---")
    for note in report["feasibility_notes"]:
        print(f"• {note}")

    if report.get("report_written"):
        print(f"\nWrote full report: {report['report_written']}")
    else:
        print(f"\n(Report also written to {args.report_file} if possible.)")

    print("\nThis skeleton fits the narrowed hierarchy (VAD + heavy transcription as core).")
    print("Speaker attribution is an additive layer for airtime, distributed leadership, and participation metrics.")
    print("Only write primary_speaker into sidecars that came from the heaviest model (large-v3).")


if __name__ == "__main__":
    main()
