# capture/

Scripts and configurations for continuous or event-driven audio recording from the radio.

## Current Status (May 2025)

- Radio model confirmed: **Cobra PX650**
- Sound card: Behringer UCA222 on order (~4 days)
- **Storage:** Currently only microSD card visible (~19 GB free on root). The two 1TB SSDs are not detected right now.
- **Agreed plan:** Proceed with initial testing on the SD card. We will tackle SSD mounting later.
- Chosen testing approach: Option A (volume knob + UCA222 hardware gains only)

## Available Files

- `check_pi_environment.py` — General environment health check
- `diagnose_storage.sh` — Run this when SSDs are not appearing (very relevant right now)
- `test_px650.py` — Basic first bring-up test (short fixed recordings)
- `record_session.py` — Main tool for the first days with the UCA222 (recommended)
- `pi_storage_recommendations.md` — Storage layout guidance
- `QUICKSTART_ALREADY_RUNNING_PI.md` — Tailored quick start for your current setup (SD card mode)

## Planned Future Scripts

- `record_continuous.py`
- `record_vad.py`
- `arecord_wrapper.sh`
- Proper cleanup / privacy deletion scripts

## Important Notes for This Hardware (Temporary)

We are currently in **SD card only** mode for initial testing. This means:

- Keep all test recordings short (30–60 seconds recommended during bring-up).
- Regularly delete old `.wav` files from `~/edupulse/test_recordings`.
- Once the UCA222 is working reliably, we should prioritize getting the SSDs mounted before doing longer or continuous recordings.

See `QUICKSTART_ALREADY_RUNNING_PI.md` for the current pragmatic testing plan.