***EDUPULSE/__INIT__.PY FULL CONTENT FROM PREVIOUS CAT***
"""EduPulse package.

Core: VAD + heavy-model (large-v3) transcription of school radio PTT transmissions.
Higher-order (optional): speaker diarization / identification via pyannote.audio.

The canonical data contract is:
- pristine tx_*.wav files
- sidecars (tx_*.json) written only from the heaviest model results
- staff_names.txt + common_words.txt as living fingerprints

Speaker features (this module) are deliberately additive and never required for
the core VAD + transcription fidelity measurements.
"""

from .analysis import (  # noqa: F401
    TRANSMISSION_CATEGORIES,
    IncidentTracker,
    batch_populate_acoustic_zscores,
    batch_populate_information_scores,
    build_enhanced_initial_prompt,
    compute_acoustic_zscores,
    compute_information_score,
    compute_lexical_surprisal,
    default_tracker,
    extract_staff_mentions,
    infer_likely_speaker,
    is_likely_noise,
    load_hand_coded_onward_corpus,
)

# Safe optional re-exports (never fail the package import if torch/pyannote missing)
try:
    from .speaker import (  # noqa: F401
        SpeakerDatabase,
        SpeakerDiarizer,
        SpeakerEmbedder,
        build_speaker_feasibility_report,
        build_radio_semantic_map,
        compute_transmission_features,
        enrich_with_speaker,
        get_pyannote_enrichment,
        get_speaker_database,
        get_speaker_diarizer,
        update_sidecar_with_pyannote,
    )
except Exception:  # pragma: no cover
    SpeakerDatabase = None  # type: ignore
    SpeakerDiarizer = None  # type: ignore
    SpeakerEmbedder = None  # type: ignore
    build_speaker_feasibility_report = None  # type: ignore
    enrich_with_speaker = None  # type: ignore
    get_speaker_database = None  # type: ignore
    get_speaker_diarizer = None  # type: ignore

__all__ = [
    "TRANSMISSION_CATEGORIES",
    "IncidentTracker",
    "batch_populate_acoustic_zscores",
    "batch_populate_information_scores",
    "build_enhanced_initial_prompt",
    "compute_acoustic_zscores",
    "compute_information_score",
    "compute_lexical_surprisal",
    "default_tracker",
    "extract_staff_mentions",
    "infer_likely_speaker",
    "is_likely_noise",
    "load_hand_coded_onward_corpus",
    "enrich_with_speaker",
    "build_speaker_feasibility_report",
    "build_radio_semantic_map",
    "compute_transmission_features",
    "get_pyannote_enrichment",
    "update_sidecar_with_pyannote",
    "SpeakerDiarizer",
    "SpeakerEmbedder",
    "SpeakerDatabase",
    "get_speaker_database",
    "get_speaker_diarizer",
]