# EduPulse — Laptop now, Pi later (offline-friendly)

**Audience:** Joseph — school desk capture when the **Windows work PC** is blocked / unanswered by IT.  
**Repo (code only):** https://github.com/ActiveUserSwitch/EduPulse  

## Strategy (two phases)

| Phase | Host | Role |
|-------|------|------|
| **A — Now** | Personal **laptop** (lug) | Live capture at desk + optional local Whisper |
| **B — Later** | **Raspberry Pi** at desk (+ **AI Hat 2** when bought) | Always-on capture; analysis can stay on laptop/home Linux |
| **Always** | Home Linux lab (`GrokBuild/EduPulse`) | Develop, push GitHub, build **USB update packs** |

IT Windows path stays documented (`WINDOWS_QUICKSTART.md`) if Boyes ever replies — you do not depend on it.

**Principle:** Capture does **not** need internet. Upgrades are **sneakernet** (USB), not `git pull` on the desk machine.

---

## Phase A — Laptop until the Pi arrives

### One-time (at home, with internet)

1. Clone or `git pull` this repo on the laptop.
2. Create venv; `pip install -r requirements.txt` (+ whisper extras if you want on-desk STT).
3. Copy live fingerprints locally (never commit):
   - `staff_names.txt` / `common_words.txt` from the `.example.txt` templates.
4. Set captures dir (Linux): `~/edupulse/captures` — or Windows laptop: `%USERPROFILE%\edupulse\captures`.
5. Smoke: `check_audio_environment.py` with UCA222 + radio.

### Daily at school

- Bring laptop + UCA222 + radio audio cable.
- Run capture only (`record_with_transcribe.py` or session tools).
- **No need** for GitHub on school Wi‑Fi if the tree is already installed.
- End of day: copy `captures/` off the laptop to home (USB or overnight sync at home) for offline analysis.

### Pros / cons

| Pros | Cons |
|------|------|
| Works immediately | Lug weight / theft risk / battery |
| Easy to upgrade at home | Desk empty if you forget it |
| Same Python stack as lab | |

---

## Phase B — Pi at desk (may have **no internet**)

Target: Pi stays plugged in; UCA222 stays connected; you visit with a USB stick.

### Recommended split

| On Pi (desk) | On laptop / home Linux |
|--------------|-------------------------|
| Capture + VAD + WAVs + JSON sidecars | Heavy Whisper, validation, dissertation metrics |
| Optional light/base model later with AI Hat 2 | `large-v3` / batch re-transcribe |

You do **not** need the AI Hat for **capture**. Buy order: **Pi + storage + UCA222 working first**, then AI Hat for on-desk STT.

### First bring-up (once, somewhere with internet — home)

1. Flash OS; enable SSH on LAN if you will ever have a cable; otherwise keyboard/monitor or USB Ethernet.
2. Clone EduPulse **once** while online (or copy a full tree from USB — see pack below).
3. `python3 -m venv ~/edupulse-env && pip install -r requirements.txt` (download wheels **while online**).
4. Prefetch any Whisper model you might use later (while online).
5. Point captures at a **USB SSD** if possible (SD cards wear out / fill fast) — see `pi_storage_recommendations.md`.
6. Confirm `check_pi_environment.py` / `check_audio_environment.py` sees UCA222.
7. **Then** move the Pi to the desk. Assume **no** school internet afterward.

Historical Pi notes: `QUICKSTART_ALREADY_RUNNING_PI.md` (update paths; prefer this playbook for offline upgrades).

---

## Offline upgrades (the “pain in the butt” fix)

### What you need on a USB stick

Build the pack **at home** (internet), then walk it to the Pi (or laptop if you froze packages).

```text
EduPulse-update-YYYY-MM-DD/
  README-APPLY.txt          # steps for the desk machine
  edupulse.bundle           # git bundle of main (code only)
  requirements.txt          # pinned copy from that revision
  wheels/                   # optional: pip download for Linux/aarch64
  models/                   # optional: whisper ggml/ctranslate dirs
```

### Build pack (home Linux, in a clone of this repo)

```bash
cd ~/Documents/GrokBuild/EduPulse
./scripts/make_offline_update_pack.sh ~/UsbStick/EduPulse-update-$(date +%F)
```

That script:

1. `git fetch` (if online) and creates a **git bundle** of `main`.
2. Copies `requirements.txt`.
3. Optionally downloads wheels for the **target platform** (set `OFFLINE_PIP_PLATFORM` — see script header).
4. Writes `README-APPLY.txt`.

### Apply on Pi (no internet)

```bash
# Mount USB, then:
cd ~/edupulse   # or wherever the clone lives
git pull /media/pi/USB/EduPulse-update-YYYY-MM-DD/edupulse.bundle main
source ~/edupulse-env/bin/activate
# If wheels/ present:
pip install --no-index --find-links=/media/pi/USB/.../wheels -r requirements.txt
# Else: only code changed; skip pip
```

**Captures and `staff_names.txt` stay on the Pi** — never put live data into the update pack or GitHub.

### Cadence

| How often | What |
|-----------|------|
| Weekly / when you remember | Copy **captures** Pi → USB → home |
| When you change code | Build pack at home → apply on Pi |
| Rarely | Refresh wheels/models (new deps or new Whisper size) |

---

## Data hygiene (same as IT brief)

- GitHub / USB **code packs**: source only.  
- Live WAVs / real fingerprints: **local only** (Pi SSD or laptop `edupulse/captures`).  
- Do not sync captures to consumer cloud if school policy forbids it.

See `docs/IT_SECURITY_REVIEW.md`.

---

## Decision cheat sheet

| Situation | Do this |
|-----------|---------|
| Need capture **this week** | Phase A laptop |
| Tired of lug; Pi purchased | Phase B capture-only first |
| Want on-desk STT | Add AI Hat 2 after capture is stable |
| No internet on Pi | USB update pack only — never rely on `git pull` from GitHub at desk |
| Boyes suddenly approves Windows | Optional third host; keep USB discipline for any locked-down machine |

---

## Open kit list (Phase B)

- [ ] Raspberry Pi (5 preferred if using AI Hat 2)
- [ ] Official power supply + cooling
- [ ] microSD for OS + **USB SSD** for captures
- [ ] Behringer UCA222 (or current interface) + cables
- [ ] Dedicated USB stick labeled **EduPulse-UPDATE** (FAT32/exFAT)
- [ ] AI Hat 2 (later)
- [ ] Home ritual: `make_offline_update_pack.sh` before school week when code changed
