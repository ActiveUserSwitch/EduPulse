# EduPulse Speaker Feasibility Report (pyannote skeleton)
Generated: 2026-06-09T15:08:19
Source: (transcripts provided directly)
Known staff list size: 101

## Important Context for This Radio Data
On school radio, the speaker usually names the *recipient* of the call,
not themselves. Example: 'Mr. Moore to Dr. Strickland' means Mr. Moore is
probably speaking. Text mentions are therefore often misleading for speaker ID.
The system is designed so that voice (embedding) does the heavy lifting.

## Transcript Anchors (text only — no voice model needed)
- Total clips with transcripts: 48
- Clips with any staff name mentioned: 15
- Strong self-ID anchors (speaker named themselves): 4

### Staff appearing in transcripts
- Mr. Bryan Marvel: 3
- Mr. Adrian Atkinson: 2
- Ms. Tracy Strickland: 2
- Ms. Valerie Simmeth: 2
- Ms. Goble: 1
- Mr. Shawn Johnston: 1
- Mr. Eldridge Moore: 1
- Mr. Joseph Hatfield: 1
- Ms. Goldsch: 1
- Ms. Shelley Gordon: 1
- Ms. Robyn Mobley: 1
- Mr. Samuel Mobley: 1
- Ms. Morgan Goltsch: 1
- Mr. Preston Furr: 1
- Ms. Stephanie Secker: 1
- Ms. Haley Davison: 1
- Ms. Shari Davison: 1
- Mr. Michael Boyes: 1

## Voice Embedding / Identification Layer
- Embeddings available (pyannote): False
- Diarization available: False
- Clips given a speaker label via voice: 0
- Unique staff that received at least one strong voice anchor: 0

## Feasibility Notes
- KEY REALITY FOR THIS DATA: On most transmissions the speaker names the *person they are calling* (e.g. 'Mr. Moore to Dr. Strickland'), not themselves. Text alone is therefore a weak and sometimes actively misleading signal for who is speaking. The primary inference method must be the voice embedding (acoustic parameters), with text used only as occasional high-confidence anchors.
- 48/48 clips are <1.5s (typical for crisp PTT). Very short clips are excellent for transcription but limit within-clip diarization. Whole-clip voice embedding remains the most promising approach.
- Strong self-ID anchors found: 4 out of 48. These are the clips where the speaker clearly named themselves ('Go for X', 'This is X', etc.). They are the highest-value seeds for labeling voice clusters.
- Warning: Very few strong self-identification moments in this set. Voice clustering will be essential — we will need to group similar-sounding clips first, then label the groups using the rare anchors.
- Transcripts mention 18 distinct staff. Repeated voices will still dominate any airtime analysis once we can attribute them reliably via voice.
- pyannote embeddings not available in this environment (torch + pyannote.audio required). The numbers above show the *text anchor* situation only. Install with: pip install pyannote.audio (plus a Hugging Face token).

## Recommended Approach Going Forward
1. Extract voice embeddings for every clip (when pyannote is installed).
2. Cluster or match embeddings to find 'same voice' groups across many transmissions.
3. Use the rare strong self-IDs ('Go for X') as reliable labels for those clusters.
4. Propagate the label to other clips that sound like the same person.
5. Only write `primary_speaker` into sidecars that came from the heavy (large-v3) model.

The VAD + heavy transcription core remains the only required fidelity contract.
