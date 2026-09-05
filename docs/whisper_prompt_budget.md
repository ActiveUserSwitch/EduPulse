# Whisper `initial_prompt` budget — model contract & EduPulse practice

**Status:** living methods note (dissertation / book trail)  
**Case study:** 2026-09-01 gold miss — live `Deannette to Mr. Mase.` vs truth `Yannett to Mr. Mayes`  
**Code:** `edupulse/whisper_prompt_budget.py`, `edupulse/categories.py` (`build_enhanced_initial_prompt`), `edupulse/name_codebook.py`  
**See also:** [`name_codebook.md`](name_codebook.md) — phonetic short codes under the same budget;  
[`transcript_repair.md`](transcript_repair.md) — LLM second pass with the **full** lexicon (beyond 223)

---

## 1. The question

> Can we raise the token amount Whisper can ingest for the audio fingerprint?

**Short answer:**

| Layer | Limit | Can we raise it? |
|-------|------:|------------------|
| Model architecture (`n_text_ctx`) | **448** decoder positions | **No** — baked into Whisper weights / positional embeddings |
| Stock OpenAI / faster-whisper *policy* | **~223** of those for the prompt | **Yes, by forking/patching** — you trade away output slots |
| What we were feeding (2026-09) | **~506** tokens | Silently truncated; front half discarded |

You cannot feed an arbitrarily large staff roster and expect the model to “see” all of it. Overflow is not an error; it is **silent left-truncation**. That is an empirical methods hazard for any domain-adapted ASR pipeline.

---

## 2. Where the numbers come from

Whisper’s text decoder has a fixed context:

```text
n_text_ctx = 448
```

OpenAI’s reference decoder (and faster-whisper / CTranslate2) **reserve roughly half** of that context for *conditioning text* (previous window and/or `initial_prompt`), and half for *newly generated* transcript tokens:

```text
prompt budget ≈ n_text_ctx // 2 - 1  =  223
output budget ≈ n_text_ctx // 2      =  224
```

In `faster_whisper.transcribe.WhisperModel.get_prompt` (installed copy):

```python
# previous_tokens includes the encoded initial_prompt
prompt.extend(previous_tokens[-(self.max_length // 2 - 1) :])
# self.max_length is hard-coded to 448
```

So:

- Tokens **beyond the last 223** of `initial_prompt` are **dropped from the front**.
- The architectural ceiling for *prompt + new tokens + special tokens* remains **448**. You cannot “turn up” 448 without a different model.

Authoritative discussion: OpenAI Whisper discussions on `initial_prompt` length; OpenAI cookbook *Whisper prompting guide* (“only the final 224 tokens of the prompt will be considered”).

---

## 3. Case study — why the gold standard failed

### Observed (live, large-v3, same day)

| Clip | Live transcript | Truth (human) |
|------|-----------------|---------------|
| `tx_…_08-39-24` | `Deannette to Mr. Mase.` | `Yanette/Yannett to Mr. Mayes` |
| next PTT | `Good afternoon, Mr. Mason.` | Mayes answering (user recalled “Go for Mr. Mayes”) |

Neither name resolved → **no `radio_caller` / `radio_callee` → zero voice enrollments** on a two-ID gold pair.

### Ablation (idle machine, same WAVs, large-v3 cpu/int8)

| Condition | 08-39-24 result |
|-----------|-----------------|
| Offline, **identical live fingerprint** | Same error (`Deannette…Mase`) |
| Offline, **no prompt** | Still wrong |
| Offline, **focused names + phrases** | `Yannette to Mr. Mayes.` |
| Offline, **repaired fingerprint** (hot tail) | `Yannett to Mr. Mayes.` (conf ↑) |

**Conclusion for methods:** the miss was **not** “async transcription changes ASR.” Same model + same audio + same prompt reproduced the error. The failure mode was **prompt content vs budget**.

### Root mechanisms stacked

1. **Application bug:** `build_enhanced_initial_prompt` kept only `sorted(staff)[:25]` full `Title First Last` lines. Alphabetically, **Mayes in / Yannett out** → decoder invented `Deannette` / `Annette`.
2. **Model contract:** even after listing all last names, the built prompt was **~506 tokens**; Whisper kept **~224 from the tail**. Early-alphabet names in the roster were still dropped.
3. **Downstream cascade:** bad orthography → staff resolver miss → no protocol enrollments.

This is the story we tell in the dissertation: *domain adaptation via prompting is capacity-constrained; silent truncation looks like “the model is bad at names” when the names never entered the conditioning window.*

---

## 4. Can forking / trading output slots help?

### What a fork actually changes

Patching `get_prompt` to keep e.g. **350–400** prompt tokens instead of **223** does **not** enlarge the model. It **reallocates** the 448-slot window:

```text
Stock:     [ ~223 prompt | ~224 new tokens ]
Trade:     [ ~380 prompt |  ~60 new tokens ]   # example for short PTT
Impossible:[ 600 prompt  |  ... ]              # exceeds n_text_ctx
```

### Why radio PTT is a plausible trade

School administrative push-to-talk clips are typically **2–6 seconds** and decode to **≪ 60 tokens** of text (`Yannett to Mr. Mayes.` is on the order of 10 BPE pieces). Burning 224 slots on *output* leaves headroom unused. Reallocating unused output budget into the fingerprint is therefore a **use-case-specific** experiment, not a general Whisper improvement.

### Risks (document these)

- Longer utterances (assemblies, PA spill) may **hit the reduced output cap** and truncate mid-sentence.
- Patching site-packages or monkey-patching is **non-portable** across faster-whisper versions.
- Hotwords / `prefix` paths in faster-whisper use the **same** `max_length // 2` knife.
- Positional embeddings were trained with the stock recipe; extreme reallocations are off-policy.

### Recommended experimental stance

Treat “expanded prompt budget” as an **A/B factor** on a frozen gold set (including 2026-09-01 Yannett/Mayes), not as production default until:

1. Output-truncation rate on full school days is measured, and  
2. Name-F1 / enrollment yield improves without regressing other categories.

Utilities: `edupulse.whisper_prompt_budget` (`measure_prompt`, `fit_prompt_to_budget`, `apply_prompt_budget_patch`).

### First A/B (2026-09-01 gold, idle large-v3)

Report: `~/edupulse/reports/prompt_budget_trade_ab.json`

| Prompt | Tokens built | Still truncated at budget=400? |
|--------|-------------:|:-------------------------------|
| Production fingerprint (hot tail) | ~505 | Yes (~105 dropped) |
| Full Title+Last roster + phrases | ~547 | Yes (~147 dropped) |

On the gold call (`08-39-24`), **every** repaired condition (stock 223 + hot tail, fit-to-223, full Title+Last, trade-380) produced `Yannett to Mr. Mayes.` — so **trading slots was not necessary** once the hot phrases sat in the kept tail.

On the reply (`08-39-28`), stock + full Title+Last (still truncated to 223 of the *end*) uniquely yielded **`Go for Mr. Mayes.`** (matches human recall); trade-380 yielded `Good afternoon, Mr. Mayes.` Prompt composition / which 223 tokens survive mattered more than raw budget on this clip.

**Methods takeaway:** raising the software prompt slice is *possible* and worth studying for long rosters, but it is not a substitute for **budget-aware prompt design**. The hard ceiling remains 448.

---

## 5. What we do in production (default)

`build_enhanced_initial_prompt` **compresses to ≤223 tokens by construction**:

1. Short base + capped channel terms.
2. Pack as many **space-separated last names** as the remaining budget allows (hot lasts first).
3. **Title+Last call signs + protocol phrases at the end**.
4. Final `fit_prompt_to_budget` safety pass with the Whisper tokenizer.
5. **ASR aliases** (`mase`→Mayes, `deannette`→Yannett) so resolver/enrollment survive residual ASR slips.

We do **not** ship a 500-token roster and hope the tail is lucky. Compare tool: `edupulse compare-tx`.

---

## 6. Process checklist (reproduce / cite)

1. Freeze WAVs + live sidecar JSON for the incident day.  
2. Confirm EduPulse capture is **idle** (no contended CPU/GPU story).  
3. Re-TX with: (a) stored live prompt, (b) no prompt, (c) budget-fit prompt, (d) optional expanded-budget patch.  
4. Report exact strings + mean `exp(avg_logprob)`.  
5. Run `parse_radio_call` on each string; record whether **two IDs** would enroll.  
6. File results under `~/edupulse/reports/live_vs_offline_*.json`.

---

## 7. One-sentence thesis line

> Whisper’s fingerprint is not an unbounded glossary: it is a **~223-token conditioning window** inside a **448-token decoder**; feeding more than the window holds does not enrich the model—it **silently deletes the beginning of your domain knowledge**, which is how a complete staff list still produced “Deannette” instead of “Yannett.”

---

## References (pointers)

- OpenAI Whisper model dims: `n_text_ctx = 448`
- faster-whisper `WhisperModel.max_length = 448`; `get_prompt` uses `max_length // 2 - 1`
- OpenAI Cookbook: Whisper prompting guide (final ~224 tokens of prompt)
- EduPulse gold artifacts: `~/edupulse/captures/2026-09-01_school-day/tx_2026-09-01_08-39-24_*.wav` and report `~/edupulse/reports/live_vs_offline_gold_v2.json`
- Trade A/B report: `~/edupulse/reports/prompt_budget_trade_ab.json`
