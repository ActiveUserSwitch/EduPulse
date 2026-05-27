# Raspberry Pi Storage Layout Recommendations (2x 1TB SSDs)

This document describes a practical storage layout for the EduPulse edge device when using two 1TB SSDs, as is the case on the current development Pi.

## Current Hardware Context (as of latest check)

- Raspberry Pi 4 Model B Rev 1.4, 8GB RAM
- Currently only the microSD card is visible (`/dev/mmcblk0`)
- User previously mentioned two 1TB SSDs, but they are **not currently showing up** in `df -h` or `lsblk -f`
- Goal: Long-duration radio monitoring with privacy constraints (raw audio must be deleted after processing)

**Current Situation (Agreed):** The two 1TB SSDs are not detected. User has decided to proceed with initial UCA222 + PX650 testing on the SD card for now and address storage later.

**Interim Rules for SD Card Testing:**
- Maximum recording length during early testing: 60 seconds
- Clean up test files after every session
- Do not leave the capture system running unattended until SSDs are available
- Use `~/edupulse/test_recordings` (or similar) as the working directory for now

## Recommended Mount Points

It is strongly recommended to mount the SSDs at stable locations such as:

```
/data/audio          # For raw recordings (high I/O, will be deleted frequently)
/data/processed      # For features, metadata, logs, database
```

Or a cleaner split:

```
/mnt/ssd1/edupulse/raw
/mnt/ssd2/edupulse/processed
```

Whatever mount points are currently in use, create a consistent project structure underneath them.

## Suggested Directory Structure on the Pi

```
/
└── data/                          # or /mnt/ssd1, /mnt/ssd2, etc.
    └── edupulse/
        ├── raw/                   # Temporary raw .wav files (delete after feature extraction)
        │   └── 2025-05/
        │       └── 2025-05-28/
        │           └── *.wav
        ├── features/              # Privacy-safe aggregated features (can keep long-term)
        │   └── 2025-05/
        ├── logs/
        │   └── capture/
        │   └── processing/
        ├── metadata/              # Weather, calendar, school schedule, etc.
        └── config/
            └── local.yaml
```

## Why Separate Raw vs Processed?

- Raw audio is the highest risk and highest volume data.
- Per the project privacy design, raw files + full transcripts should be deleted after feature extraction.
- Keeping raw audio on a separate mount or sub-volume makes cleanup scripts safer and easier.

## Suggested Mount Strategy

Option 1 (Simple):
- SSD 1 mounted at `/data` → used primarily for raw audio
- SSD 2 mounted at `/data2` → used for features, logs, database

Option 2 (More robust):
- Both SSDs in RAID-0 or JBOD for capacity
- Or one SSD for data, second SSD for redundancy / rsync target

## Environment Variables / Config

It is recommended to define base paths in a config file or environment variables rather than hardcoding paths in scripts.

Example in `~/.edupulse.env` (never committed):

```bash
EDUPULSE_BASE=/data/edupulse
EDUPULSE_RAW=$EDUPULSE_BASE/raw
EDUPULSE_FEATURES=$EDUPULSE_BASE/features
EDUPULSE_LOGS=$EDUPULSE_BASE/logs
```

All capture and processing scripts should respect these variables.

## Next Actions

- [ ] Confirm current mount points and filesystem on the two SSDs (`df -h`, `lsblk -f`, `mount`)
- [ ] Decide on final base path (e.g. `/data/edupulse`)
- [ ] Create the directory structure
- [ ] Update `test_px650.py` and future scripts to write raw audio under the chosen `raw/` path
- [ ] Add a simple cleanup script (later) that deletes raw files older than N hours after they have been processed

## Current Status

This document was created in response to the user confirming the Pi already has two 1TB SSDs configured for data.
