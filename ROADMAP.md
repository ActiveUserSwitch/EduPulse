# EduPulse Roadmap (Post-Collection)

**Status:** School-year data collection is complete. We have
raw per-transmission audio + metadata from the final days
(plus earlier tests). The 3-month break is for turning
that raw material into high-quality, validated output.

Use `retag_session.py` + `analyze_manifest.py` + 
`test/test_whisper.py` (with the fingerprint files) as the
primary workflow.

## Must-Do (in rough priority)

1. **Maintain the live fingerprint files**
   - `hardware/capture/staff_names.txt` — full legal names
     of teaching and admin staff (one per line). This is
     the highest-leverage single thing you can do.
   - `hardware/capture/common_words.txt` — the actual
     words and short phrases that flew on the radio this
     year (chromebook returns, test monitoring, building
     numbers, 10-4, specific call signs, exam logistics
     language, etc.).
   - These two files are fed to both Whisper and the
     IncidentTracker. Keep them current.

2. **Re-transcribe the marginal segments with heavier models**
   - Priority targets (from the retagged manifests):
     - Everything currently flagged Noise / low-conf
       (< ~0.40)
     - Short segments (< 1.5–2 s) in Other / Unclear
     - Any segment that produced obvious hallucinations
       (e.g. "Thanks for watching")
   - Command template:
     ```bash
     python test/test_whisper.py \
       --file <path-to-tx_....wav> \
       --model base \                 # or medium / large-v3
       --known-staff-file hardware/capture/staff_names.txt \
       --common-words-file hardware/capture/common_words.txt \
       --initial-prompt "School administrative radio \
traffic, logistics, dismissals, hallway movement, staff \
roles (Mr, Mrs, Coach, Nurse, Officer, etc.), EOC, 500 \
building, Chromebook, instructors, 10-4, test monitoring, \
bio retake. Pure school radio only — no video sign-offs, \
no 'thanks for watching'."
     ```
   - Update the corresponding sidecar (or produce a parallel
     "validated" manifest) with the better transcript.

3. **Re-apply analysis after better transcripts**
   - After you have improved transcripts for a session, run:
     ```bash
     python hardware/capture/retag_session.py \
       <session>/session_manifest.jsonl \
       --known-staff-file hardware/capture/staff_names.txt \
       --common-words-file hardware/capture/common_words.txt
     ```
   - This updates categories and INC linking with the
     current rules + fingerprint.

4. **Expand categories and noise filter from real data**
   - Add real phrases that appeared in the finals chatter
     to the keyword lists in `edupulse/analysis.py`
     (especially under Logistics and Testing).
   - Add any new hallucination patterns you observe to
     `is_likely_noise`.
   - Re-run retag after changes and compare quality
     reports.

5. **Validation + metrics (the actual research output)**
   - Pick 40–60 real transmissions from the last two days.
   - Listen to the raw .wav while reading the best
     available transcript + category + INC.
   - Score transcription accuracy, categorization, and
     incident linking.
   - From the cleaned retagged manifests, compute the
     things we originally cared about: response patterns,
     busiest categories/times during finals stress, role
     participation (who talks on the radio), student
     mention rate, INC length distributions, etc.

6. **Prepare for return to Pi**
   - Any VAD parameter lessons that worked well on real
     data (pre-roll, tail padding, silence timeout,
     adaptive margin, etc.).
   - Storage layout and rotation strategy that survived
     a full day.
   - One-channel audio handling (we auto-select dominant;
     document any remaining gotchas).
   - Systemd / always-on service skeleton (if not already
     present).

## Nice-to-Haves (lower priority)

- A small `reprocess_session.py` helper that walks one
  session dir and produces a fully validated manifest +
  short report.
- A simple notebook or set of scripts that turn the
  retagged manifests into the organizational metrics
  you want.
- Grow the fingerprint files from the actual transcripts
  produced during the break (not just what you remember
  hearing live).
- **Speaker / voice recognition (pyannote.audio skeleton already present)**
  - `edupulse/speaker.py` + `test/test_speaker.py` + `extract_staff_mentions`
    in analysis.py give you the start for per-transmission speaker ID
    and (later) airtime stats.
  - Run `python test/test_speaker.py` (it auto-falls back to the hand-coded
    validation transcripts for a demo, or point it at a real capture dir +
    the large-v3 transcripts.txt).
  - The output report + `build_speaker_feasibility_report` tell you how
    many clean single-staff clips you have for enrollment, coverage of the
    101-voice list, and practical notes (short 1-4 s PTT clips are great for
    transcription but limit within-clip diarization).
  - When ready: `pip install pyannote.audio`, accept the HF model cards,
    set HF_TOKEN, then re-run with `--diarize` on real data.
  - Goal (per user): once accurate, use primary_speaker + speaker_conf
    (written only into heavy-model sidecars) for distributed leadership,
    participation equity, who talks most by role, etc.
  - This stays strictly above the VAD + transcription core.

## When You Come Back After the Break

1. Activate the env and run `retag_session.py` on every
   session using the current `staff_names.txt` +
   `common_words.txt`.
2. Run `analyze_manifest.py` on the resulting
   `.retagged.jsonl` files and read the Data Quality
   Summary.
3. Look at the list of remaining low-quality segments and
   decide what to re-transcribe next with heavier models.
4. Iterate rules → retag → measure quality. Repeat.

The raw `.wav` files + the two fingerprint text files are
the only things that truly need to survive the break
intact.

## June 2026 Updates (post-collection iteration)

- **Full sidecar standardization**: Every WAV now (or via the retro script) has large-v3 transcription as the canonical field in its sidecar. Old light-model sidecars are upgraded in place.
- **Pyannote data in every sidecar** (retro + forward): `acoustic_features` (volume, onset_rate, speech_ratio etc.), `primary_speaker`/`speaker_conf`, `speaker_segments` (diar for longer clips). See `get_pyannote_enrichment` / `update_sidecar_with_pyannote` and the recorder integration.
- **Retro tool**: `hardware/capture/retro_upgrade_sidecars.py` (handles heavy trans via project logic + analysis + pyannote). Run per day with limits as needed.
- **Semantic map from accumulated traffic (not for recognition)**: `build_radio_semantic_map` in edupulse/analysis.py. Purely post-hoc mining of heavy transcripts + metadata for dissertation data (staff-location bindings, protocol pairs, crisis clusters, etc.). Example snapshot in `semantic_map_radio_traffic.json`. Seeded from the bookmarked fight report.
- **Critical transmission baseline**: The fight report (`tx_2026-06-05_10-32-03_5.7s`, tagged `fight_report`, `critical_baseline: true`) + its pyannote acoustic signature used as anchor. Comparison across enriched clips produced recommended 65-75% composite threshold (combined with keywords + voice sim).
- **Documentation**: This ROADMAP + README now include the full pipeline flowchart (mermaid) and the separation of live/retro/post layers.

All future work preserves the core contract: pristine WAVs + heavy-model sidecars only. Speaker/acoustic/semantic layers are additive for analysis and airtime/leadership metrics.

## Probabilistic Language Modeling Roadmap (for Normal Radio Traffic & Surprisal)

**Motivation (from analysis limitations):** 
Current `build_radio_semantic_map` uses co-occurrence / entity graphs. This is useful for clusters (staff-location, crisis terms, protocol pairs) but is not a true probabilistic language model. It relies on simple unigram-like rarity for content surprisal proxies. We lack:
- Sequence-aware modeling (bigrams, trigrams, or neural for structure, proword patterns, call-response, entity chains like "Go for X" → response).
- A large, clean, labeled "normal" corpus (unigram is weak; we have ~143 high-quality transcripts from hand-coded day 2026-06-05 + graduation + validation gold, but this is small and we deliberately exclude pre-06-05 noisy early days).
- Per-sequence or per-clip true self-information: -log₂(p) under a model of "normal" school radio language (vs. rare crisis/urgent events like the fight report anchor).

Goal: Build a domain-specific PLM of "normal" radio traffic (procedural, low-urgency logistics, testing, movement, staff coordination using prowords, titles, common words). Use it for:
- Accurate lexical/sequence surprisal on new clips (high -log p = high information = candidate for urgency/critical/leadership-under-stress).
- Combine with existing acoustic z-scores (rms, speech_ratio, onset_rate, active time, duration — already prototyped vs. 06-05 baselines) and pyannote features into a multi-modal "information score".
- Bootstrap better anomaly/urgency detection without needing perfect labels upfront.
- Dissertation value: quantitative measures of information in institutional radio under stress.

**Scope restrictions (per prior decisions):**
- Corpus for "normal" model: Strictly hand-coded day (2026-06-05_last-day-2, now 100% large-v3) + graduation (2026-06-09) + validation CSVs (human gold + large-v3 from the stratified sample). ~143+ clean transcripts / ~1200+ tokens as starting point.
- Explicitly exclude earlier days (06-02/03/04) for the normal LM and semantic map to avoid light-model noise (upgrades on those days are paused/stopped).
- Critical/outlier clips (e.g., the bookmarked fight report `tx_2026-06-05_10-32-03_5.7s` with "They're fighting!", high acoustic intensity/speech density) are held out as positive high-surprisal examples for validation, not mixed into the "normal" training distribution.
- All modeling stays post-accumulation (never in live recognition/transcription/prompting). Heavy large-v3 sidecars + pyannote data are prerequisites.

**Phased Roadmap (Short / Medium / Long term, during break + return):**

1. **Foundation & Data (immediate, 1-2 weeks):**
   - Formalize a "normal_corpus" loader in `edupulse/analysis.py` (or new `edupulse/language_model.py`): hard-coded to the allowed days + validation CSVs, filter large-v3 + clean text (no "subtitles/amara", min length), exclude known critical clips (use tags like "fight_report" or acoustic z-score thresholds from the critical baseline work).
   - Build a small "normal" reference set of transcripts + metadata (acoustic features, speaker info, duration, proword usage).
   - Tokenization: Improve beyond raw words — normalize entities (staff titles/last names via existing `extract_staff_mentions`), treat prowords ("10-4", "go for", "on my way") as atomic units, add markers for call structure (e.g., "CALLER: ...", "RESPONSE: ...", location mentions).
   - Baseline stats: Extend the acoustic z-score machinery (already in the fight report analysis and `compute_transmission_features`) to a reusable `compute_acoustic_zscores(clip_features, baseline_stats)` that can be updated incrementally per day.
   - Quick win: Upgrade the current co-occurrence map to simple bigram/trigram counts on the cleaned normal corpus. Compute per-clip average surprisal as proxy -log p (using the n-gram model). Compare fight report vs. normal clips.

2. **N-gram LM + Hybrid Surprisal (short term, 2-4 weeks):**
   - Implement `build_normal_ngram_lm(corpus, order=3)` and `compute_sequence_surprisal(text, lm, smoothing="add1")` returning mean -log2(p) per token or total.
   - Add to sidecars (post heavy trans): "lexical_surprisal", "proword_deviation", "structure_score" (e.g., presence/absence of expected call-response patterns).
   - Hybrid score: Combine lexical surprisal (normalized or z-scored against normal distribution) with acoustic z-composite (rms_z + speech_ratio_z + duration_z + onset_z, as prototyped). This directly addresses the quoted limitation by moving beyond unigram.
   - Validation: Use the fight report + any other user-labeled critical clips as high-surprisal positives. Measure separation (e.g., surprisal of fight vs. mean normal). Cross-check against human "urgency" ratings on a small held-out set from the hand-coded sample.
   - Batch-at-complete-sampling (the path taken per latest user direction: "I dont need a live z score, lets create a field for it if we dont have one and populate it when we batch all the days files.  Then we can aggrigate all of them when we have a 'Complete' sampling."):

     The live-Z inaccuracy problem described ("by the time the next transmission came in the score would be inaccurate because the data set had grown") is accepted. We do **not** persist live/causal z-scores or information scores in sidecars.

     Implementation (complete for the acoustic + phase-1 lexical layer):

     - `batch_populate_information_scores(day_dir)` (and `batch_populate_acoustic_zscores`) in `edupulse/analysis.py` is the *only* writer of the canonical `information_score` / `acoustic_zscores` / `lexical_surprisal` fields.
     - Invoked by `retro_upgrade_sidecars.py` (after heavy trans + pyannote for the day) — or manually — only once the day's files have been batched together.
     - Baseline is the current "complete" reference (2026-06-05 + graduation, criticals excluded via tags). See the detailed docstring on the batch functions for the definition of "Complete" sampling and re-aggregation steps.
     - `RunningNormalBaseline` (Welford) + the causal `compute_*_from_running` helpers still exist for optional experiments or provisional live displays, but **they are never used to write the sidecar fields**. All persisted `information_score` values are stable batch reference values.
     - When a new day reaches complete, add its path to the reference list and re-invoke batch population across all complete days. This is the "aggregate all of them" step.

     In practice:
     - Capture / retro upgrade day: large-v3 + full pyannote (acoustic_features etc.).
     - Batch-at-complete: run the populate (automatically at end of a retro day, or explicit call). Sidecars now contain the rich `information_score` object (value + lexical + acoustic_composite_z + reference + computed_at) plus `acoustic_zscores` and top-level `lexical_surprisal`.
     - Re-aggregate later: when the set of complete hand-coded days grows, refresh the reference and re-batch the prior complete days for comparable numbers.
     - The fight report remains excluded from every normal baseline so its high score is a clean anchor.

     - Acoustics: fully wired (rms, speech_ratio, onset, duration, active_speech, etc.).
     - Lexical (phase 1): proxy based on crisis seeds + protocol deviation (gives the fight clip non-zero lexical component now). Phase 2 will replace the proxy body of `compute_lexical_surprisal` + `load_hand_coded_onward_corpus` with real n-gram counts / -log2(p) trained strictly on the clean corpus.
     - Combined information_score: already computed and stored at batch time (weights currently balanced; tunable later against the fight anchor).
     - Future work (phase 2+): implement the n-gram LM, wire it, re-run batch on complete sets, keep the same sidecar field names.
   - Grow the corpus: As more days are captured/processed (post-break), add only high-quality large-v3 + human-reviewed if available. Bootstrap labels: high acoustic_z or lexical_surprisal clips can be flagged for quick user review to expand "normal" vs. "critical" sets.

3. **Neural / Modern LM (medium term, 4-8 weeks or post-break):**
   - Move beyond n-grams: Fine-tune a small causal LM (e.g., GPT-2 small or DistilGPT2 via Hugging Face transformers — check if available in env; otherwise start with simple LSTM/RNN on the tokenized radio text for sequences).
   - Domain adaptation: Train on the "normal" radio corpus (procedural language). Use the fight report and other outliers only for evaluation / few-shot prompting examples.
   - Better surprisal: Per-token -log p, sequence perplexity, or entropy. Detect "surprising" subsequences (e.g., the "They're fighting!" burst).
   - Multi-modal: Condition the LM on acoustic features (e.g., concatenate normalized z-scores or intensity/pitch as prefix tokens) or use late fusion for a joint information score.
   - Efficiency: For near real-time, the LM inference is fast on CPU once the model is small/fine-tuned; run after heavy transcription. Cache a base "normal" model and do lightweight online adaptation (e.g., few gradient steps or count updates for n-grams) as new normal clips arrive.
   - Evaluation: Human correlation on validation set; precision/recall for retrieving known critical clips (fight report as gold); downstream utility (does high surprisal + high acoustic z predict "leadership under stress" behaviors in speaker data?).

4. **Integration, Tooling & Deployment (ongoing + when returning to Pi):**
   - New functions in `edupulse/analysis.py`: `load_hand_coded_onward_corpus()`, `batch_populate_information_scores()`, `batch_populate_acoustic_zscores()`, `compute_lexical_surprisal()`, `compute_acoustic_zscores()`, `compute_information_score()` (all implemented; the batch funcs are the writers called from retro).
   - Extend existing: Make `build_radio_semantic_map` optionally use future LM probabilities. The recorder and retro already call the post-heavy path; information scores are attached only in the batch step.
   - Sidecar/manifest enrichment: `information_score` (object with value/lexical_surprisal/acoustic_composite_z/reference/computed_at), `acoustic_zscores`, and `lexical_surprisal` (only written for large-v3 sidecars during batch-at-complete-sampling). The fields are created if missing.
   - Reports & viz: Extend `analyze_manifest.py` or add `compute_information_report.py` that surfaces high-surprisal clips, plots z-score distributions, highlights clusters in the semantic map.
   - Real-time considerations: Acoustics z-scores and simple n-gram surprisal can be near real-time (per-clip after trans). Full neural LM is post-transcription but still "near" for the day's analysis. For ultra-low latency alerts, prototype a light-model proxy that is upgraded later. Maintain per-day or sliding-window baselines to handle context drift (e.g., finals vs. normal day).
   - Scaling the corpus: Tools to merge new days' validated transcripts into the normal reference (filtering out user-flagged critical ones). Version the LM alongside fingerprint files.
   - Dissemination: Use for the original goals — quantitative "information in radio under stress", participation by role in high-info events, distributed leadership signals (who initiates high-surprisal calls?).

**Risks & Mitigations:**
- Small starting corpus: Start with n-grams (robust with smoothing); use the existing co-occurrence map + acoustic z as strong baseline. Bootstrap more data from future captures.
- "Normal" definition drift: Explicitly version the normal corpus/LM per context (e.g., "finals_2026", "regular"). Allow user overrides for known high-stress but non-crisis periods.
- Latency: Heavy trans is the bottleneck for true real-time; z-scores/surprisal are cheap once text+features exist. Document this clearly.
- Overfitting to one school's radio: The LM will be highly domain-specific (good for this use case); keep it internal.

**Success Metrics:**
- High-surprisal clips (lexical + acoustic) correlate with user-labeled critical events (fight report as first gold standard).
- Improved separation in semantic map / urgency clusters when using LM surprisal vs. current co-occurrence.
- Actionable for downstream: e.g., "top 5% info_score clips account for X% of leadership turns" or better anomaly flagging than acoustics alone.
- Usable in the live pipeline (attached to sidecars, queryable in manifests) without violating the heavy-only / post-accumulation rules.

This directly evolves the current post-accumulation analysis (semantic map, critical baseline using the fight report's pyannote + lexical proxies) into a more principled information-theoretic framework while staying true to the project's narrowed focus (VAD + heavy transcription core; everything else additive and scoped to hand-coded day onward for cleanliness).

See also the existing "Critical / urgent transmission baseline" and "Post-accumulation analysis" sections above, and the multi-modal flow chart in the Processing Pipeline section of README.md.
