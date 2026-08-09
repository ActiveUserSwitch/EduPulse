#!/usr/bin/env python3
"""
EduPulse - Optional Speaker Diarization & Identification (pyannote.audio skeleton)

This module provides a thin, optional wrapper around pyannote.audio for
speaker diarization (who spoke when) and speaker identification (which known
staff member is speaking).

Design goals:
- Zero hard dependency: everything is inside try/except so the rest of
  edupulse (analysis.py, recorders, etc.) stays lightweight and importable
  even if pyannote/torch are not installed.
- Works on the existing short tx_*.wav clips.
- Plays nicely with the gold human_transcript + staff_names.txt we already have
  for weak supervision / enrollment.
- Produces fields that can be written into the existing sidecar .json format.

Intended use (once enabled):
- Per-transmission primary speaker identification (most PTT turns are one speaker).
- Optional within-clip diarization for longer transmissions.
- Later: participation stats, turn-taking, "distributed leadership" metrics
  (who initiates INCs, who talks most by role, response patterns, equity, etc.).

Installation (heavy):
    # System (outside the venv)
    sudo apt update && sudo apt install ffmpeg

    # In your edupulse venv
    pip install pyannote.audio
    # or
    uv add pyannote.audio

    # Then (one-time):
    # 1. Visit and Accept the gated models:
    #      https://huggingface.co/pyannote/embedding
    #      https://huggingface.co/pyannote/speaker-diarization-3.1
    # 2. Create a token: https://huggingface.co/settings/tokens
    #
    # Token options (in priority order):
    #   - export HF_TOKEN=hf_...   (or HUGGINGFACE_HUB_TOKEN)
    #   - Save the token to a file named HuggingFaceToken.txt
    #     (supported locations: project root, ~/ , hardware/capture/ , next to this code)
    #   - huggingface-cli login
    #
    # After that the speaker features (embeddings + optional diarization) become active.
    # They remain completely optional — the rest of EduPulse works without them.

Typical usage in a test script or after transcription:

    from edupulse.speaker import SpeakerDiarizer, SpeakerDatabase, get_speaker_database

    diar = SpeakerDiarizer()                    # may be None if pyannote missing
    segments = diar.diarize("tx_....wav") if diar else []

    db = get_speaker_database(known_staff=load_staff_names())
    # Only enroll on strong self-identification ("Go for X", "This is X").
    # Most transmissions name the person being *called*, not the person speaking.
    db.mine_and_enroll("tx_foo.wav", transcript="Go for Strickland.")
    name, conf = db.identify("tx_bar.wav")   # real work happens via voice embedding

    # Then write into sidecar (only ever for large-v3 / heavy model results):
    # meta["primary_speaker"] = name
    # meta["speaker_conf"] = round(conf, 3)
    # meta["speaker_segments"] = segments
"""

from __future__ import annotations

import os
import pickle
import warnings
from typing import Any, Optional

# We deliberately do NOT import numpy / torch / pyannote at module level.
# All heavy imports are inside methods so "import edupulse.speaker" is always safe.
try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


def _discover_hf_token(explicit_token: str | None = None) -> str | None:
    """Return a HF token from explicit arg, env vars, or a token file.

    Supports saving the token to HuggingFaceToken.txt in common locations
    (project root, ~/, hardware/capture/, next to the code) as a convenient
    alternative to always exporting HF_TOKEN.

    The file can contain just the token or "hf_..." on the first non-comment line.
    """
    if explicit_token:
        return explicit_token

    # 1. Environment variables (standard)
    tok = os.environ.get("HUGGINGFACE_HUB_TOKEN") or os.environ.get("HF_TOKEN")
    if tok:
        return tok

    # 2. Search for HuggingFaceToken.txt (user convenience)
    candidates = [
        "HuggingFaceToken.txt",                                   # cwd
        os.path.expanduser("~/HuggingFaceToken.txt"),             # home
        # From this file (edupulse/speaker.py) -> GrokBuild root
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "HuggingFaceToken.txt")),
        # Explicit workspace path (common in this project)
        "/home/joseph/Documents/GrokBuild/HuggingFaceToken.txt",
        # In the capture dir (for Pi / field use)
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "hardware", "capture", "HuggingFaceToken.txt")),
    ]

    for p in candidates:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            if line.startswith("hf_") or len(line) > 20:
                                return line
            except Exception:
                continue
    return None


class SpeakerDiarizer:
    """Optional wrapper for pyannote speaker diarization (who spoke when).

    If the package or the pretrained pipeline cannot be loaded, every method
    returns an empty list / None and the rest of the system continues to work.
    """

    def __init__(self, hf_token: str | None = None):
        self.pipeline = None
        self.hf_token = _discover_hf_token(hf_token)
        self._load()

    def _load(self) -> None:
        if np is None:
            return
        try:
            from pyannote.audio import Pipeline
            # pyannote/speaker-diarization-3.1 (or newer 3.x) is the recommended pipeline.
            # In pyannote.audio >= 3/4 + current HF hub the kwarg is "token", not "use_auth_token".
            kwargs = {}
            if self.hf_token:
                kwargs["token"] = self.hf_token
            self.pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                **kwargs
            )
        except Exception as e:
            msg = str(e)
            if "gated" in msg.lower() or "401" in msg or "access" in msg.lower() or "token" in msg.lower():
                guidance = (
                    "\n\nTo use speaker diarization you must:\n"
                    "  1. Visit https://huggingface.co/pyannote/speaker-diarization-3.1 and click 'Accept' on the model card.\n"
                    "  2. (Recommended) Also accept https://huggingface.co/pyannote/segmentation-3.0\n"
                    "  3. Create a token at https://huggingface.co/settings/tokens (read permission is enough).\n"
                    "  4. Provide the token by:\n"
                    "       export HF_TOKEN=hf_...   (or HUGGINGFACE_HUB_TOKEN)\n"
                    "     or save it (as the only content or first non-# line) to HuggingFaceToken.txt\n"
                    "     in the project root / ~/ / hardware/capture/ (auto-discovered, like staff_names.txt)\n"
                    "  5. CRITICAL: After creating the token you MUST visit the HF model page while logged in\n"
                    "     with that account and click the 'Accept' button, or you will get 403 'not in authorized list'.\n"
                )
            else:
                guidance = ""
            warnings.warn(
                f"[edupulse.speaker] pyannote diarization pipeline not available: {e}." + guidance +
                "\nSpeaker diarization will be a no-op until the above is done.",
                stacklevel=2,
            )
            self.pipeline = None

    def is_available(self) -> bool:
        return self.pipeline is not None

    def diarize(self, audio_path: str) -> list[dict[str, Any]]:
        """Run diarization on a single (usually short) transmission clip.

        Returns a list of segments:
            [{"start": 0.0, "end": 2.34, "speaker": "SPEAKER_00"}, ...]

        If pyannote is unavailable or the file cannot be processed, returns [].
        """
        if self.pipeline is None:
            return []
        try:
            diarization = self.pipeline(audio_path)
            segments: list[dict[str, Any]] = []
            # Handle pyannote 3.x+ output (DiarizeOutput has .speaker_diarization as Annotation)
            if hasattr(diarization, "speaker_diarization"):
                annotation = diarization.speaker_diarization
            else:
                annotation = diarization
            for turn, _, speaker in annotation.itertracks(yield_label=True):
                segments.append({
                    "start": float(turn.start),
                    "end": float(turn.end),
                    "speaker": str(speaker),
                })
            return segments
        except Exception as e:
            warnings.warn(f"[edupulse.speaker] diarization failed on {audio_path}: {e}")
            return []


class SpeakerEmbedder:
    """Extract a single fixed-size embedding for a whole (short) transmission.

    Useful for identification against a database of known staff voices.
    """

    def __init__(self, hf_token: str | None = None):
        self.embedding = None
        self.hf_token = _discover_hf_token(hf_token)
        self._load()

    def _load(self) -> None:
        if np is None:
            return
        try:
            from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding
            # pyannote/embedding is gated on HF.
            # Newer versions of the HF client accept `token=`.
            emb_kwargs = {"device": "cpu"}
            if self.hf_token:
                emb_kwargs["token"] = self.hf_token
            self.embedding = PretrainedSpeakerEmbedding(
                "pyannote/embedding",
                **emb_kwargs
            )
        except Exception as e:
            msg = str(e)
            if "gated" in msg.lower() or "401" in msg or "access" in msg.lower() or "restricted" in msg.lower():
                guidance = (
                    "\n\nTo use speaker embeddings / identification you must:\n"
                    "  1. Visit https://huggingface.co/pyannote/embedding and click 'Accept' (user conditions).\n"
                    "  2. Create a read token at https://huggingface.co/settings/tokens\n"
                    "  3. Provide the token by:\n"
                    "       export HF_TOKEN=hf_...   (or HUGGINGFACE_HUB_TOKEN)\n"
                    "     or save it (as the only content or first non-# line) to HuggingFaceToken.txt\n"
                    "     in the project root, your home, or hardware/capture/ (auto-discovered)\n"
                    "  4. CRITICAL: After creating the token / saving the file, you MUST visit the page while logged in\n"
                    "     with the same HF account and click 'Accept'. Token alone is not enough — you will get 403\n"
                    "     'not in the authorized list' until you accept on the website.\n"
                    "  5. (Optional but recommended) Also accept https://huggingface.co/pyannote/speaker-diarization-3.1 for --diarize.\n"
                )
            else:
                guidance = ""
            warnings.warn(f"[edupulse.speaker] pyannote embedding model not available: {e}" + guidance)
            self.embedding = None

    def is_available(self) -> bool:
        return self.embedding is not None

    def embed(self, audio_path: str) -> Optional["np.ndarray"]:
        """Return a 1-D numpy array (the speaker embedding) or None on failure."""
        if self.embedding is None or np is None:
            return None
        try:
            import torch
            from pyannote.audio import Audio

            audio = Audio(sample_rate=16000, mono=True)
            waveform, sample_rate = audio(audio_path)   # torch.Tensor, shape usually (1, time) or (time,)

            # Force strict mono (1, time) - some model versions are picky about channels
            if waveform.ndim == 1:
                waveform = waveform.unsqueeze(0)
            if waveform.shape[0] > 1:
                waveform = waveform.mean(dim=0, keepdim=True)

            # Make sure it's on the same device as the model if the model has one
            if hasattr(self.embedding, "device"):
                waveform = waveform.to(self.embedding.device)

            emb = self.embedding(waveform)
            return np.asarray(emb).squeeze()
        except Exception as e:
            # Fallback: direct path (some pyannote versions handle loading internally)
            try:
                emb = self.embedding(audio_path)
                return np.asarray(emb).squeeze()
            except Exception as e2:
                warnings.warn(f"[edupulse.speaker] embedding failed on {audio_path}: {e} / fallback: {e2}")
                return None


class SpeakerDatabase:
    """A tiny in-memory database of known speakers.

    You can:
    - Manually enroll(name, wav_path)
    - Mine weak labels from transcripts that mention exactly one known staff member
      (using the staff_names.txt you already maintain).
    - Identify a new clip against the database.

    This is deliberately simple. For production distributed-leadership work you
    will probably want to persist the embeddings (numpy .npy or a small vector DB).
    """

    def __init__(self, embedder: SpeakerEmbedder | None = None, hf_token: str | None = None):
        discovered = _discover_hf_token(hf_token)
        self.embedder = embedder
        if self.embedder is None:
            try:
                self.embedder = SpeakerEmbedder(hf_token=discovered)
            except Exception:
                self.embedder = None  # vector-only mode; searches on pre-cached embeddings still work
        self._db: dict[str, list["np.ndarray"]] = {}   # name -> list of embeddings

    def is_available(self) -> bool:
        # Available for *search / identification* if we have any enrolled vectors,
        # even if the live embedder is missing (we can still operate on pre-cached day embeddings).
        if self._db:
            return True
        if self.embedder is not None:
            try:
                return self.embedder.is_available()
            except Exception:
                return False
        return False

    def enroll(self, name: str, audio_path: str) -> bool:
        """Add one enrollment embedding for a known speaker."""
        emb = self.embedder.embed(audio_path)
        if emb is None:
            return False
        self._db.setdefault(name, []).append(emb)
        return True

    def mine_and_enroll(self, wav_path: str, transcript: str, known_staff: list[str]) -> list[str]:
        """Conservative enrollment using *strong self-identification only*.

        In this radio environment, people usually say the *other person's* name
        ("Dr. Strickland, can you come...?"). The speaker is often the caller,
        not the person named.

        We only treat a clip as a high-confidence enrollment example when the
        transcript contains a clear self-reference by the speaker:
          - "Go for X", "This is X", "X here", "Yeah, Strickland."

        General name mentions are *not* used for blind enrollment anymore.

        Returns the list of names we felt safe enrolling from this clip (0 or 1).
        """
        if not transcript or not known_staff:
            return []

        try:
            from edupulse.analysis import infer_likely_speaker

            name, conf = infer_likely_speaker(transcript, known_staff)
            if name and conf == "strong":
                if self.enroll(name, wav_path):
                    return [name]
        except Exception:
            pass

        return []

    def identify(self, audio_path: str, threshold: float = 0.65) -> tuple[str | None, float]:
        """Return (best_matching_name, cosine_similarity) or (None, score) if below threshold."""
        if not self._db or not self.embedder.is_available():
            return None, 0.0

        emb = self.embedder.embed(audio_path)
        if emb is None:
            return None, 0.0

        best_name: str | None = None
        best_score = -1.0

        for name, embs in self._db.items():
            scores = []
            for e in embs:
                denom = (np.linalg.norm(emb) * np.linalg.norm(e)) + 1e-8
                scores.append(float(np.dot(emb, e) / denom))
            if scores:
                score = float(np.mean(scores))
                if score > best_score:
                    best_score = score
                    best_name = name

        if best_score >= threshold and best_name is not None:
            return best_name, best_score
        return None, best_score

    def known_speakers(self) -> list[str]:
        return sorted(self._db.keys())

    def force_enroll(
        self,
        name: str,
        audio_path: str | None = None,
        embedding: "np.ndarray | None" = None,
    ) -> bool:
        """Directly enroll a voice sample for a speaker by name.

        This is the primary method for the human-in-the-loop workflow:
        user listens to a raw tx_*.wav and says "tx_foo is Mr. X", then we
        force_enroll the *actual acoustic embedding* of that clip (bypassing
        any transcript text, because most transmissions name the recipient).

        You may pass either:
          - audio_path: path to the .wav (will compute embedding live)
          - embedding: a pre-computed 1-D numpy vector (useful when you already
            have day caches loaded and want to label a clip without re-reading audio)

        The name is stored exactly as provided (caller is responsible for
        canonicalizing to the Title First Last form from staff_names.txt).
        Multiple samples per name are kept; identify() and search use the mean.
        """
        if embedding is not None:
            emb = np.asarray(embedding).squeeze().astype(float)
        elif audio_path:
            if self.embedder is None:
                return False
            emb = self.embedder.embed(audio_path)
            if emb is not None:
                emb = np.asarray(emb).squeeze().astype(float)
        else:
            return False

        if emb is None or emb.ndim != 1:
            return False

        self._db.setdefault(name, []).append(emb)
        return True

    def mean_embedding_for(self, name: str) -> Optional["np.ndarray"]:
        """Return the mean voice profile for a speaker (or None)."""
        vecs = self._db.get(name)
        if not vecs:
            return None
        if len(vecs) == 1:
            return np.asarray(vecs[0]).squeeze().astype(float)
        return np.mean([np.asarray(v).squeeze() for v in vecs], axis=0).astype(float)

    def find_similar(
        self,
        query_embedding: "np.ndarray",
        threshold: float = 0.70,
        top_k: int = 30,
    ) -> list[tuple[str, float]]:
        """Rank known speaker profiles by cosine similarity to the query vector.

        Returns list of (speaker_name, score) sorted descending, only those >= threshold.
        """
        if not self._db or query_embedding is None or np is None:
            return []

        q = np.asarray(query_embedding).squeeze().astype(float)
        qn = np.linalg.norm(q) + 1e-8
        results: list[tuple[str, float]] = []

        for name, vecs in self._db.items():
            if not vecs:
                continue
            # compare against the mean profile for robustness
            mean_v = self.mean_embedding_for(name)
            if mean_v is None:
                continue
            vn = np.linalg.norm(mean_v) + 1e-8
            score = float(np.dot(q, mean_v) / (qn * vn))
            if score >= threshold:
                results.append((name, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def search_clips(
        self,
        query_name: str,
        clip_embeddings: dict[str, "np.ndarray"],
        threshold: float = 0.55,
        top_k: int = 15,
        exclude: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Search a dict of {tx_basename: embedding} for clips similar to query_name's profile.

        Returns [(tx_name, cosine), ...] highest first.
        This is the fast path used with the pre-cached per-day embedding pkls.
        """
        profile = self.mean_embedding_for(query_name)
        if profile is None or not clip_embeddings:
            return []

        exclude = exclude or set()
        qn = np.linalg.norm(profile) + 1e-8
        scored: list[tuple[str, float]] = []

        for tx, vec in clip_embeddings.items():
            if tx in exclude:
                continue
            v = np.asarray(vec).squeeze().astype(float)
            vn = np.linalg.norm(v) + 1e-8
            score = float(np.dot(profile, v) / (qn * vn))
            if score >= threshold:
                scored.append((tx, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def save_session(self, path: str = "/tmp/edupulse_speaker_db_session.pkl") -> None:
        """Persist the current enrollments (names + all raw vectors) to a pickle."""
        try:
            payload = {
                "speakers": self.known_speakers(),
                "embeddings": {n: [np.asarray(e) for e in lst] for n, lst in self._db.items()},
            }
            with open(path, "wb") as f:
                pickle.dump(payload, f)
        except Exception as e:
            warnings.warn(f"[edupulse.speaker] Failed to save session to {path}: {e}")

    @classmethod
    def load_session(
        cls,
        path: str = "/tmp/edupulse_speaker_db_session.pkl",
        hf_token: str | None = None,
    ) -> "SpeakerDatabase | None":
        """Load a previously saved session (or start fresh if file missing).

        Works in "vector-only" mode even when pyannote/torch are not importable:
        all math (means, cosine searches) is pure numpy on the stored vectors.
        """
        db = None
        try:
            # Try a lightweight construction first (embedder may be absent)
            db = cls(hf_token=hf_token)
        except Exception:
            # Ultimate fallback: empty shell we can still populate from pkl
            db = cls.__new__(cls)
            db.embedder = None
            db._db = {}

        if not os.path.isfile(path):
            return db

        try:
            with open(path, "rb") as f:
                payload = pickle.load(f)
            embs = payload.get("embeddings", {})
            for name, vecs in embs.items():
                if isinstance(vecs, list):
                    for v in vecs:
                        db._db.setdefault(name, []).append(np.asarray(v))
                else:
                    db._db.setdefault(name, []).append(np.asarray(vecs))
            return db
        except Exception as e:
            warnings.warn(f"[edupulse.speaker] Could not load session {path}: {e}")
            return db if db is not None else None


def get_speaker_diarizer(hf_token: str | None = None) -> SpeakerDiarizer | None:
    """Factory that returns a diarizer or None if pyannote is not usable."""
    try:
        discovered = _discover_hf_token(hf_token)
        d = SpeakerDiarizer(hf_token=discovered)
        return d if d.is_available() else None
    except Exception:
        return None


def get_speaker_database(known_staff: list[str] | None = None, hf_token: str | None = None) -> SpeakerDatabase | None:
    """Factory that returns a database or None if embeddings are not available."""
    try:
        discovered = _discover_hf_token(hf_token)
        db = SpeakerDatabase(hf_token=discovered)
        return db if db.is_available() else None
    except Exception:
        return None


# Convenience helper that downstream code (test scripts, future recorder worker)
# can call without caring about optional dependencies.
def enrich_with_speaker(
    wav_path: str,
    transcript: str,
    known_staff: list[str] | None = None,
    diarize: bool = False,
    hf_token: str | None = None,
) -> dict[str, Any]:
    """Return a small dict with whatever speaker information we could extract.

    This is the main "public" entry point for the rest of the system.
    It is safe to call even if pyannote is missing (returns mostly empty data).
    """
    result: dict[str, Any] = {
        "primary_speaker": None,
        "speaker_conf": 0.0,
        "speaker_segments": [],
    }

    discovered = _discover_hf_token(hf_token)
    db = get_speaker_database(known_staff=known_staff, hf_token=discovered)
    if db is not None:
        # Try to mine the current clip itself (very weak but useful bootstrap)
        db.mine_and_enroll(wav_path, transcript, known_staff or [])
        name, conf = db.identify(wav_path)
        if name:
            result["primary_speaker"] = name
            result["speaker_conf"] = round(conf, 3)

    if diarize:
        diar = get_speaker_diarizer(hf_token=discovered)
        if diar is not None:
            result["speaker_segments"] = diar.diarize(wav_path)

    return result


# =============================================================================
# SESSION-LEVEL FEASIBILITY HELPERS (the real "buildout" for the skeleton)
# =============================================================================
# These give you immediate value from the transcripts + staff_names.txt you
# already maintain, *before* you even install pyannote. When the embedding
# models are present they add the actual voice clustering / identification layer.
#
# Primary goal: quantify how much "supervision signal" exists in the collected
# radio traffic for speaker recognition, and surface practical feasibility
# notes (clip length distribution, repeated voices, short-PTT reality, etc.).
# =============================================================================

def compute_transcript_mention_stats(
    transcripts: dict[str, str], known_staff: list[str]
) -> dict[str, Any]:
    """Pure-transcript supervision stats (works with zero ML deps).

    IMPORTANT: In this radio protocol, people mostly say the name of the
    person they are calling, not their own name. So "Dr. Strickland" in a
    transcript often means someone else is talking *to* Dr. Strickland.

    We now separate:
    - General name mentions (common, but weak for knowing who is speaking)
    - Strong self-identification ("Go for X", "This is X") — these are the
      rare but high-value anchors where we can be fairly sure who the speaker is.
    """
    from collections import Counter

    per_staff: Counter[str] = Counter()
    strong_anchors: list[str] = []   # clips where speaker clearly named themselves
    any_mention_clips: int = 0
    no_mention: int = 0

    for wav, txt in transcripts.items():
        try:
            from edupulse.analysis import extract_staff_mentions, infer_likely_speaker

            mentions = extract_staff_mentions(txt, known_staff)
            name, conf = infer_likely_speaker(txt, known_staff)

            if mentions:
                any_mention_clips += 1
                for m in mentions:
                    per_staff[m] += 1

            if name and conf == "strong":
                per_staff[name] += 1   # count it for visibility
                strong_anchors.append(wav)

        except Exception:
            # very conservative fallback
            t = (txt or "").lower()
            for n in known_staff:
                if n.lower() in t:
                    per_staff[n] += 1
                    any_mention_clips += 1

    total_clips = len(transcripts)
    return {
        "total_clips": total_clips,
        "clips_with_any_staff_mention": any_mention_clips,
        "clips_with_strong_self_id": len(strong_anchors),
        "strong_self_id_wavs": strong_anchors,
        "per_staff_mention_counts": dict(per_staff.most_common()),
        "unique_staff_mentioned": len(per_staff),
    }


def build_speaker_feasibility_report(
    wav_dir: str | None,
    transcripts: dict[str, str],
    known_staff: list[str],
    durations: dict[str, float] | None = None,  # wav_name -> seconds (from sidecar preferred)
    run_identification: bool = True,
    diarize: bool = False,
    report_path: str | None = None,
    hf_token: str | None = None,
) -> dict[str, Any]:
    """End-to-end skeleton run for a capture session or validation set.

    - Always produces transcript-based supervision / mention stats (no torch needed).
    - If pyannote embeddings available: mines enrollments across the set,
      attempts identification, reports hit rate on the enrollable clips.
    - Optional diarization pass (slow, usually 1 segment per short tx).
    - Emits a human-readable markdown report (written if report_path given).
    - Designed to be called from test_speaker.py or a future capture post-processor.

    Returns the full report dict (stats + per-clip results + notes).
    """
    from collections import Counter
    import datetime as _dt

    report: dict[str, Any] = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "wav_dir": wav_dir,
        "num_known_staff": len(known_staff),
        "num_transcripts": len(transcripts),
        "transcript_stats": {},
        "embedding_available": False,
        "diarization_available": False,
        "per_clip": [],
        "summary": {},
        "feasibility_notes": [],
    }

    # 1. Transcript supervision (always) — now aware of caller vs receiver problem
    tstats = compute_transcript_mention_stats(transcripts, known_staff)
    report["transcript_stats"] = tstats

    # 2. Try embeddings — this is where the real speaker inference happens
    discovered = _discover_hf_token(hf_token)
    db = get_speaker_database(known_staff=known_staff, hf_token=discovered)
    report["embedding_available"] = bool(db and db.is_available())

    diar = get_speaker_diarizer(hf_token=discovered) if diarize else None
    report["diarization_available"] = bool(diar and diar.is_available())

    strong_anchor_count = tstats.get("clips_with_strong_self_id", 0)
    enrolled_names: Counter[str] = Counter()
    identified_count = 0
    speaker_confidences: list[float] = []

    for wav_name, txt in transcripts.items():
        clip: dict[str, Any] = {
            "wav": wav_name,
            "transcript_preview": (txt or "")[:90],
            "duration_sec": (durations or {}).get(wav_name),
            "enrolled_from_this": [],
            "identified": None,
            "conf": 0.0,
            "diar_segments": 0,
            "strong_self_id": False,
        }

        if db is not None:
            enr = db.mine_and_enroll(wav_name if wav_dir else wav_name, txt, known_staff)
            clip["enrolled_from_this"] = enr
            for n in enr:
                enrolled_names[n] += 1
                clip["strong_self_id"] = True

            if run_identification:
                name, conf = db.identify(wav_name if wav_dir else wav_name)
                if name:
                    clip["identified"] = name
                    clip["conf"] = round(conf, 3)
                    identified_count += 1
                    speaker_confidences.append(conf)

        if diar is not None:
            segs = diar.diarize( (wav_dir + "/" + wav_name) if wav_dir else wav_name )
            clip["diar_segments"] = len(segs)

        report["per_clip"].append(clip)

    # Summaries
    report["summary"] = {
        "strong_self_id_anchors": strong_anchor_count,
        "unique_staff_with_strong_anchors": len(enrolled_names),
        "clips_identified_by_voice": identified_count,
        "mean_identification_conf": round(sum(speaker_confidences) / len(speaker_confidences), 3) if speaker_confidences else 0.0,
        "top_anchored_staff": enrolled_names.most_common(10),
    }

    # Practical feasibility notes — now explicitly addressing the user's point
    notes: list[str] = []
    total_clips = tstats["total_clips"]

    notes.append(
        "KEY REALITY FOR THIS DATA: On most transmissions the speaker names the "
        "*person they are calling* (e.g. 'Mr. Moore to Dr. Strickland'), not themselves. "
        "Text alone is therefore a weak and sometimes actively misleading signal for who is speaking. "
        "The primary inference method must be the voice embedding (acoustic parameters), "
        "with text used only as occasional high-confidence anchors."
    )

    if total_clips:
        short = sum(1 for c in report["per_clip"] if (c.get("duration_sec") or 0) < 1.5)
        notes.append(
            f"{short}/{total_clips} clips are <1.5s (typical for crisp PTT). "
            "Very short clips are excellent for transcription but limit within-clip diarization. "
            "Whole-clip voice embedding remains the most promising approach."
        )

    notes.append(
        f"Strong self-ID anchors found: {strong_anchor_count} out of {total_clips}. "
        "These are the clips where the speaker clearly named themselves ('Go for X', 'This is X', etc.). "
        "They are the highest-value seeds for labeling voice clusters."
    )

    if strong_anchor_count < 5 and total_clips > 20:
        notes.append(
            "Warning: Very few strong self-identification moments in this set. "
            "Voice clustering will be essential — we will need to group similar-sounding clips "
            "first, then label the groups using the rare anchors."
        )

    if tstats["unique_staff_mentioned"] >= 8:
        notes.append(
            f"Transcripts mention {tstats['unique_staff_mentioned']} distinct staff. "
            "Repeated voices will still dominate any airtime analysis once we can attribute them reliably via voice."
        )

    if not report["embedding_available"]:
        notes.append(
            "pyannote embeddings not available in this environment (torch + pyannote.audio required). "
            "The numbers above show the *text anchor* situation only. "
            "Install with: pip install pyannote.audio (plus a Hugging Face token)."
        )

    report["feasibility_notes"] = notes

    # Write human report if requested
    if report_path:
        try:
            lines = [
                "# EduPulse Speaker Feasibility Report (pyannote skeleton)",
                f"Generated: {report['generated_at']}",
                f"Source: {wav_dir or '(transcripts provided directly)'}",
                f"Known staff list size: {report['num_known_staff']}",
                "",
                "## Important Context for This Radio Data",
                "On school radio, the speaker usually names the *recipient* of the call,",
                "not themselves. Example: 'Mr. Moore to Dr. Strickland' means Mr. Moore is",
                "probably speaking. Text mentions are therefore often misleading for speaker ID.",
                "The system is designed so that voice (embedding) does the heavy lifting.",
                "",
                "## Transcript Anchors (text only — no voice model needed)",
                f"- Total clips with transcripts: {tstats['total_clips']}",
                f"- Clips with any staff name mentioned: {tstats['clips_with_any_staff_mention']}",
                f"- Strong self-ID anchors (speaker named themselves): {tstats['clips_with_strong_self_id']}",
                "",
                "### Staff appearing in transcripts",
            ]
            for name, cnt in tstats["per_staff_mention_counts"].items():
                lines.append(f"- {name}: {cnt}")
            lines.append("")
            lines.append("## Voice Embedding / Identification Layer")
            lines.append(f"- Embeddings available (pyannote): {report['embedding_available']}")
            lines.append(f"- Diarization available: {report['diarization_available']}")
            lines.append(f"- Clips given a speaker label via voice: {identified_count}")
            if report["summary"]["mean_identification_conf"]:
                lines.append(f"- Mean confidence on labeled clips: {report['summary']['mean_identification_conf']}")
            lines.append(f"- Unique staff that received at least one strong voice anchor: {len(enrolled_names)}")
            lines.append("")
            lines.append("## Feasibility Notes")
            for n in notes:
                lines.append(f"- {n}")
            lines.append("")
            lines.append("## Recommended Approach Going Forward")
            lines.append("1. Extract voice embeddings for every clip (when pyannote is installed).")
            lines.append("2. Cluster or match embeddings to find 'same voice' groups across many transmissions.")
            lines.append("3. Use the rare strong self-IDs ('Go for X') as reliable labels for those clusters.")
            lines.append("4. Propagate the label to other clips that sound like the same person.")
            lines.append("5. Only write `primary_speaker` into sidecars that came from the heavy (large-v3) model.")
            lines.append("")
            lines.append("The VAD + heavy transcription core remains the only required fidelity contract.")
            with open(report_path, "w") as f:
                f.write("\n".join(lines) + "\n")
            report["report_written"] = report_path
        except Exception as e:
            report["report_write_error"] = str(e)

    return report


# =============================================================================
# RICHER ACOUSTIC / PROSODY FEATURES (additive to speaker + transcription)
# =============================================================================
# These give metrics on *how* something was said (volume, activity, delivery),
# which is exactly the point of the tx_2026-06-05_10-32-03_5.7s example:
# transcription (even large-v3) can be garbage on noisy radio, but the
# delivery characteristics + who is speaking + VAD still carry signal.
# =============================================================================

def compute_transmission_features(
    wav_path: str,
    hf_token: str | None = None,
    include_diar: bool = True,
) -> dict[str, Any]:
    """Extract basic acoustic features from a transmission clip.

    Returns a dict with:
      - duration_sec, rms, peak, approx_dbfs
      - active_speech_sec (from diarization if available, else energy proxy)
      - speech_ratio, onset_rate (crude "punchiness")
      - diar_segments (list) if include_diar and diarizer works
      - embedding (if embedder available) for convenience
      - notes

    Volume and activity are always useful. Inflection/urgency are higher-order
    and benefit from optional pitch (librosa) later; for now we surface the
    raw material (energy contour stats) that such metrics would be built on.
    """
    result: dict[str, Any] = {
        "wav": os.path.basename(wav_path),
        "duration_sec": None,
        "rms": None,
        "peak": None,
        "approx_dbfs": None,
        "active_speech_sec": None,
        "speech_ratio": None,
        "onset_rate": None,
        "diar_segments": [],
        "embedding": None,
        "notes": [],
    }

    # 1. Waveform via the same loader the embedder uses (pyannote.audio.Audio or fallback)
    waveform = None
    sr = 16000
    try:
        from pyannote.audio import Audio as PAudio
        audio = PAudio(sample_rate=sr, mono=True)
        wf, _ = audio(wav_path)
        if hasattr(wf, "ndim"):
            if wf.ndim == 1:
                wf = wf.unsqueeze(0)
            if wf.shape[0] > 1:
                wf = wf.mean(dim=0, keepdim=True)
            waveform = wf.squeeze().cpu().numpy().astype(float) if hasattr(wf, "cpu") else np.asarray(wf).squeeze().astype(float)
    except Exception:
        # Fallback to wave (stdlib) + numpy - works for the 16-bit PCM files we produce
        try:
            import wave
            with wave.open(wav_path, "rb") as w:
                sr = w.getframerate()
                raw = w.readframes(w.getnframes())
                samples = np.frombuffer(raw, dtype=np.int16).astype(float) / 32768.0
                if w.getnchannels() == 2:
                    samples = samples.reshape(-1, 2).mean(axis=1)
                waveform = samples
        except Exception as e:
            result["notes"].append(f"waveform load failed: {e}")
            waveform = None

    if waveform is not None and len(waveform) > 0:
        dur = len(waveform) / float(sr)
        result["duration_sec"] = round(dur, 3)
        rms = float(np.sqrt(np.mean(waveform ** 2)))
        peak = float(np.max(np.abs(waveform)))
        result["rms"] = round(rms, 6)
        result["peak"] = round(peak, 6)
        result["approx_dbfs"] = round(20 * np.log10(rms + 1e-9), 1)

        # Frame energy for onsets / activity proxy (50ms frames)
        fl = int(0.050 * sr)
        hop = int(0.025 * sr)
        if fl > 0 and len(waveform) > fl:
            ens = []
            for i in range(0, len(waveform) - fl, hop):
                ens.append(np.sqrt(np.mean(waveform[i : i + fl] ** 2)))
            ens = np.asarray(ens)
            if len(ens) > 1:
                onsets = int(np.sum(np.diff(ens) > (0.4 * (ens.std() + 1e-9))))
                result["onset_rate"] = round(onsets / dur, 2)
                # crude active using energy
                act = float((ens > (ens.mean() + 0.3 * ens.std())).sum() * (hop / sr))
                result["active_speech_sec"] = round(act, 3)
                result["speech_ratio"] = round(act / dur, 3) if dur > 0 else 0.0

    # 2. Optional diarization (gives the clean "who spoke when" turns)
    if include_diar:
        try:
            diar = get_speaker_diarizer(hf_token=hf_token)
            if diar is not None:
                segs = diar.diarize(wav_path)
                result["diar_segments"] = segs
                if segs:
                    total_speech = sum(s["end"] - s["start"] for s in segs)
                    result["active_speech_sec"] = round(total_speech, 3)
                    if result["duration_sec"]:
                        result["speech_ratio"] = round(total_speech / result["duration_sec"], 3)
        except Exception as e:
            result["notes"].append(f"diarization features failed: {e}")

    # 3. Embedding (for convenience / clustering this transmission)
    try:
        emb = SpeakerEmbedder(hf_token=_discover_hf_token(hf_token))
        if emb.is_available():
            result["embedding"] = emb.embed(wav_path)
    except Exception:
        pass

    # Notes
    if result["duration_sec"] and result["duration_sec"] > 4.0:
        result["notes"].append("Longer transmission (>4s) — good candidate for within-clip diarization and prosody.")
    if result.get("approx_dbfs") is not None and result["approx_dbfs"] > -15:
        result["notes"].append("Relatively hot/loud level — consider as a volume/urgency cue.")

    return result


def get_pyannote_enrichment(
    wav_path: str,
    known_staff: list[str] | None = None,
    include_diar: bool = False,
    hf_token: str | None = None,
) -> dict[str, Any]:
    """Return a dict of pyannote-derived fields ready to merge into a sidecar JSON.

    This is the central place for "all available data from pyannote" in sidecars
    (going forward in the recorder and retroactively via update helpers).

    Contents (only populated fields are included):
      - primary_speaker: str | None
      - speaker_conf: float
      - speaker_segments: list of {"start":, "end":, "speaker":} from diarization (if include_diar)
      - acoustic_features: dict with rms, peak, approx_dbfs, onset_rate, speech_ratio,
        active_speech_sec, duration_sec (always attempted, cheap even without pyannote)

    The raw embedding vector is NOT stored in sidecars (too large; use the caches + DB for that).
    Diarization is optional and recommended only for longer clips.
    """
    out: dict[str, Any] = {}

    # Acoustic + optional diar (this function already falls back gracefully)
    feats = compute_transmission_features(
        wav_path, hf_token=hf_token, include_diar=include_diar
    )

    # Acoustic features (core for volume, urgency proxies, etc.)
    acoustic = {}
    for k in ("rms", "peak", "approx_dbfs", "onset_rate", "speech_ratio", "active_speech_sec", "duration_sec"):
        val = feats.get(k)
        if val is not None:
            acoustic[k] = val
    if acoustic:
        out["acoustic_features"] = acoustic

    # Diarization turns (pyannote's direct output)
    segs = feats.get("diar_segments") or []
    if segs:
        out["speaker_segments"] = segs

    # Speaker identification against the running DB (voice primary)
    try:
        db = get_speaker_database(known_staff=known_staff, hf_token=hf_token)
        if db and db.is_available():
            name, conf = db.identify(wav_path)
            if name:
                out["primary_speaker"] = name
                out["speaker_conf"] = round(conf, 3)
            else:
                out["primary_speaker"] = None
                out["speaker_conf"] = round(conf, 3) if conf else 0.0
    except Exception:
        pass

    return out


def update_sidecar_with_pyannote(
    wav_path: str,
    include_diar: bool = False,
    known_staff: list[str] | None = None,
    hf_token: str | None = None,
    backup: bool = True,
) -> bool:
    """Retroactively (or in post-process) enrich an existing sidecar with pyannote data.

    Loads the .json next to the wav (if present), merges the enrichment from
    get_pyannote_enrichment, and writes it back. Optionally backs up first.

    Returns True on success.
    Use this in batch scripts for existing capture days.
    """
    from pathlib import Path
    import json as _json

    wav_p = Path(wav_path)
    side_p = wav_p.with_suffix(".json")
    if not side_p.exists():
        return False

    try:
        with open(side_p, "r", encoding="utf-8") as f:
            meta = _json.load(f)
    except Exception:
        return False

    if backup:
        bak = side_p.with_suffix(".json.pyannote-bak")
        if not bak.exists():
            try:
                bak.write_text(side_p.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass

    enrich = get_pyannote_enrichment(
        str(wav_p), known_staff=known_staff, include_diar=include_diar, hf_token=hf_token
    )

    # Merge: don't clobber existing good data with empty
    for k, v in enrich.items():
        if v or k not in meta:
            meta[k] = v

    try:
        with open(side_p, "w", encoding="utf-8") as f:
            _json.dump(meta, f, indent=2)
        return True
    except Exception:
        return False
