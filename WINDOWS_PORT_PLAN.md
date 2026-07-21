# EduPulse — Windows Port Plan

**Audience:** Another Grok Build (or human) instance with a fresh clone of this repo on **Windows**.  
**Goal:** Run EduPulse capture + offline pipeline on Windows without rewriting the product.  
**Status:** Plan only (not fully implemented). Prefer minimal, reversible changes.

---

## 1. Functional target (what “done” means)

| Capability | Priority | Notes |
|------------|----------|--------|
| Offline: retag, re-transcribe, analyze, validation stats | **P0** | Should work with almost no code change |
| Live capture via UCA222 (or any USB audio) + VAD + WAVs + sidecars | **P0** | sounddevice/WASAPI; device index selection |
| Live light Whisper (tiny/base) during capture | **P1** | CPU or CUDA |
| Offline large-v3 / retro_upgrade | **P1** | Same as Linux |
| pyannote speaker layer | **P2** | Optional; torch + HF token |
| Pi/ALSA docs parity | **P3** | Document only; no ALSA on Windows |
| systemd / bash launchers | **N/A** | Replace with PowerShell |

**Non-goals:** Native WinUI app, MSI installer, rewriting analysis in C#, dropping pathlib, changing WAV/sidecar schema.

---

## 2. Architecture (unchanged)

```
Radio (Cobra PX650) → USB audio (UCA222) → sounddevice capture
  → energy VAD → tx_*.wav (raw, 16 kHz 16-bit) + JSON sidecar
  → optional faster-whisper (live) → categorize + IncidentTracker
  → session_manifest.jsonl

Offline:
  test/test_whisper.py | retro_upgrade_sidecars.py
  retag_session.py → session_manifest.retagged.jsonl
  analyze_manifest.py | validation/* | stats.py
```

**Invariants (do not break):**
- Raw `.wav` is canonical; never overwrite with processed audio.
- Sidecar + manifest schema stays compatible with existing captures under `~/edupulse/captures/` (or Windows equivalent).
- Fingerprint files (`staff_names.txt`, `common_words.txt`) stay **local/gitignored**.
- `edupulse/analysis.py` remains single source of truth for categories / INC linking.

---

## 3. What already works on Windows

- Pure Python modules: `edupulse/analysis.py`, `edupulse/speaker.py`, most of `hardware/capture/*.py` (pathlib, threading, queue, signal.SIGINT).
- Offline scripts: `retag_session.py`, `analyze_manifest.py`, `retro_upgrade_sidecars.py`, `test/test_whisper.py`, `validation/validate_edupulse.py`, `stats.py`.
- Dependencies: `numpy`, `soundfile`, `scipy`, `faster-whisper` (wheels available on Win).
- `sounddevice` uses **WASAPI** on Windows (not ALSA).

---

## 4. Gaps to close (ordered work packages)

### WP0 — Environment bootstrap (0.5–1 h)

1. Install **Python 3.11+** from python.org (check “Add python.exe to PATH”).
2. Clone:
   ```powershell
   git clone https://github.com/ActiveUserSwitch/EduPulse.git
   cd EduPulse
   ```
3. Venv:
   ```powershell
   python -m venv edupulse-env
   .\edupulse-env\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
4. Optional GPU: install CUDA-enabled `torch` matching local CUDA, then `faster-whisper`.
5. Create data root:
   ```powershell
   mkdir $env:USERPROFILE\edupulse\captures -Force
   ```
6. Copy fingerprint templates → live files (gitignored):
   ```powershell
   copy hardware\capture\staff_names.example.txt hardware\capture\staff_names.txt
   copy hardware\capture\common_words.example.txt hardware\capture\common_words.txt
   # edit with real staff / channel language — never commit
   ```

**Acceptance:** `python -c "import sounddevice, soundfile, numpy; print('ok')"` and `python -c "from edupulse.analysis import categorize_transmission; print(categorize_transmission('need nurse in hallway'))"`.

---

### WP1 — Device discovery (1–2 h)

**Problem:** Docs/scripts mention `arecord -l`; that is ALSA-only.

**Do:**
1. Prefer existing `sounddevice.query_devices()` path in `check_pi_environment.py` / capture scripts.
2. Add Windows-friendly listing (new or extend `check_pi_environment.py`):
   - Rename conceptually to “environment check” or add `check_audio_environment.py`.
   - On Windows: skip `arecord`/`aplay`; always print `sd.query_devices()` with indices, host API, max input channels.
3. Ensure capture CLIs accept **`--device INDEX`** (verify `record_session.py` / `record_with_transcribe.py` / `record_continuous.py`; add if missing).
4. Document: Windows Sound → Input → set UCA222 as default **or** pass `--device`.

**Acceptance:** User can list devices and run a 15–30 s preview capture that creates `tx_*.wav` under `%USERPROFILE%\edupulse\captures\...`.

---

### WP2 — Capture path hardening (2–4 h)

Audit and fix only if broken on Windows:

| Area | Risk | Fix approach |
|------|------|----------------|
| Default `--data-dir` | `Path.home() / "edupulse" / "captures"` | Already OK on Windows |
| `signal.signal(SIGINT)` | Fine | Keep; document Ctrl+C in PowerShell |
| `shutil.disk_usage` | Fine | Keep |
| Binary modes for WAV | Usually fine via soundfile | Verify |
| Shell launcher `edupulse-record` | Bash | Add `edupulse-record.ps1` with same flags |
| Long paths / spaces | Medium | Always quote paths in docs; use `pathlib` only |
| Console UTF-8 | Medium | `chcp 65001` or set `PYTHONIOENCODING=utf-8` if emoji/logs break |
| Exclusive WASAPI / shared mode | Medium | Document “close exclusive apps”; try default shared mode first |

**Optional code:** small `edupulse/platform_util.py`:

```python
def is_windows() -> bool: ...
def default_captures_dir() -> Path: ...
def list_input_devices() -> list[dict]: ...
```

Use only where it removes `# if linux` sprawl.

**Acceptance:** Full `record_with_transcribe.py` session with `--max-duration 120`, real or loopback input, produces manifest + sidecars; Ctrl+C flushes cleanly.

---

### WP3 — Offline pipeline verification (1–2 h)

On Windows, with a **copy** of an existing session (WAVs + sidecars) or a short capture:

```powershell
python hardware\capture\retag_session.py `
  $env:USERPROFILE\edupulse\captures\<session>\session_manifest.jsonl `
  --known-staff-file hardware\capture\staff_names.txt `
  --common-words-file hardware\capture\common_words.txt

python hardware\capture\analyze_manifest.py `
  $env:USERPROFILE\edupulse\captures\<session>\session_manifest.retagged.jsonl

python test\test_whisper.py `
  --file $env:USERPROFILE\edupulse\captures\<session>\tx_....wav `
  --model tiny `
  --known-staff-file hardware\capture\staff_names.txt `
  --common-words-file hardware\capture\common_words.txt
```

**Acceptance:** retagged manifest written; whisper produces text; no Linux-only path errors.

---

### WP4 — Docs & launcher (1 h)

1. Add short section to root `README.md` linking this plan.
2. Add `hardware/capture/WINDOWS_QUICKSTART.md` (or keep everything here and link once).
3. PowerShell launcher `hardware/capture/edupulse-record.ps1`:
   - activate venv if present
   - call `record_with_transcribe.py` with defaults pointing at `$env:USERPROFILE\edupulse\captures`

**Do not** delete Pi/ALSA docs; label them “Linux/Pi”.

---

### WP5 — Optional polish

- CUDA install notes for large-v3 overnight batch on a gaming/workstation laptop.
- Windows Task Scheduler equivalent of “run after school” batch reprocess (not required for MVP).
- WSL2 alternative path: “if USB passthrough is painful, capture on bare metal Windows; analyze in WSL” — document as fallback only.

---

## 5. Explicit non-changes

- Do **not** commit `staff_names.txt` / `common_words.txt` / `*.wav` / HF tokens.
- Do **not** change category IDs or INC format without a migration note.
- Do **not** make two-phase tiny/live + overnight large the default unless the user asks (prior laptop preference was stay on large when hardware allows).
- Do **not** port StockExplorer / ClipFinder as part of this plan.

---

## 6. Suggested implementation order for the other agent

1. WP0 bootstrap → prove imports.  
2. WP3 offline on copied session → prove analysis path.  
3. WP1 device list + short capture.  
4. WP2 fix only bugs found.  
5. WP4 docs + `.ps1`.  
6. Smoke: 10-minute live radio session if hardware available.

Commit style: small commits per WP (`fix(windows): ...`, `docs(windows): ...`).

---

## 7. Smoke-test checklist (agent must run)

- [ ] `python -c "import sounddevice as sd; print(sd.query_devices())"`
- [ ] Preview/capture ≥ 30 s → ≥1 `tx_*.wav` + `.json` + manifest line  
- [ ] `retag_session.py` on that session  
- [ ] `analyze_manifest.py` on retagged  
- [ ] `test_whisper.py --model tiny` on one wav  
- [ ] Paths with spaces in username still work  
- [ ] Ctrl+C during capture leaves consistent session_summary / flushed queue  

---

## 8. Hardware notes (Windows)

- Same chain: **PX650 headphone/line out → UCA222 line in → USB → PC**.  
- Install UCA222 drivers only if Windows does not auto-enumerate (often class-compliant).  
- Disable exclusive mode on the device if capture fails to open (Sound → device → Properties → Advanced).  
- Gain still set so quiet gaps are roughly in the range the VAD docs describe (see `record_with_transcribe.py` docstring).  

---

## 9. Repo / paths reference

| Item | Location |
|------|----------|
| Repo | https://github.com/ActiveUserSwitch/EduPulse |
| Package / analysis | `edupulse/` |
| Capture | `hardware/capture/record_with_transcribe.py` |
| Fingerprint examples | `hardware/capture/*.example.txt` |
| Live data (local) | `%USERPROFILE%\edupulse\captures\` (or `--data-dir`) |
| Requirements | `requirements.txt` |

---

## 10. Success criteria

Windows port is **complete enough** when:

1. A Windows machine can capture a session with the same artifact layout as Linux.  
2. Offline retag + whisper reprocess work on that session.  
3. Another Grok instance can follow this document without tribal Linux knowledge.  
4. No secrets or raw radio audio are committed.

---

*Last updated for handoff with repo sync (Windows plan). Prefer executing WP0–WP3 before any large refactors.*
