# Day 1 with the Behringer UCA222 – Checklist

This is your practical step-by-step guide for the first day you have the UCA222 in hand.

> **Note (laptop continuation):** The wiring guide and all scripts are now in this git repo under `hardware/`. The old "copy from local workspace" steps below are historical from the initial Pi session. When working from a fresh clone on the Pi you can simply `git pull` (or rsync from laptop clone).

**Current Constraints (as of now):**
- Raspberry Pi 4 (8GB)
- Only microSD card storage available (~19 GB free on root)
- Cobra PX650 radio with 2.5mm jack
- 2.5mm → RCA cable already purchased
- Using Option A (radio volume knob + UCA222 gain knobs only)
- All tools are in `~/edupulse/hardware/capture/`

---

## Pre-Arrival (Do This Before the UCA222 Arrives)

- [ ] Make sure all scripts are copied into your project:
  ```bash
  mkdir -p ~/edupulse/hardware/capture
  cp /home/joseph/EduPulse/hardware/capture/* ~/edupulse/hardware/capture/
  ```
- [ ] Create the test recordings folder:
  ```bash
  mkdir -p ~/edupulse/test_recordings
  ```
- [ ] Run the environment checker so you have a baseline:
  ```bash
  python ~/edupulse/hardware/capture/check_pi_environment.py
  ```
- [ ] Review the wiring guide:
  ```bash
  cat ~/edupulse/hardware/wiring/Cobra_PX650_UCA222.md
  ```
- [ ] Make the launcher executable:
  ```bash
  chmod +x ~/edupulse/hardware/capture/edupulse-record
  ```

---

## Day 1 – When the UCA222 Arrives

### 1. Physical Setup

- [ ] Power off the Pi (recommended for first connection).
- [ ] Plug the UCA222 into a USB 3.0 port (blue port) on the Pi 4.
- [ ] Connect the 2.5mm end of your cable into the PX650 accessory jack (the port used for headsets).
- [ ] Connect the two RCA plugs into the **Line Inputs** on the back of the UCA222.
- [ ] Power the Pi back on.

### 2. Verify Hardware Detection

- [ ] Run:
  ```bash
  arecord -l
  lsusb | grep -i behringer
  ```
- [ ] Expected: You should see something like `card X: UCA222 [BEHRINGER UCA222]`
- [ ] Run the full environment checker again:
  ```bash
  python ~/edupulse/hardware/capture/check_pi_environment.py
  ```

### 3. First Level Check (No Recording Yet)

- [ ] Use preview mode to see levels without writing anything:
  ```bash
  python ~/edupulse/hardware/capture/record_session.py --preview
  ```
- [ ] Or use the launcher:
  ```bash
  ~/edupulse/hardware/capture/edupulse-record --preview
  ```
- [ ] Speak into the radio or have someone transmit.
- [ ] Observe which channel (L or R) shows strong audio. With the 2.5mm cable on the PX650, usually only **one channel** will be loud.

### 4. First Real Test Recording

- [ ] Set the PX650 volume knob to ~25–35%.
- [ ] Set both UCA222 input gain knobs to ~50%.
- [ ] Run a short test:
  ```bash
  python ~/edupulse/hardware/capture/test_px650.py --duration 20
  ```
  or
  ```bash
  ~/edupulse/hardware/capture/edupulse-record --duration 30 --label "first-test"
  ```

- [ ] After recording, check:
  - Was there clipping? (Look at the console output)
  - Which channel has the radio audio?
  - Is the signal clean and usable?

- [ ] Adjust the radio volume knob first. Only touch the UCA222 knobs if needed.

### 5. Disk Space Awareness (Critical on SD Card)

- [ ] Check current space:
  ```bash
  df -h ~
  ```
- [ ] Use the cleanup helper regularly:
  ```bash
  python ~/edupulse/hardware/capture/cleanup_recordings.py
  ```

**Rule of thumb while on SD card:**
- Never leave the recorder running unattended.
- Delete test files after every session.

### 6. ALSA Quick Check (Optional but Recommended)

- [ ] Open alsamixer for the UCA222:
  ```bash
  alsamixer -c UCA222
  ```
- [ ] The physical knobs on the UCA222 are usually enough. Capture gain in alsamixer can usually stay low (0–30%).

### 7. Document Your First Session

- [ ] Note down:
  - Final radio volume knob position
  - Final UCA222 gain knob positions
  - Which channel is dominant
  - Any clipping or noise observed
  - Approximate RMS levels you saw in preview

This information will be very useful when you move to longer recordings.

---

## If Something Goes Wrong

| Problem                        | Likely Cause                          | Fix |
|--------------------------------|---------------------------------------|-----|
| UCA222 not detected            | Bad USB port / cable / power          | Try different blue USB port, reboot |
| No audio in either channel     | Cable not fully seated / radio off    | Check 2.5mm connection, power on PX650 |
| Only one channel has audio     | Normal for PX650 + 2.5mm cable        | This is expected. Use the louder channel. |
| Heavy clipping even at low volume | Radio output is hot                   | Lower PX650 volume knob more |
| Very quiet audio               | UCA222 gain too low                   | Increase UCA222 input knobs |
| Crackling / dropouts           | USB power or buffer issues            | Try powered USB hub, or adjust ALSA buffers later |

---

## End of Day 1 Goals

By the end of the first day you should have:

- Confirmed the UCA222 is detected
- Successfully made at least 3–5 short test recordings
- Found reasonable volume/gain settings with no major clipping on normal transmissions
- Understood which channel carries the radio audio
- Not filled up your SD card

---

## Next Steps After Day 1

- Get the two 1TB SSDs mounted and switch the default recording path.
- Consider moving to longer sessions using `record_session.py`.
- Start thinking about the continuous recorder skeleton (`record_continuous.py`).
- Begin proper ALSA configuration if you see buffer/quality issues.

---

**Good luck on Day 1.** Take it slow, keep recordings short, and clean up after every test.

Once you have the UCA222 and have done your first successful capture, let me know how it went and we’ll decide what to tackle next.
