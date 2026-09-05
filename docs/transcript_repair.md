# Second-pass transcript repair (full lexicon)

**Why:** Whisper’s fingerprint is capped at ~223 tokens
([`whisper_prompt_budget.md`](whisper_prompt_budget.md)). Lexical expand cannot
fix unconstrained misses, e.g. `Codes for Shar.` → **Coach Richard**
(`tx_2026-09-04_09-32-42`).

**What:** Offline repair with the **full** staff / radio / places lexicon.

## Billing — read this

| Backend | What it uses | Money |
|---------|----------------|------|
| **`ollama` (default)** | Local Ollama (`llama3.1`, etc.) | **$0 API** — your machine |
| **`queue`** | Writes `~/edupulse/repair_queue.jsonl` for **Grok Build / grokbot** | Uses the SuperGrok / Build subscription you already pay for — **not** `api.x.ai` |
| **`xai`** | SpaceXAI developer API (`XAI_API_KEY` → `api.x.ai`) | **Metered per token** — opt-in only |

SuperGrok / Grok Build ≠ developer API credits. We do **not** default to `api.x.ai`.

```text
Whisper (≤223) → transcription
                      ↓
         ollama (default)  or  queue → Grok Build
                      ↓
         transcription_repair + optional --apply
```

## Setup (default: Ollama)

```bash
# Ollama already running with a chat model, e.g. llama3.1:latest
export EDUPULSE_REPAIR_BACKEND=ollama   # default
export EDUPULSE_OLLAMA_MODEL=llama3.1:latest
```

Optional queue for Grok Build sessions:

```bash
edupulse repair-tx --day 2026-09-04_school-day --backend queue --only-low-conf
# then in Grok Build: process ~/edupulse/repair_queue.jsonl
```

## CLI

```bash
# Local free repair of the known miss
edupulse repair-tx \
  --wav ~/edupulse/captures/2026-09-04_school-day/tx_2026-09-04_09-32-42_3.2s.wav \
  --backend ollama --apply

# After school, low-conf only
edupulse repair-tx --day 2026-09-04_school-day --only-low-conf --apply
```

## Sidecar fields

| Field | Meaning |
|-------|---------|
| `transcription` | Best display string (updated if `--apply`) |
| `transcription_whisper` | Snapshot of pre-repair text |
| `transcription_repair` | `{original, corrected, changed, backend, model, …}` |

Ensure **Coach Richard** is on `staff_names.txt` / `radio_staff.txt` (already added).
