"""EduPulse package.

Core: VAD + heavy-model transcription of school radio PTT transmissions.
Higher-order (optional): speaker diarization via pyannote.audio.

Canonical modules:
  categories, incidents, information_score, semantic_map, audio_io, vad, sidecar
  analysis  — back-compat re-exports
"""

from .analysis import (  # noqa: F401
    TRANSMISSION_CATEGORIES,
    IncidentTracker,
    batch_populate_acoustic_zscores,
    batch_populate_information_scores,
    build_enhanced_initial_prompt,
    build_radio_semantic_map,
    categorize_transmission,
    compute_acoustic_zscores,
    compute_information_score,
    compute_lexical_surprisal,
    default_tracker,
    extract_staff_mentions,
    infer_likely_speaker,
    is_likely_noise,
    load_hand_coded_onward_corpus,
)
from .platform_util import (  # noqa: F401
    default_captures_dir,
    find_preferred_input,
    is_windows,
    list_input_devices,
    print_input_devices,
)
from .sidecar import (  # noqa: F401
    TransmissionSidecar,
    build_sidecar,
    process_transcript,
)

try:
    from .speaker import (  # noqa: F401
        SpeakerDatabase,
        SpeakerDiarizer,
        SpeakerEmbedder,
        build_speaker_feasibility_report,
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
    compute_transmission_features = None  # type: ignore
    get_pyannote_enrichment = None  # type: ignore
    update_sidecar_with_pyannote = None  # type: ignore

__all__ = [
    "TRANSMISSION_CATEGORIES",
    "IncidentTracker",
    "TransmissionSidecar",
    "batch_populate_acoustic_zscores",
    "batch_populate_information_scores",
    "build_enhanced_initial_prompt",
    "build_radio_semantic_map",
    "build_sidecar",
    "categorize_transmission",
    "compute_acoustic_zscores",
    "compute_information_score",
    "compute_lexical_surprisal",
    "default_captures_dir",
    "default_tracker",
    "extract_staff_mentions",
    "find_preferred_input",
    "infer_likely_speaker",
    "is_likely_noise",
    "is_windows",
    "list_input_devices",
    "load_hand_coded_onward_corpus",
    "print_input_devices",
    "process_transcript",
    "enrich_with_speaker",
    "build_speaker_feasibility_report",
    "compute_transmission_features",
    "get_pyannote_enrichment",
    "update_sidecar_with_pyannote",
    "SpeakerDiarizer",
    "SpeakerEmbedder",
    "SpeakerDatabase",
    "get_speaker_database",
    "get_speaker_diarizer",
]
