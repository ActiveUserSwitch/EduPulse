#!/usr/bin/env python3
"""
EduPulse - Whisper Transcription Test / Starter

Transcribes captured radio recordings (e.g. your first successful laptop test)
using faster-whisper. This exercises the "analysis" side of the pipeline with
real data from the capture tools.

The tiny + int8 + cpu config is fast for laptop development and works well
for short radio transmissions.

Note on VAD + spaced transmissions:
Radio comms are push-to-talk style with potentially long silences between
bursts. VAD is OFF by default (so the second smaller transmission at the end
of the file is captured, as happened with the original "first-tx" capture).

If you have background noise and want the model to focus only on speech,
enable it explicitly:

    python test/test_whisper.py --vad-filter

You can also tune --min-silence-ms and --vad-threshold when VAD is on.

Usage:
    # Auto-find the newest px650_*.wav (e.g. your recent first-tx capture)
    python test/test_whisper.py

    # Explicit file (recommended while you have multiple tests)
    python test/test_whisper.py --file ~/edupulse/test_recordings/px650_2026-06-02_18-31-54_first-tx.wav

    # When VAD drops a later/quiet transmission:
    python test/test_whisper.py --no-vad

    # Other options
    python test/test_whisper.py --file my-recording.wav --model base --language en --beam-size 8 --initial-prompt "School radio communications:"

    # Best accuracy on laptop (slower)
    python test/test_whisper.py --file ... --model small --temperature 0.0

    # With audio fingerprint (staff names + common radio words) for much better results:
    # python test/test_whisper.py --file tx_....wav --known-staff "Ms. Chandler,Mr. Moore" --common-words "chromebook,retake,500"

After each line you will also see rudimentary categorization + incident ID, e.g.:
[ 0.00s -> 4.00s] [INC-003] (conf 0.81) [Discipline (Student Conflict, Defiance, etc.) conf:0.75] Two students fighting...

Note: "Ben for dismissal" should now correctly match Early Dismissal thanks to keywords like "for dismissal".
"""

import argparse
import math
import sys
from pathlib import Path

# Allow running this script directly from test/ (or any subdir) without
# PYTHONPATH=. or pip install -e. Walk up until the dir containing edupulse/
# package is found. Keeps usage examples in docs and --help simple.
_here = Path(__file__).resolve()
for _ in range(6):
    if (_here / "edupulse" / "__init__.py").exists():
        if str(_here) not in sys.path:
            sys.path.insert(0, str(_here))
        break
    _here = _here.parent
else:
    _root = Path(__file__).resolve().parents[1]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import numpy as np

# =============================================================================
# Shared categorization + incident linking (single source of truth)
# See edupulse/analysis.py for the implementation and detailed radio protocol rules.
# =============================================================================
from edupulse.analysis import (
    TRANSMISSION_CATEGORIES,
    build_enhanced_initial_prompt,
    categorize_transmission,
    IncidentTracker,
)
# =============================================================================


# =============================================================================
# INCIDENT / CONVERSATION LINKING (same logic as realtime script)
# Based on typical school radio protocol:
#   Caller A: "Receiver B [Caller A]"
#   Receiver B: "Go ahead / Yes / Copy"
#   Caller A: message
#   Receiver B: question / confirm / clarify
#
# Key rules (per user):
# - Student names (especially full "First Last" like "Emily Rodriguez" or "Ricky Bobby") are *very strong anchors*.
#   Mentioning the same student (by full name) is a safe bet for continuation of the same event.
#   Different full student names almost always means a separate incident. Single names are weaker.
# - Role calls (Nurse, Officer, Sergeant, Captain, Custodian, Mr./Mrs./Ms./Coach etc.) usually start *new*
#   incidents unless clearly tied to a student.
# - JROTC officers (Sergeant Marvel, Captain Hatfield, etc.) are grouped together when JROTC context is present.
# - Coaches are tagged for the Athletic Department (treated as role/teacher-or-admin per request).
# Full student names take precedence and prevent cross-student over-linking of unrelated
# early dismissals, nurse calls, etc.
# =============================================================================

# IncidentTracker is now imported from edupulse.analysis (see top of file).
# The definition below has been removed to eliminate duplication.
# class IncidentTracker: ... (implementation lives in edupulse/analysis.py)

# (old _extract_names body removed; logic is in the shared edupulse.analysis.IncidentTracker)

# (remaining old tracker methods removed)
def find_latest_recording() -> Path | None:
    """Search common locations for the most recent px650_* recording."""
    candidates = [
        Path.home() / "edupulse" / "test_recordings",
        Path("test_recordings"),
        Path.cwd() / "test_recordings",
        Path("..") / "test_recordings",
    ]
    for base in candidates:
        try:
            if base.exists():
                files = sorted(
                    base.glob("px650_*.wav"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if files:
                    return files[0]
        except Exception:
            pass
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe EduPulse radio recordings with faster-whisper"
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Path to .wav file to transcribe. "
             "Default: auto-find the newest px650_*.wav under ~/edupulse/test_recordings or ./test_recordings",
    )
    parser.add_argument(
        "--model", default="tiny", help="Model size: tiny, base, small, medium, large-v3, etc."
    )
    parser.add_argument("--device", default="cpu", help="cpu or cuda (if you have GPU)")
    parser.add_argument(
        "--compute-type",
        default="int8",
        dest="compute_type",
        help="int8, int8_float16, float16, float32 (int8 is fastest for CPU)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Force a language code (e.g. 'en'). Omit for auto-detection.",
    )
    parser.add_argument(
        "--beam-size", type=int, default=5, dest="beam_size",
        help="Beam size for decoding (higher = potentially better but slower)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.0,
        help="0.0 for deterministic output (recommended for accuracy on radio). Higher values add variety but can cause hallucinations.",
    )
    parser.add_argument(
        "--initial-prompt", default=None,
        help="Optional text prompt to bias transcription toward expected domain, e.g. 'School radio administrative messages, clear English phrases:'",
    )
    parser.add_argument("--known-staff", help="Comma-separated full staff names for fingerprint (improves prompt + name extraction)")
    parser.add_argument("--known-staff-file", type=Path, help="File with one staff full name per line")
    parser.add_argument("--common-words", help="Comma-separated common radio words for fingerprint")
    parser.add_argument("--common-words-file", type=Path, help="File with common words/phrases (one per line or space separated)")
    parser.add_argument("--list-categories", action="store_true",
                        help="List the current rudimentary transmission categories and exit")
    parser.add_argument(
        "--vad-filter",
        action="store_true",
        default=False,
        help="Enable VAD (voice activity detection) to skip long silences or background noise. "
             "Disabled by default because real radio (PTT) transmissions often have long gaps; "
             "VAD can drop a second smaller transmission near the end of the file (as seen with the "
             "original first-tx capture). Turn VAD on only when you have significant noise to filter.",
    )
    parser.add_argument(
        "--no-vad", dest="vad_filter", action="store_false",
        help="Explicitly force VAD off (same as the default). Useful for clarity in docs or scripts.",
    )
    parser.add_argument(
        "--min-silence-ms", type=int, default=1500, dest="min_silence_ms",
        help="VAD only: minimum silence (ms) before splitting a speech segment. Raise this for very spaced radio comms.",
    )
    parser.add_argument(
        "--vad-threshold", type=float, default=0.4, dest="vad_threshold",
        help="VAD only: speech probability threshold (lower = more sensitive to quiet/small transmissions).",
    )
    args = parser.parse_args()

    if args.list_categories:
        print("Current rudimentary transmission categories (keyword-based):")
        for cat, kws in TRANSMISSION_CATEGORIES.items():
            print(f"  - {cat}")
            print(f"      keywords: {', '.join(kws)}")
        return

    # Fingerprint loading (same as in the live capture tool)
    known_staff_names: list[str] = []
    if args.known_staff:
        known_staff_names.extend([x.strip() for x in args.known_staff.split(",") if x.strip()])
    if getattr(args, "known_staff_file", None) and args.known_staff_file.exists():
        for line in args.known_staff_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                known_staff_names.append(line)
    known_staff_names = sorted(set(known_staff_names))

    common_words: list[str] = []
    if args.common_words:
        common_words.extend([x.strip() for x in args.common_words.split(",") if x.strip()])
    if getattr(args, "common_words_file", None) and args.common_words_file.exists():
        for line in args.common_words_file.read_text().splitlines():
            for tok in line.replace(",", " ").split():
                tok = tok.strip()
                if tok and not tok.startswith("#"):
                    common_words.append(tok)
    common_words = sorted(set(common_words))

    # Merge fingerprint into the prompt for this file
    effective_prompt = build_enhanced_initial_prompt(
        base=args.initial_prompt,
        known_staff=known_staff_names,
        common_words=common_words,
    )
    if effective_prompt != args.initial_prompt:
        print(f"[fingerprint] Enhanced prompt with {len(known_staff_names)} staff names + {len(common_words)} common words.")

    wav_path = args.file
    if wav_path is None:
        wav_path = find_latest_recording()
        if wav_path is None:
            print("ERROR: No --file given and could not auto-discover a px650_*.wav recording.")
            print()
            print("Quick start:")
            print("  1. Make a capture first:")
            print("     python hardware/capture/record_session.py --label test --duration 15")
            print("  2. Then run this again (it will auto-pick the newest px650 file).")
            print()
            print("Or specify explicitly:")
            print("  python test/test_whisper.py --file ~/edupulse/test_recordings/px650_....wav")
            sys.exit(1)
        print(f"Auto-selected most recent recording: {wav_path}")

    wav_path = wav_path.expanduser().resolve()
    if not wav_path.exists():
        print(f"ERROR: File not found: {wav_path}")
        sys.exit(1)

    print(f"\n=== EduPulse Whisper Test ===")
    print(f"File       : {wav_path}")
    print("RUDIMENTARY CATEGORIES (user-provided): " + ", ".join(TRANSMISSION_CATEGORIES.keys()))
    print(f"Model      : {args.model}  | device={args.device}  | compute={args.compute_type}")
    print(f"Beam       : {args.beam_size}  | VAD={args.vad_filter}")
    if args.vad_filter:
        print(f"VAD params : min_silence={args.min_silence_ms}ms  threshold={args.vad_threshold}")
    if args.language:
        print(f"Language   : {args.language} (forced)")
    print()

    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        print("ERROR: faster-whisper is not installed in this environment.")
        print("Install with: pip install faster-whisper")
        print("(See requirements.txt)")
        sys.exit(1)

    print("Loading Whisper model (tiny downloads quickly on first run)...")
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)

    print("Transcribing (this may take a few seconds for a short clip)...")
    vad_params = dict(
        min_silence_duration_ms=args.min_silence_ms,
        threshold=args.vad_threshold,
    ) if args.vad_filter else None

    # Load and preprocess for best results on radio audio (dominant channel + normalize)
    import soundfile as sf
    audio, sr = sf.read(str(wav_path))
    if audio.ndim > 1 and audio.shape[1] > 1:
        rms_l = np.sqrt(np.mean(audio[:, 0]**2))
        rms_r = np.sqrt(np.mean(audio[:, 1]**2))
        audio = audio[:, 0] if rms_l > rms_r else audio[:, 1]
    # normalize
    peak = np.max(np.abs(audio))
    if peak > 1e-6:
        audio = audio / peak

    segments, info = model.transcribe(
        audio,
        beam_size=args.beam_size,
        temperature=args.temperature,
        initial_prompt=effective_prompt,
        language=args.language,
        vad_filter=args.vad_filter,
        vad_parameters=vad_params,
        condition_on_previous_text=False,  # treat bursts more independently (good for radio PTT)
    )

    print(f"\nDetected language : {info.language} (probability {info.language_probability:.2f})")
    print(f"Audio duration    : {info.duration:.1f} s")
    print("-" * 70)

    # Per-file incident tracker for linking transmissions within this recording
    file_tracker = IncidentTracker(known_staff_names=known_staff_names)

    text_parts = []
    confs = []
    for segment in segments:
        conf = math.exp(segment.avg_logprob)
        confs.append(conf)
        cat_result = categorize_transmission(segment.text)
        cat_str = cat_result["category"]
        cat_conf = cat_result["confidence"]

        # Link using the same radio-protocol aware logic (time within file + names).
        # Pass confs so low-quality segments don't introduce garbage names.
        inc_id = file_tracker.get_incident_id(segment.text, segment.start, cat_str,
                                              whisper_conf=conf, cat_conf=cat_conf)

        line = (
            f"[{segment.start:6.2f}s -> {segment.end:6.2f}s] "
            f"[{inc_id}] "
            f"(conf {conf:.2f}) "
            f"[{cat_str} conf:{cat_conf:.2f}] "
            f"{segment.text.strip()}"
        )
        print(line)
        text_parts.append(segment.text.strip())

    print("-" * 70)
    full_text = " ".join(text_parts)
    avg_conf = sum(confs) / len(confs) if confs else 0.0
    print(f"Full transcript   : {full_text or '(no speech detected)'}")
    print(f"Average confidence: {avg_conf:.2f}")
    print("\nDone. Use this as a starting point for radio phrase detection, logging, etc.")


if __name__ == "__main__":
    main()
