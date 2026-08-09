# EduPulse — IT / security review brief

**Audience:** District IT / security reviewing this GitHub repository before install on a staff work PC.  
**Status:** Principal approval obtained for the research/ops venture (school administrative radio analysis).  
**Repo:** https://github.com/ActiveUserSwitch/EduPulse (code only)

This document describes what the software does, what is **not** in the repository, residual risk, and mitigations. It is not a formal penetration-test report.

---

## 1. What this software is

EduPulse is a **Python research tool** that:

1. Captures **school operations radio** (line-level audio via USB interface such as Behringer UCA222 — not a classroom microphone bug).
2. Writes **local** per-transmission WAV files + JSON metadata on the **Windows work PC** (primary live host).
3. Optionally runs **local** speech-to-text (faster-whisper) and rule-based categorization.
4. Supports **offline** re-transcription, retagging, and validation metrics (Windows or Linux).

Older Raspberry Pi / ALSA notes in the tree are historical only and not required for the school PC deployment.

It is **not** a remote access trojan, keylogger, browser extension, or cloud chatbot that streams audio to a third-party LLM API as part of normal capture.

---

## 2. What IT scanners will typically find

| Expected finding | Interpretation |
|------------------|----------------|
| Python source, PowerShell setup scripts | Normal for research tooling |
| Dependencies: `sounddevice`, `numpy`, `soundfile`, optional `faster-whisper` / torch | Audio I/O + local ML |
| No installer MSI / no Windows service in-repo | User-run scripts only |
| Git history / docs mentioning Pi, radio, VAD | Operational research context |

**What should *not* appear in a clean clone:**

- Raw `.wav` radio audio  
- Live `staff_names.txt` / `common_words.txt` (real fingerprints)  
- Hugging Face / API tokens  
- Real validation CSVs or semantic maps built from live traffic  

A pre-push check (`scripts/check_git_secrets.sh`) blocks common leak paths. `.gitignore` is written to exclude captures, tokens, and PII-bearing local datasets.

---

## 3. Data flow (local vs network)

```
Radio (PX650) → USB audio interface → this PC (sounddevice)
  → local disk: %USERPROFILE%\edupulse\captures\...
  → optional local Whisper model files
  → optional local analysis (no cloud LLM required)

Network (typical):
  - git clone / pull of this *code* repo
  - pip install (PyPI) and one-time model downloads (e.g. Hugging Face)
  - Not used by default to upload radio audio or transcripts
```

**Local by design for sensitive content.** Network is for software/model acquisition and code updates, not for streaming school radio.

---

## 4. Mitigations (current, bare minimum)

| Control | Detail |
|---------|--------|
| **Principal approval** | School leadership aware of ops-radio research use |
| **Code vs data separation** | Git holds source + synthetic demos; live audio/PII stay off-repo |
| **`.gitignore` + secret scan** | Blocks audio, tokens, live fingerprints, private validation sets |
| **No cloud LLM in capture path** | Transcription is local (faster-whisper) when enabled |
| **Fingerprint files local-only** | Real staff lists never intended for Git |
| **Least encryption** | Rely on **district BitLocker** (or existing disk encryption) if already standard; no extra vault required unless IT asks |
| **Windows install path** | Documented setup (`hardware/capture/WINDOWS_QUICKSTART.md`); no SYSTEM service |
| **User-mode only** | Runs under the signed-in user account |

We intentionally **do not** require VeraCrypt or custom crypto unless IT mandates it.

---

## 5. Residual risks (honest)

| Risk | Notes |
|------|--------|
| Live capture on a district PC | USB audio + long-running process; operational radio may include student names |
| Model/package install | Outbound HTTPS to PyPI / model hosts unless offline wheels are used |
| User error | Copying capture folders into OneDrive or emailing CSVs |
| Historical Git history | If old commits ever contained sample PII, history rewrite may be needed separately |

---

## 6. What we ask of IT

1. Review this repository as **open research code** (not malware).  
2. Approve **Python 3.11+**, **Git**, and listed packages if required by policy.  
3. Confirm **BitLocker** (or equivalent) on the assigned work PC if that is district standard.  
4. If policy requires: restricted folder for `%USERPROFILE%\edupulse\` and exclusion from consumer cloud backup.  
5. Tell us if additional controls are required (we will increase encryption / logging only if asked).

---

## 7. Contact / ownership

- **Operational owner:** project author (staff researcher) with principal approval  
- **Data classification:** treat live captures and real transcripts as **sensitive internal**  
- **Code repository:** public or private GitHub as configured — **must not** contain live captures  

---

## 8. Quick verification commands (for IT)

```powershell
# Clone should contain no WAV / tokens
git clone <repo-url> EduPulse-review
cd EduPulse-review
# Expect no matches:
Get-ChildItem -Recurse -Include *.wav,HuggingFaceToken.txt,staff_names.txt | Select-Object FullName
# Secret path check (Git Bash or WSL):
bash scripts/check_git_secrets.sh
```

---

*Keep this file short and accurate. Prefer policy partnership over security theater.*
