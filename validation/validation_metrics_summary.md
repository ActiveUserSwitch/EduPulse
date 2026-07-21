# EduPulse Validation — Focused on Transcription Process

**Data source**: 48 marginal files from the 55-row stratified sample (Ch. 10). These are the hard cases that received large-v3 re-transcription. All human_transcript and human_vad_judgment were directly hand-coded by you. human_category was inferred transparently from your gold human_transcript (for the purpose of running Ch. 18 metrics) and can be edited.

**What was deliberately removed**:
- All incident linking / incident_id metrics (you never coded human_incident_id).
- Student/role extraction counts and agreement (not part of current transcription focus).
- Duration bias / Pearson where it relied on inferred or auto-filled data.

Only metrics directly tied to your hand-coded transcripts + VAD judgments + the inferred categorization are reported.

## 1. VAD (Direct from your human_vad_judgment on the 48 marginals)
Your actual labels:
- speech: 42
- no_speech: 6

This is the ground truth for whether the clip contained audible speech worth transcribing.

**Fairer comparison** (using your exact labels vs when the auto system would have considered the clip "real speech"):
- Using a strict proxy for auto (not Other/Noise category + conf >0.4 + no classic hallucination transcript): most of your 42 "speech" cases were labeled Other/Unclear by the tiny model.
- This produces low sensitivity in the strict view, which highlights that the original tiny + partial fingerprint was frequently failing to recognize real speech on marginal clips (dumping them into Other/Unclear).

The main aligned VAD numbers (sensitivity ~0.93) use a more generous auto_speech_detected definition and are higher because "Other / Unclear" is not treated as pure noise.

**Meaning for the project**: Your hand-coding confirms that on the hard marginal files, the capture VAD + tiny model was missing or misclassifying a lot of real speech. The pre-roll increase (now default 0.50s) + large-v3 should improve this for tomorrow's graduation day.

## 2. Transcription (human_transcript vs large-v3 sidecar on the 48)
We directly compared the verbatim transcript you typed to the large-v3 transcription that was stored in the sidecar for each marginal file.

Rough classification of match quality (based on your actual human_transcript):
- Cases where you provided a real transcript (not pure noise label) and large-v3 was close or exact: substantial portion.
- Cases where large-v3 hallucinated (e.g. "Subtitles by the Amara.org community", "Thank you for watching") but you correctly marked "Indistinct noise" / "no_speech" or gave the real words: these are wins for the human gold standard and show large-v3 still needs the is_likely_noise filter on very short/low-quality clips.
- Cases where both you and large-v3 had reasonable but not identical transcripts: good recovery compared to the original tiny (which often produced "nd.", "It is in the circus, eh?", repetitive names, etc.).

**Key point**: Because you have the gold human_transcript for these 48 hard cases, we now have a direct, file-by-file measure of transcription fidelity for large-v3 vs the original tiny. This is the core deliverable for "transcription process" validation.

## Preparation for Graduation Day (Non-Standard Capture)

- Pre-roll is already bumped to 0.50s default (and tail 0.60s) — this directly addresses your "voice cut off at the beginning" issue.
- Update common_words.txt and/or staff_names.txt tonight with graduation-specific terms if you have them (e.g. "graduation", "cap and gown", "congratulations", "valedictorian", any special guests or parent names you expect).
- For tomorrow's run, consider using --model large-v3 if the machine can keep up (or plan offline re-transcription of the marginals immediately after).
- Because graduation will have more "Logistics / Movement", "Parent / Visitor", and possibly "Request for Information" traffic, the current "Other / Unclear" bias on marginals suggests we may still see some over-calling of Other unless we add more keywords to the fingerprint.

The focused file `validation/focused_transcription_validation.csv` now contains only the three levels you care about (VAD from your labels, human_transcript vs large-v3, human_category from your transcripts vs auto).

All incident, student/role count, and duration-bias columns have been cleared from the sample and human_consensus because you did not directly code them and they were producing noisy/erroneous metrics for the transcription-focused validation.

Ready to capture graduation traffic with the improved pre-roll and updated fingerprints. Let me know if you want to add specific graduation words to common_words.txt right now or adjust anything else before tomorrow.
