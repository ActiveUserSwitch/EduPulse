"""Back-compat re-exports for edupulse.analysis (split into focused modules).

Prefer importing from:
  edupulse.categories, edupulse.incidents, edupulse.information_score,
  edupulse.semantic_map, edupulse.fingerprint (build_enhanced_initial_prompt lives in categories).
"""
from __future__ import annotations

from .categories import (  # noqa: F401
    TRANSMISSION_CATEGORIES,
    build_enhanced_initial_prompt,
    categorize_transmission,
    is_likely_noise,
)
from .incidents import (  # noqa: F401
    IncidentTracker,
    default_tracker,
    extract_staff_mentions,
)
from .information_score import (  # noqa: F401
    RunningNormalBaseline,
    batch_populate_acoustic_zscores,
    batch_populate_information_scores,
    compute_acoustic_zscores,
    compute_acoustic_zscores_from_running,
    compute_information_score,
    compute_lexical_surprisal,
    load_hand_coded_onward_corpus,
)
from .semantic_map import (  # noqa: F401
    build_radio_semantic_map,
    infer_likely_speaker,
)

__all__ = [
    "TRANSMISSION_CATEGORIES",
    "IncidentTracker",
    "batch_populate_acoustic_zscores",
    "batch_populate_information_scores",
    "build_enhanced_initial_prompt",
    "build_radio_semantic_map",
    "categorize_transmission",
    "compute_acoustic_zscores",
    "compute_acoustic_zscores_from_running",
    "compute_information_score",
    "compute_lexical_surprisal",
    "default_tracker",
    "extract_staff_mentions",
    "infer_likely_speaker",
    "is_likely_noise",
    "load_hand_coded_onward_corpus",
    "RunningNormalBaseline",
]
