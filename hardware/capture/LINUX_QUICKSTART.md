# EduPulse on Linux — Quick Start

Run **live capture and offline analysis** on Linux (this lab: Joseph’s desktop).
Same WAV / sidecar / `session_manifest.jsonl` artifacts as Windows.

Windows school PC: [`WINDOWS_QUICKSTART.md`](WINDOWS_QUICKSTART.md).  
Pi / `~/.asoundrc` checklists: **historical only** (files named `*pi*` / `alsa_config.md`).

**IT / privacy:** [`docs/IT_SECURITY_REVIEW.md`](../../docs/IT_SECURITY_REVIEW.md) — live radio and fingerprints stay local, not in git.

---

## Paths on this machine

| Role | Path |
|------|------|
| Repo | `~/Documents/GrokBuild/EduPulse` |
| Shortcut | `~/edupulse-code` → that repo |
| Python env | `~/edupulse-env` |
| Live captures | `~/edupulse/captures/<date>_<label>/` |
| Fingerprints | `hardware/capture/staff_names.txt` and `common_words.txt` (gitignored) |

Always `cd` to the **repo root** (`EduPulse/`) before `python hardware/capture/...`.

---

## 1. One-time setup (if the env is missing)

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev portaudio19-dev libsndfile1

python3 -m venv ~/edupulse-env
source ~/edupulse-env/bin/activate
cd ~/Documents/GrokBuild/EduPulse
pip install -r requirements.txt

mkdir -p ~/edupulse/captures

# Live fingerprints (never commit)
cp -n hardware/capture/staff_names.example.txt hardware/capture/staff_names.txt
cp -n hardware/capture/common_words.example.txt hardware/capture/common_words.txt
# Edit staff_names.txt / common_words.txt with real names and radio language
```

**Smoke:**

```bash
source ~/edupulse-env/bin/activate
cd ~/Documents/GrokBuild/EduPulse
python -c "import sounddevice, soundfile, numpy; print('ok')"
python -c "from edupulse.analysis import categorize_transmission; print(categorize_transmission('need nurse in hallway'))"
python hardware/capture/check_audio_environment.py
```

---

## 2. List audio devices (UCA222 / USB)

Hardware: **PX650 accessory jack → 2.5mm-to-RCA → UCA222 LINE IN → USB → Linux box.**

```bash
source ~/edupulse-env/bin/activate
cd ~/Documents/GrokBuild/EduPulse
python hardware/capture/check_audio_environment.py --list-devices
# or
python hardware/capture/record_with_transcribe.py --list-devices
```

Note the **integer index** of the Behringer UCA222 (or Pulse “Monitor of …” if you must). Prefer the hardware device, not a loopback.

If Pulse grabs the UCA222 exclusively, unplug/replug USB or:

```bash
pactl list short sources
# then pass the sounddevice index from --list-devices
```

---

## 3. Live capture (full session)

**Easiest (after one-time setup):** put `~/bin` on your PATH (usually already is), then:

```bash
edupulse              # capture + large-v3 Whisper → ~/edupulse/captures/YYYY-MM-DD_school-day/
edupulse devices      # list inputs
edupulse preview      # levels only
edupulse note "Fire drill ~09:15" --tag fire_drill   # human day context
edupulse context      # show DAY_CONTEXT.md for latest day
edupulse --model small     # if live lag is too high on this machine
edupulse --no-transcribe   # WAV only if you want
# Ctrl+C to stop
```

Launcher: `scripts/edupulse` (symlinked to `~/bin/edupulse`). Auto-picks UCA222 when possible; defaults **live `large-v3`** (English). WAVs are saved immediately; the `>>> Speaker: text` line may lag behind the radio.

**Speaker ID (continual):** on each tx, radio protocol enrolls voices into `~/edupulse/speaker_db.pkl`:
- `Name1 to Name2` → enroll **Name1** (caller is speaking)
- `Go for Name2` → enroll **Name2** (self-ID / answer)
- then match the WAV embedding → prefer voice label on the print line  

Needs pyannote embedding + HF token (already used for speaker features). The 4pm AC timer still catches transcript backlog.

Full manual command:

```bash
source ~/edupulse-env/bin/activate
cd ~/Documents/GrokBuild/EduPulse

python hardware/capture/record_with_transcribe.py \
  --data-dir ~/edupulse/captures \
  --session "linux-test" \
  --device <INDEX> \
  --model tiny \
  --known-staff-file hardware/capture/staff_names.txt \
  --common-words-file hardware/capture/common_words.txt
```

Useful flags:

```bash
# 10-minute hardware test
... --max-duration 600

# Watch levels, no files
python hardware/capture/edupulse-record --preview --device <INDEX>

# Short labeled WAV (no Whisper)
python hardware/capture/edupulse-record --duration 60 --label "bring-up" --device <INDEX>

# Categories
python hardware/capture/record_with_transcribe.py --list-categories
```

All-day: `tmux new -s edupulse` then the `record_with_transcribe.py` command inside. Stop with **Ctrl+C** (flushes queue / manifest).

Artifacts:

`~/edupulse/captures/YYYY-MM-DD_linux-test/`

- `tx_*.wav` + `tx_*.json`
- `session_manifest.jsonl`

Quiet-floor target on the live line: gaps around **-45 to -55 dB**. PX650 volume first, then UCA222 knobs.

---

## 4. Offline (this is the usual Linux work)

Collection for the school year is done; Linux is where retag / Whisper / stats run.

```bash
source ~/edupulse-env/bin/activate
cd ~/Documents/GrokBuild/EduPulse

SESS=~/edupulse/captures/<session-folder>

python hardware/capture/retag_session.py \
  "$SESS/session_manifest.jsonl" \
  --known-staff-file hardware/capture/staff_names.txt \
  --common-words-file hardware/capture/common_words.txt

python hardware/capture/analyze_manifest.py \
  "$SESS/session_manifest.retagged.jsonl"

python test/test_whisper.py \
  --file "$SESS"/tx_....wav \
  --model base \
  --known-staff-file hardware/capture/staff_names.txt \
  --common-words-file hardware/capture/common_words.txt
```

Always analyze the **`.retagged.jsonl`** after retag.

Heavy upgrade of a day (large-v3 + optional pyannote):

```bash
PYTHONPATH=. python hardware/capture/retro_upgrade_sidecars.py \
  --base-dir ~/edupulse/captures \
  --day 2026-06-05_last-day-2
```

Do **not** batch-upgrade `2026-06-03_finals-day3` or `2026-06-04_last-day-1` (stopped on purpose).

---

## 5. Do not

- Commit `staff_names.txt`, `common_words.txt`, tokens, or `.wav` files.
- Confuse this path with Raspberry Pi systemd / `arecord`-only docs.
- Run capture scripts from `~/Documents/GrokBuild` (parent of the repo). Cwd is `EduPulse/`.

---

## 6. Troubleshooting

| Symptom | Fix |
|---------|-----|
| No UCA222 in `--list-devices` | `lsusb`; try another USB port; `sudo dmesg \| tail` |
| Device busy / PortAudio error | Close Zoom/Chrome tab using the mic; unplug UCA222; pick a different index |
| Only one channel has audio | Normal for this radio cable; leave stereo capture |
| `edupulse` import fails | `cd ~/Documents/GrokBuild/EduPulse` then `source ~/edupulse-env/bin/activate` |
| Pulse vs ALSA names | Use the **index** from `record_with_transcribe.py --list-devices`, not `hw:1,0` strings |
| Whisper lag too high on CPU | Live default is `large-v3` (print lags; WAVs OK). Try `--model small` or `--model base`. |

---

*Linux lab + Windows work PC are both supported. Pi/ALSA files under this folder are optional history.*
