"""Post-accumulation acoustic z-scores and information_score batch writers."""
from __future__ import annotations

import re
from typing import Any, Optional

from .categories import is_likely_noise

def load_hand_coded_onward_corpus() -> list[dict]:
    """Return list of {"text": ..., "acoustic": ..., "critical": ..., "tx": ...}
    strictly from 2026-06-05 + graduation + validation CSVs (large-v3 + human gold).
    This is the ONLY data used for "normal" radio traffic modeling.
    Earlier days are excluded to avoid light-model noise.

    Used for future n-gram LM training, semantic baselines, and "complete"
    sampling re-aggregation. Called post-accumulation only.
    """
    import glob
    import json
    import os

    from .platform_util import default_reference_capture_dirs

    ref_dirs = default_reference_capture_dirs()
    items: list[dict] = []
    for d in ref_dirs:
        for j in glob.glob(os.path.join(d, "tx_*.json")):
            try:
                with open(j) as f:
                    m = json.load(f)
                if m.get("model") != "large-v3":
                    continue
                tags = m.get("tags", []) or []
                is_crit = bool(m.get("critical_baseline")) or ("fight_report" in tags)
                text = (m.get("transcription") or "").strip()
                if not text:
                    continue
                # light filter: skip obvious noise unless it is a known critical
                if not is_crit and is_likely_noise(text, float(m.get("duration_sec", 0) or 0), m.get("whisper_conf")):
                    continue
                ac = m.get("acoustic_features") or {}
                items.append({
                    "text": text,
                    "acoustic": ac,
                    "critical": is_crit,
                    "tx": os.path.basename(j).replace(".json", ""),
                    "duration_sec": m.get("duration_sec"),
                    "category": m.get("category"),
                    "dir": os.path.basename(d),
                })
            except Exception:
                continue

    # TODO (phase 1/2): also ingest validation/*.csv (human gold + large-v3 columns)
    # for additional clean transcripts when building n-gram counts.
    # For now the hand-coded day + grad sidecars provide the primary clean corpus.
    return items


def compute_lexical_surprisal(
    text: str,
    normal_lm: Optional[Any] = None,
    smoothing: str = "add1",
    **kwargs,
) -> dict[str, float]:
    """Return surprisal metrics for the transcript under a "normal" radio LM.

    When normal_lm is None or not yet implemented, falls back to a simple
    entity-rarity proxy (inspired by the current build_radio_semantic_map and
    fight-report seeds). Future (phase 2+) will use n-gram (or neural) LM
    trained ONLY on load_hand_coded_onward_corpus() and return real
    mean -log2(p) per token or total sequence surprisal.

    The resulting "lexical_surprisal" is combined with acoustic z-scores
    (see compute_information_score) for the multi-modal field stored in
    sidecars during batch-at-complete-sampling.

    This is deliberately post-accumulation only. No live z / surprisal.
    """
    if not text or not text.strip():
        return {"lexical_surprisal": 0.0}

    # Phase-1 proxy (until n-gram LM): use crisis/event seeds + protocol deviation
    # drawn from the same seeds as build_radio_semantic_map + the fight report anchor.
    # This gives the bookmarked fight clip a visibly higher lexical component immediately.
    # Real implementation will replace with:
    #   counts from normal corpus -> p(w) -> -log2(p + eps) averaged over tokens.
    t = " " + text.lower() + " "
    tokens = [w for w in re.findall(r"\b[a-z']+\b", text.lower()) if len(w) > 1]

    # High-surprisal seeds for school radio "normal" (logistics, prowords, routine)
    # vs. rare crisis/urgent content.
    crisis_seeds = {
        "fighting", "fight", "administrator", "admin", "backup", "emergency",
        "media center", "theyre", "they're", "now", "help",
    }
    protocol_common = {
        "copy", "roger", "10-4", "go for", "on my way", "thank you",
        "standing by", "yes", "no", "affirmative",
    }

    rare_hits = sum(1 for tok in tokens if tok in crisis_seeds)
    # Penalize very short routine acks a little; boost longer or crisis-containing.
    base = 0.8
    if any(p in t for p in protocol_common):
        base -= 0.3
    if rare_hits:
        base += 4.0 * (rare_hits / max(1, len(tokens)))

    # scale roughly toward bits-like range for the fight example (~4-9)
    surp = max(0.0, round(base + 1.5 * (rare_hits > 0), 3))

    notes = "phase-1 proxy (crisis seeds + protocol deviation); replace with n-gram -log2(p) from hand-coded onward corpus"
    if normal_lm is not None:
        notes = "normal_lm provided but n-gram/neural not yet wired; using proxy"

    return {
        "lexical_surprisal": surp,
        "notes": notes,
    }


def compute_acoustic_zscores(
    clip_features: dict[str, float],
    baseline_stats: Optional[dict[str, tuple[float, float]]] = None,
    **kwargs,
) -> dict[str, float]:
    """Return z-scores for acoustic features vs. a "normal" baseline.

    clip_features: dict from compute_transmission_features or sidecar
                   (rms, speech_ratio, onset_rate, duration_sec, active_speech_sec, ...)
    baseline_stats: {feature: (mean, std), ...}  — can be pre-computed from
                    the hand-coded day onward corpus or maintained as
                    running per-day / exponential moving averages for
                    near-real-time use.

    This is the direct extension of the z-score analysis performed on the
    fight report clip (rms z=+6.65, speech_ratio z=+5.90, etc. vs. 06-05 baselines).
    It is already feasible "near real time" per clip (after heavy transcription
    and feature extraction complete).

    Returns e.g. {"rms_z": 6.65, "speech_ratio_z": 5.90, "composite_z": ...}
    """
    if baseline_stats is None:
        # In a real implementation this would come from a persisted
        # reference computed on the restricted (06-05 + grad) corpus,
        # or be updated online.
        return {"notes": "No baseline_stats provided — z-scores not computed (stub)."}

    out = {}
    composite_parts = []
    for feat, (mu, sigma) in baseline_stats.items():
        if feat in clip_features and sigma > 0:
            z = (clip_features[feat] - mu) / sigma
            out[f"{feat}_z"] = round(z, 3)
            composite_parts.append(z)
    if composite_parts:
        out["acoustic_composite_z"] = round(sum(composite_parts) / len(composite_parts), 3)
    return out


def compute_acoustic_zscores_from_running(
    clip_features: dict[str, float],
    running_baseline: "RunningNormalBaseline",
) -> dict[str, float]:
    """Convenience wrapper: compute z-scores using a RunningNormalBaseline.

    This gives you the *causal* (live) z-score for the current clip,
    based only on normal clips that arrived before it.
    """
    baseline_stats = running_baseline.to_baseline_stats()
    return compute_acoustic_zscores(clip_features, baseline_stats=baseline_stats)


class RunningNormalBaseline:
    """Maintains running mean and variance (Welford's method) for acoustic features.

    This directly solves the problem: "live Z-scores would only be based on files
    collected before the current clip, and would become inaccurate later when
    the dataset grows."

    - zscores() always returns values computed from *previous* normal clips only
      (causal / what you would have seen live for this clip).
    - You only call update() on clips that are *later classified as normal*.
      This way the baseline never gets polluted by the high-surprisal events
      themselves.

    Two common ways to use it:
    1. Pure live/causal: never recompute old z-scores. Each clip keeps the number
       it had when it arrived (based on data before it).
    2. Live provisional + final reference: use the causal numbers for immediate
       awareness during the day, then at end-of-day (or after review) compute
       stable z-scores against the day's final normal stats (or against a
       long-term reference like the complete 2026-06-05 hand-coded day) for
       the semantic map and permanent analysis. The live numbers don't have to
       match the final ones.

    Typical causal usage during a day:
        baseline = RunningNormalBaseline()
        for clip in day_clips_in_order:
            live_z = baseline.zscores(clip["acoustic_features"])
            # ... decide is_normal using live_z + lexical surprisal etc. ...
            if is_normal:
                baseline.update(clip["acoustic_features"])

    At end of day:
        final_reference = baseline.to_baseline_stats()   # only normals
        # or load a long-term reference from previous clean days
    """
    def __init__(self):
        import math
        self._count = 0
        self._mean: dict[str, float] = {}
        self._m2: dict[str, float] = {}   # sum of squares of differences

    def update(self, features: dict[str, float]):
        """Incorporate a clip that has been classified as normal."""
        self._count += 1
        for k, v in features.items():
            if k not in self._mean:
                self._mean[k] = 0.0
                self._m2[k] = 0.0
            delta = v - self._mean[k]
            self._mean[k] += delta / self._count
            delta2 = v - self._mean[k]
            self._m2[k] += delta * delta2

    def zscores(self, features: dict[str, float]) -> dict[str, float]:
        """Z-scores using the statistics from *previous* normal clips only.
        This is the value you would have seen "live" for this clip.
        """
        import math
        out = {}
        if self._count < 2:
            return {k: 0.0 for k in features}

        for k, v in features.items():
            if k in self._mean:
                var = self._m2[k] / (self._count - 1)
                sigma = math.sqrt(var) if var > 0 else 0.0
                out[f"{k}_z"] = round((v - self._mean[k]) / sigma, 3) if sigma > 0 else 0.0

        if out:
            vals = [out[k] for k in out if k.endswith("_z")]
            if vals:
                out["composite_z"] = round(sum(vals) / len(vals), 3)
        return out

    def to_baseline_stats(self) -> dict[str, tuple[float, float]]:
        """Current (mean, std) suitable for passing to compute_acoustic_zscores."""
        import math
        out = {}
        for k in self._mean:
            if self._count > 1:
                var = self._m2[k] / (self._count - 1)
                sigma = math.sqrt(var) if var > 0 else 0.0
                out[k] = (self._mean[k], sigma)
        return out

    @property
    def count(self) -> int:
        return self._count


def compute_information_score(
    transcript: str,
    acoustic_features: dict[str, float],
    normal_lm: Optional[Any] = None,
    acoustic_baselines: Optional[dict[str, tuple[float, float]]] = None,
    weights: Optional[dict[str, float]] = None,
) -> dict[str, float]:
    """Combine lexical surprisal (future LM) with acoustic z-scores into one score.

    This is the concrete realization of using both content and signal features
    for high -log₂(p) detection, as discussed in the fight report analysis.
    Weights default to balanced; can be tuned using the fight report (and future
    labeled critical clips) as anchor points where both components are high.
    """
    weights = weights or {"lexical": 0.5, "acoustic": 0.5}
    lex = compute_lexical_surprisal(transcript, normal_lm=normal_lm)
    ac_z = compute_acoustic_zscores(acoustic_features, baseline_stats=acoustic_baselines)

    # Simple combination for now (will become weighted sum of normalized terms)
    info = {
        "lexical_surprisal": lex.get("lexical_surprisal", 0.0),
        "acoustic_composite_z": ac_z.get("acoustic_composite_z", 0.0),
    }
    info["information_score"] = (
        weights["lexical"] * info["lexical_surprisal"]
        + weights["acoustic"] * info["acoustic_composite_z"]
    )
    return info


def batch_populate_acoustic_zscores(
    day_dir: str,
    reference_dirs: list[str] | None = None,
    exclude_critical: bool = True,
    field_name: str = "acoustic_zscores",
) -> None:
    """Batch compute and attach z-scores (and the richer information_score) to
    all sidecars in day_dir.

    Uses a reference "normal" baseline computed from the hand-coded day (06-05)
    and onward (graduation), excluding critical clips (tagged fight_report or
    critical_baseline=True). This implements the user's request:
      "create a field for it if we dont have one and populate it when we batch
       all the days files. Then we can aggrigate all of them when we have a
       'Complete' sampling."

    This is strictly the batch/post-day (or post-complete-set) way.
    No live / causal z-scores or information_score are written by this path
    (RunningNormalBaseline remains available for optional future use but is
    not invoked here).

    Call this (or batch_populate_information_scores) after the day's files
    have all been upgraded (large-v3 + pyannote acoustic_features present).

    Adds / updates on each qualifying sidecar:
      "acoustic_zscores": {"rms_z": ..., "speech_ratio_z": ..., "acoustic_composite_z": ...}
      "zscores_reference": "hand_coded_day_onward"
      "information_score": {
          "value": <blended>,
          "lexical_surprisal": <proxy or future -logp>,
          "acoustic_composite_z": <...>,
          "reference": "...",
          "computed_at": "..."
      }
      "lexical_surprisal": <top-level convenience copy>

    "Complete" sampling definition:
      - A day reaches "complete" when all its transmissions have been captured,
        heavy-transcribed, pyannote-enriched, optionally human-reviewed, and
        criticals (fight_report, etc.) have been tagged.
      - At that point, run batch population for the day (populates using the
        current declared complete reference set).
      - When additional days reach complete, extend the reference_dirs list
        (or the defaults inside this func) with their paths and re-invoke
        batch_populate_* on *all* participating complete days. This re-aggregates
        the baseline stats from the larger "normal" pool and refreshes every
        sidecar's information_score with stable, comparable numbers.
      - The hand-coded day (2026-06-05) + graduation currently define the
        initial complete reference. Earlier days are deliberately excluded.
    """
    import glob
    import json
    import os
    from datetime import datetime
    from pathlib import Path

    if reference_dirs is None:
        from .platform_util import default_reference_capture_dirs

        reference_dirs = default_reference_capture_dirs()

    # 1. Collect reference acoustic features for "normal" clips
    ref_features = []
    for d in reference_dirs:
        for j in glob.glob(os.path.join(d, "tx_*.json")):
            try:
                with open(j) as f:
                    m = json.load(f)
                if m.get("model") != "large-v3":
                    continue
                if exclude_critical:
                    tags = m.get("tags", [])
                    if m.get("critical_baseline") or "fight_report" in tags:
                        continue
                ac = m.get("acoustic_features") or {}
                if ac and all(k in ac for k in ["rms", "speech_ratio"]):  # at least key ones
                    ref_features.append(ac)
            except Exception:
                continue

    if not ref_features:
        print(f"No reference features found for z-scores from {reference_dirs}")
        return

    # Compute baseline_stats (mean, std)
    feats = ["rms", "peak", "approx_dbfs", "onset_rate", "speech_ratio", "active_speech_sec", "duration_sec"]
    baseline_stats = {}
    for feat in feats:
        vals = [f[feat] for f in ref_features if feat in f and f[feat] is not None]
        if vals:
            n = len(vals)
            mu = sum(vals) / n
            var = sum((x - mu) ** 2 for x in vals) / n
            sigma = var ** 0.5
            baseline_stats[feat] = (mu, sigma)

    # 2. For the day_dir, for each sidecar, compute z + full information_score and attach
    day_path = Path(day_dir)
    updated = 0
    for j in glob.glob(str(day_path / "tx_*.json")):
        try:
            with open(j) as f:
                m = json.load(f)
            ac = m.get("acoustic_features") or {}
            if not ac:
                continue
            z = compute_acoustic_zscores(ac, baseline_stats=baseline_stats)
            m[field_name] = z
            m["zscores_reference"] = "hand_coded_day_onward"

            # Create the requested information_score field (batch only, at complete sampling time).
            # Uses the just-computed baseline + current (phase-1 proxy) lexical surprisal.
            trans = m.get("transcription", "") or ""
            info = compute_information_score(trans, ac, acoustic_baselines=baseline_stats)
            m["information_score"] = {
                "value": round(info.get("information_score", 0.0), 3),
                "lexical_surprisal": round(info.get("lexical_surprisal", 0.0), 3),
                "acoustic_composite_z": info.get("acoustic_composite_z", 0.0),
                "reference": "hand_coded_day_onward",
                "computed_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            # Convenience top-level (mirrors what many reports will query first)
            m["lexical_surprisal"] = m["information_score"]["lexical_surprisal"]

            with open(j, "w") as f:
                json.dump(m, f, indent=2)
            updated += 1
        except Exception as e:
            print(f"  zscore/info attach failed for {j}: {e}")
            continue

    print(f"Populated {field_name} + information_score for {updated} clips in {day_dir} using hand-coded reference.")
    print(f"  Reference clips used for normal baseline: {len(ref_features)}")
    print("  (information_score is batch-only; re-run after adding more complete days to re-aggregate)")


def batch_populate_information_scores(
    day_dir: str,
    reference_dirs: list[str] | None = None,
    exclude_critical: bool = True,
) -> None:
    """Primary entry point for the user's batch-at-complete-sampling request.

    Creates (if missing) and populates the "information_score" (and supporting
    acoustic_zscores / lexical_surprisal) fields for every large-v3 sidecar in
    the given day_dir.

    - Populated only when batch-processing all (or the complete set of) a day's files.
    - Baseline always drawn from the current "complete" reference (hand-coded day
      2026-06-05 + graduation, excluding tagged criticals).
    - When more days become "complete", update the reference list and re-invoke
      on the full set of complete days to re-aggregate.

    Delegates to the acoustic batch (which now also writes the information_score
    field). Safe to call multiple times; idempotent for already-processed clips
    (overwrites with fresh reference stats).
    """
    batch_populate_acoustic_zscores(
        day_dir,
        reference_dirs=reference_dirs,
        exclude_critical=exclude_critical,
    )

