# hardware/capture/

Scripts for capturing and post-processing school radio traffic.

**This is the active directory for the capture + offline iteration tools.**

**Live capture primary target:** **Windows work PC** (see `WINDOWS_QUICKSTART.md`).  
**Offline tools** run on Windows or Linux.  
**Raspberry Pi / ALSA** material below is **optional / historical** only.

See the root `README.md` and `ROADMAP.md` for overall status.

## Primary Tools (use these)

- `record_with_transcribe.py` — Full-day / session capture (WAV + sidecar +
  `session_manifest.jsonl`). Prefer `--list-devices` then `--device N`.
- `edupulse-record.ps1` / `Setup-EduPulseWindows.ps1` — Windows launch + bootstrap.
- `check_audio_environment.py` — Cross-platform device/package check (prefer this).
- `retag_session.py` — Re-apply rules + fingerprint to a previous session.
- `analyze_manifest.py` — Stats + data quality summary from `.retagged.jsonl`.
- `staff_names.txt` + `common_words.txt` — Live fingerprints (**local only**, gitignored).

## Supporting / Historical (including Raspberry Pi)

- `record_session.py` — Short bring-up sessions (`--preview` / `--label`).
- `check_pi_environment.py`, `alsa_config.md`, `asoundrc.example`,
  `QUICKSTART_ALREADY_RUNNING_PI.md`, `pi_storage_recommendations.md`,
  `DAY1_UCA222_CHECKLIST.md` — **Pi/ALSA era**; keep for reference if you ever
  deploy on a Pi again. Not the school work-PC path.
- `test_px650.py`, `record_continuous.py` — early experiments.

## Wiring & Hardware Notes

Radio chain (any host): see `../wiring/Cobra_PX650_UCA222.md`  
(Windows section first; Pi section labeled optional).

For IT / privacy (no live data in Git): `../../docs/IT_SECURITY_REVIEW.md`.
