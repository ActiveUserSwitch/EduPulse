# Capture artifacts that corrupt school-radio ASR

**Status:** methods / findings note for dissertation & book  
**Date of discovery:** 2026-09-04 (human gold listen of disputed TX)  
**Corpus day:** `~/edupulse/captures/2026-09-04_school-day/`  
**Code fix:** `hardware/capture/record_with_transcribe.py`, `edupulse/vad.py` (pre-roll duplicate removed)

---

## Abstract

Two independent capture-side problems were identified while adjudicating low-confidence Whisper transcripts against human listening. Both produce **onset or intelligibility damage** that ASR models (Whisper large-v3, Grok STT) systematically misread as wrong names or invented phrases. Neither is primarily an “LLM repair” failure; both are **upstream of transcription**.

| # | Problem | Mechanism | Perceptual effect | ASR consequence |
|---|---------|-----------|-------------------|-----------------|
| **A** | Pre-roll double-append | Trigger audio block copied twice into the saved WAV | ~64 ms skip / stutter on first syllable | Name mangling (`Coach Richar` → `Codes for Shar`, `Trishar`, `Tricia`, …) |
| **B** | Hard clipping | Peak level hits digital full-scale (±1) for a non-trivial fraction of samples | Harsh, crushed consonants | Further ASR instability on the same onsets |

---

## Problem A — Pre-roll stitch duplicates ~64 ms at speech onset

### Intended design

EduPulse uses energy VAD with a **rolling pre-roll** (default **1.25 s**) so soft radio onsets are not cut off when the threshold is crossed. Each capture block is 1024 samples at 16 kHz ≈ **64 ms**.

### Bug

On the frame that first exceeds the speech threshold, the capture loop:

1. Appended the current block to `pre_buffer` (correct).  
2. Then started the segment as `pre_buffer[:] + [audio.copy()]` — **the same block again**.

So the saved transmission contained an **exact duplicate** of the trigger block at the pre-roll / speech boundary.

### Evidence (instrumental)

File: `tx_2026-09-04_12-03-42_3.8s.wav`  
Human gold: *“Mr. Harris to Coach L.”* (jitter during “Mr. Harris”).

- Exact consecutive duplicate of a 1024-sample block at **t ≈ 1.152 s** (length **64.0 ms**).  
- Jump at the nominal 1.25 s pre-roll *boundary* was tiny (~0.018) — the defect is **duplication**, not a gap between unrelated buffers.  
- Same human-reported “skip on Coach / first words” pattern on related clips the same day (e.g. `09-31-52`, `09-32-42`: gold *“Coach Richar.”* with skip on “Coach”).

### Evidence (perceptual / ASR)

| Clip | Human gold | Example machine outputs |
|------|------------|-------------------------|
| `09-32-42` | Coach Richar. (skip on Coach) | Whisper: `Codes for Shar.`; Grok STT: `Good afternoon, Tricia.` |
| `09-31-52` | Coach Richar. (small skip on Coach) | Whisper: `Current Trishar.`; Grok STT: `Patrick O'Shara.` |
| `12-03-42` | Mr. Harris to Coach L. (jitter on Mr. Harris) | Whisper: `This is the Harris Hotel.` |

Phonetic family: *Richar / Shar / Trishar / Tricia / Rochard* — consistent with a **mangled onset** of “Coach Richar,” not random LLM invention alone.

### Fix (future recordings)

Start the segment from the rolling pre-roll **only** (block already included):

```text
audio_buffer = pre_buffer[:]   # not pre_buffer + [audio]
```

Applied in both the live capture script and `edupulse/vad.py`. **Requires restarting `edupulse`** so new WAVs are clean. Existing files retain the duplicate unless re-captured.

### Dissertation framing

> Domain ASR evaluation must separate **model error** from **segmentation / buffering artifacts**. A 64 ms exact repeat at PTT onset is a deterministic capture bug that systematically biases name recognition on the first stressed syllable — the same locus where school radio identifies the callee.

---

## Problem B — Hard digital clipping from excess gain

### Observation

On `tx_2026-09-04_12-03-42_3.8s.wav` (dominant left channel):

- Peak ≈ **1.0** (full scale).  
- Fraction of samples with \|x\| > 0.99 ≈ **4.1%**.  
- Largest sample-to-sample jumps are **rail-to-rail** (±1), i.e. clipped waveform edges, not silence dropouts.

### Operational cause

Radio monitor level and/or UCA222 input gain set too high for peak PTT energy. Clipping is **in the recorded PCM**, so no later software stage can restore lost waveform peaks.

### ASR consequence

Clipped onsets destroy formant cues for consonants (/k/, /tʃ/ in “Coach”, stop bursts in “Harris”), compounding Problem A when both occur near the start of a call.

### Mitigation (operator + system)

1. **Operator:** lower radio volume / interface gain until live meters show headroom (peaks below ~−3 dBFS under typical key-ups).  
2. **System (future work):** optional peak warning in the capture UI when clip fraction exceeds a threshold; refuse or flag TX with high clip rate in sidecars (`levels` already store dB RMS).

### Dissertation framing

> For radio-derived corpora, **gain staging is a validity threat**. Clipping is irreversible information loss; reporting WER without documenting peak headroom and clip rate confounds acoustic conditions with model quality.

---

## Interaction of A and B

On several 2026-09-04 gold listens, **both** were present: onset stutter (A) plus crushed peaks (B). Machine pipelines then diverged:

- Whisper invented orthography from the damaged onset.  
- Text-only “repair” (Ollama) sometimes forced lexicon names (`Mayes`, `10-4`) without audio.  
- Grok STT (same stack as TUI voice dictation, WAV in) also disagreed with human gold on clipped/skipped onsets.

**Implication for methods:** second-pass LLM repair cannot substitute for clean capture; gold listening remains necessary for onset-critical protocol speech.

---

## Human gold anchors (this investigation)

| File | Human gold | Notes |
|------|------------|-------|
| `tx_2026-09-04_08-22-28` | Go for Doctor Strickland. | |
| `tx_2026-09-04_08-36-13` | Yannett to TT…. | Garble up front; cut off |
| `tx_2026-09-04_09-17-21` | *(empty / static)* | Noise; watermark ASR |
| `tx_2026-09-04_09-31-52` | Coach Richar. | Skip on Coach |
| `tx_2026-09-04_09-32-42` | Coach Richar. | Skip on Coach |
| `tx_2026-09-04_09-57-52` | I'm on it. | |
| `tx_2026-09-04_09-59-46` | Sergeant Marvel. | |
| `tx_2026-09-04_10-24-45` | *(empty / static)* | Noise |
| `tx_2026-09-04_11-44-28` | Yannett to Coach… | Cut off |
| `tx_2026-09-04_12-03-42` | Mr. Harris to Coach L. | Jitter on Mr. Harris; duplicate block + clipping measured |

Sidecar field: `transcription_human_gold` on each JSON.

---

## Checklist for clean school-day capture

1. Restart capture after the pre-roll fix.  
2. Set gain so peaks have headroom (watch live RMS/peak; avoid rail hits).  
3. Spot-check first few TX of the day for onset stutter (should be gone).  
4. Keep human gold notes for dissertation-critical calls (`edupulse note` / `transcription_human_gold`).

---

## One-sentence thesis lines

**A:** *A one-line buffering error that duplicated 64 ms at VAD onset produced perceptual “skips” on the first syllable of radio call signs and systematically poisoned ASR name recognition.*

**B:** *Hard clipping from excess monitor gain is irreversible acoustic damage; without reporting clip rate, radio ASR benchmarks confound gain staging with model accuracy.*
