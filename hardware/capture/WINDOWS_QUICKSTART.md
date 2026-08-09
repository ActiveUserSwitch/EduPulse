# EduPulse on Windows — Quick Start

Run capture + offline analysis on a **Windows work PC** with the same artifacts as Linux/Pi.

Full design notes: [`WINDOWS_PORT_PLAN.md`](../../WINDOWS_PORT_PLAN.md) (repo root).

---

## 1. One-time setup

```powershell
# Python 3.11+ from python.org (Add to PATH)
git clone https://github.com/ActiveUserSwitch/EduPulse.git
cd EduPulse

python -m venv edupulse-env
.\edupulse-env\Scripts\Activate.ps1
pip install -r requirements.txt

# Data root
mkdir $env:USERPROFILE\edupulse\captures -Force

# Live fingerprints (never commit)
copy hardware\capture\staff_names.example.txt hardware\capture\staff_names.txt
copy hardware\capture\common_words.example.txt hardware\capture\common_words.txt
# Edit staff_names.txt / common_words.txt with real names and radio language
```

Or run:

```powershell
.\hardware\capture\Setup-EduPulseWindows.ps1
```

**Smoke:**

```powershell
python -c "import sounddevice, soundfile, numpy; print('ok')"
python -c "from edupulse.analysis import categorize_transmission; print(categorize_transmission('need nurse in hallway'))"
python hardware\capture\check_audio_environment.py
```

---

## 2. List audio devices (UCA222 / USB)

```powershell
python hardware\capture\check_audio_environment.py --list-devices
# or
python hardware\capture\record_with_transcribe.py --list-devices
```

Note the **index** of the Behringer UCA222 (or your input).  
If open fails: Sound → device → Properties → **Advanced** → uncheck exclusive mode.

Hardware chain (same as Pi): **PX650 out → UCA222 line in → USB → PC**.

---

## 3. Live capture

```powershell
.\edupulse-env\Scripts\Activate.ps1
cd <path-to-EduPulse>

python hardware\capture\record_with_transcribe.py `
  --data-dir $env:USERPROFILE\edupulse\captures `
  --session "work-pc-test" `
  --device <INDEX> `
  --model tiny `
  --known-staff-file hardware\capture\staff_names.txt `
  --common-words-file hardware\capture\common_words.txt
```

Or the PowerShell wrapper:

```powershell
.\hardware\capture\edupulse-record.ps1 -Device <INDEX> -Session "work-pc-test"
```

Stop with **Ctrl+C** (flushes queue / manifest).

Artifacts land under:

`%USERPROFILE%\edupulse\captures\YYYY-MM-DD_work-pc-test\`

- `tx_*.wav` + `tx_*.json`
- `session_manifest.jsonl`

---

## 4. Offline pipeline

```powershell
$sess = "$env:USERPROFILE\edupulse\captures\<session-folder>"

python hardware\capture\retag_session.py `
  $sess\session_manifest.jsonl `
  --known-staff-file hardware\capture\staff_names.txt `
  --common-words-file hardware\capture\common_words.txt

python hardware\capture\analyze_manifest.py `
  $sess\session_manifest.retagged.jsonl

python test\test_whisper.py `
  --file $sess\tx_....wav `
  --model tiny `
  --known-staff-file hardware\capture\staff_names.txt `
  --common-words-file hardware\capture\common_words.txt
```

Copy an existing Linux session folder to Windows to work offline without the radio.

---

## 5. Paths that just work

| Role | Path |
|------|------|
| Captures | `%USERPROFILE%\edupulse\captures\` |
| Fingerprints | `hardware\capture\staff_names.txt` (local only) |
| HF token (optional pyannote) | `$env:HF_TOKEN` or `%USERPROFILE%\HuggingFaceToken.txt` |

Defaults use `Path.home() / "edupulse" / ...` — no Linux-only `/home/...` required.

---

## 6. Do not

- Commit `staff_names.txt`, `common_words.txt`, tokens, or `.wav` files.
- Expect ALSA/`arecord` (use sounddevice / WASAPI).
- Expect `systemd` or bash launchers (use PowerShell).

---

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| No input devices | Plug UCA222; reopen PowerShell; check Sound settings |
| `Error opening InputStream` | Disable exclusive mode; close Zoom/Teams exclusive use |
| `edupulse` import fails | Run from repo root; or `pip install -e .` if you add packaging later |
| Unicode/console errors | `chcp 65001` or `$env:PYTHONIOENCODING="utf-8"` |
| Paths with spaces | Keep using `pathlib` / quoted PowerShell paths |

---

*Pair with Pi docs under `hardware/capture/*` labeled Linux/Pi; this file is Windows-only ops.*
