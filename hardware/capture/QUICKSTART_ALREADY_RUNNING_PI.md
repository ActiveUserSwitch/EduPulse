# Quick Start — Already Running Pi (Pi 4 8GB)

This guide is for the current situation:

- **Raspberry Pi 4 Model B Rev 1.4**, 8GB RAM
- Repo already cloned at `~/edupulse`
- Virtual environment: `edupulse-env` (already in use)
- Behringer UCA222 arriving in a few days
- Radio: Cobra PX650
- Chosen approach: Option A (volume knob + UCA222 gain only)

**Current Storage Reality:** As of the latest check, the two 1TB SSDs are **not showing up** in `df -h` or `lsblk`. The system is running from the microSD card only (~19 GB free on root).

**Decision:** We will proceed with initial testing on the SD card for now and tackle the SSDs later. This means we must keep test recordings short and clean up frequently.

## 1. First Things to Run Right Now (on the Pi)

```bash
# Make sure you're in the right place
cd ~/edupulse

# Activate your environment (if not already active)
source ~/edupulse-env/bin/activate   # or wherever your env lives

# Run the environment checker (new file)
python hardware/capture/check_pi_environment.py
```

This will show you:
- Current audio devices
- Whether sounddevice / soundfile are installed in your env
- How your two SSDs are currently mounted
- Python version, etc.

Save or screenshot the output.

## 2. Check Your SSD Mounts

Run these and note the output:

```bash
df -h
lsblk -f
mount | grep -E 'ssd|data|mnt'
```

Tell me (or paste) the output so we can decide on the best base path for raw recordings (e.g. `/data/edupulse/raw`, `/mnt/ssd1/edupulse/raw`, etc.).

## 3. When the UCA222 Arrives

```bash
# 1. Plug in the UCA222
# 2. Re-run the checker
python hardware/capture/check_pi_environment.py

# 3. Run the first proper test recording
# Point it at one of your SSDs (example below)
python hardware/capture/test_px650.py \
    --data-dir /data/edupulse/raw \
    --duration 60
```

Adjust `--data-dir` to wherever you want the test recordings to live.

## 4. Recommended Immediate Actions

- [ ] Run the checker script and save the output
- [ ] Confirm your two SSD mount points
- [ ] Decide on a stable base path (we'll lock this in together)
- [ ] Make sure `sounddevice` and `soundfile` are installed in `edupulse-env`:

```bash
pip install sounddevice soundfile numpy scipy
```

- [ ] When the UCA222 arrives, test with the PX650 using the exact instructions in `wiring/Cobra_PX650_UCA222.md`

## 5. Useful One-Liners

Check if the UCA222 is visible after plugging it in:

```bash
arecord -l
lsusb | grep -i behringer
```

Check current git status on the Pi:

```bash
cd ~/edupulse && git status
```

## Temporary SD Card Testing Mode (Current Plan)

Since the SSDs are not currently visible and you want to proceed anyway, here is the pragmatic plan:

- All early testing will write to the SD card (e.g. `~/edupulse/test_recordings`).
- Keep recordings short (15–60 seconds max during initial bring-up).
- Manually delete old test files after each session.
- Once the UCA222 is working and basic capture is stable, we will prioritize getting the SSDs mounted before doing longer recordings.

**Recommended test directory for now:**
```bash
mkdir -p ~/edupulse/test_recordings
```

### Getting the scripts onto the Pi (Important!)

The scripts live in this git repository. On the Pi (after cloning or when the repo is at `~/edupulse`):

```bash
cd ~/edupulse
git pull   # or git fetch && git checkout main
```

Or from your laptop (while in the EduPulse clone):

```bash
rsync -av hardware/capture/ joseph@raspberrypi:~/edupulse/hardware/capture/
```

After the files are present, on the Pi:

```bash
python hardware/capture/record_session.py --data-dir ~/edupulse/test_recordings --duration 30
```

## Questions for You (Lower Priority)

1. Paste the exact output of:
   ```bash
   cat /sys/firmware/devicetree/base/model
   ```

2. When you have time, run and paste:
   ```bash
   bash hardware/capture/diagnose_storage.sh
   sudo fdisk -l
   ```

We can fix the SSD situation whenever you're ready — it doesn't block initial UCA222 + PX650 testing.
