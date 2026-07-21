# What "Usable Yield" Means in EduPulse

From the validation spec (Chapter 12 – Estimation) and the implemented script:

**Definition**  
Usable yield = proportion of raw PTT detections that survive all filters and become structured, analyzable records.

Current implementation (compute_usable_yield):
- NOT flagged as noise (is_noise or "Noise / Squelch / Hallucination" category)
- whisper_conf >= threshold (we have used 0.40 / 0.55 / 0.70 / 0.85 in snapshots)
- category is one of the 12 specific categories (i.e. NOT "Other / Unclear")

In other words: the file has a reasonably confident transcription, is not pure squelch/hallucination, and the content is specific enough that the rudimentary keyword categorizer can assign it to one of the real radio purposes (Logistics, Discipline, Medical, etc.).

**Why we track it**  
Even if transcription is imperfect, we need a large enough volume of *categorized* events to compute the organizational metrics the dissertation cares about (busiest categories during finals stress, response patterns, role participation, INC lengths, student mention rates, etc.).

**Current reality (from the 2026-06-05 retagged data + 55 sample)**  
- At the live tiny model + old fingerprint: usable yield was very low at any sensible threshold.
- The proxy snapshot showed:
  - conf >= 0.40 : ~16%
  - conf >= 0.55 : ~8%
  - conf >= 0.70 : <1%
- This is why we are pushing large-v3 re-transcription of marginals + the updated titled staff list: higher confidence + cleaner text should move many "Other / Unclear" into real categories and raise the yield.

**Note on transcription vs categorization priority**  
You are correct — transcription accuracy is the proximate problem.  
Categorization is downstream of transcription quality. Bad transcripts → weak keyword matches → lots of "Other".  
Once we have better transcripts on the marginal files (large-v3 + current staff_names.txt), we re-run retag and the usable yield number should improve even before we do full human validation.

The 55-row validation sample already exists precisely so we can later measure *both* transcription fidelity (human listening) *and* the resulting categorization / incident / extraction agreement.

For now, with frozen fingerprints, the practical path is:
1. Re-transcribe the ~48 marginal files in the 55 (and the worst of the rest of the day) with large-v3.
2. Drop the new sidecars into processed/<day>/large-v3/ using the organizer or the helper script.
3. Re-tag.
4. Re-compute usable yield on the new outputs.
5. Human code the 55 for the real transcription quality numbers + downstream agreement.
