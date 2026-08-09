# Wiring: Cobra PX650 + Behringer UCA222

This document describes the physical connections for **Option A** (minimal control
via physical knobs only).

**Primary host (current plan):** Windows work PC (WASAPI via `sounddevice`).  
**Optional / historical:** Raspberry Pi 4 + ALSA — see notes at the end.

## Hardware

- **Host PC** (Windows work station preferred; Linux laptop OK)
- Cobra PX650 radio (2.5mm accessory / headset jack on the side or back)
- 2.5mm TRS male → dual RCA male cable (confirmed correct cable)
- Behringer UCA222 USB audio interface
- USB cable for the UCA222 (prefer USB 3.0 port when available)
- (Optional) Powered USB hub if power issues appear

## Connections (Option A)

1. **Radio → Cable**
   - Plug the 2.5mm (TRS) end firmly into the Cobra PX650's accessory jack (the port
     normally used for headsets/speaker-mics).
   - The PX650 should be powered on.

2. **Cable → UCA222**
   - Connect the two RCA plugs into the **LINE INPUT** jacks on the back of the
     UCA222 (not the phono/turntable inputs if it has them).
   - Left/Right orientation: doesn't matter much for mono-ish radio traffic, but
     consistent is nice. With the 2.5mm cable on this radio, typically **only one
     channel** will carry strong audio.

3. **UCA222 → host PC (primary: Windows)**
   - Plug the UCA222's USB cable into the work PC (or laptop).
   - Windows: set the device as input or pass `--device N` from
     `check_audio_environment.py --list-devices` / `record_with_transcribe.py --list-devices`.
   - If open fails: Sound → device → Properties → Advanced → uncheck exclusive mode.
   - See `hardware/capture/WINDOWS_QUICKSTART.md`.

4. **Knob Philosophy (Option A)**
   - Primary level control: the volume knob on the Cobra PX650 itself.
   - Secondary/fine level control: the two hardware gain knobs on the front of the
     UCA222.
   - Do **not** rely on host software gain in early testing unless the hardware knobs
     can't get you into a good range.
   - Start conservative: PX650 ~25-35%, UCA222 gains ~40-60%. Increase radio volume
     first if too quiet.

## First Power-Up Checklist

- [ ] Host PC ready (Windows preferred).
- [ ] UCA222 plugged into USB.
- [ ] 2.5mm seated fully in the PX650.
- [ ] RCA plugs fully seated in UCA222 Line In.
- [ ] PX650 turned on and volume at low-medium.
- [ ] Verify detection (prefer sounddevice, not ALSA-only):

```powershell
# Windows (primary)
python hardware\capture\check_audio_environment.py --list-devices
```

```bash
# Linux (optional)
python hardware/capture/check_audio_environment.py --list-devices
# Historical Pi-only: arecord -l
```

Expect a Behringer / UCA222 / USB Audio entry with a numeric **index** for `--device`.

## Level Setting Tips

- Use `python hardware/capture/record_session.py --preview` (or
  `edupulse-record.ps1` / `edupulse-record --preview`) to watch live levels.
- With the PX650 + 2.5mm cable, expect one channel to dominate. Scripts highlight
  the active channel.
- Watch for clipping (peaks near 0 dBFS).
- Rule: turn the radio volume knob down before touching UCA222 knobs if you see
  clipping on normal speech.

## Troubleshooting Physical Layer

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| No UCA222 in device list | Wrong USB port / cable / power | Reseat USB, try another port/hub, reboot |
| No audio in either channel | Cable not seated, radio off or volume 0 | Reseat 2.5mm, power on PX650, raise volume |
| Only one channel works | Normal for this radio + cable | Analysis uses louder channel |
| Crackling / USB dropouts | USB power or bandwidth | Hub, shorter cable, USB 3 port |
| Very low levels | Radio/UCA222 gain low | Raise PX650 knob first |
| Heavy clipping | Radio output too hot | Lower PX650 volume |
| Windows stream open fails | Exclusive mode | Device Properties → Advanced → uncheck exclusive |

## Optional / historical: Raspberry Pi 4

If you deliberately deploy on a Pi (not the primary plan):

- Prefer blue USB 3.0 ports; `arecord -l` / `alsa_config.md` may apply.
- See `hardware/capture/QUICKSTART_ALREADY_RUNNING_PI.md` and
  `DAY1_UCA222_CHECKLIST.md` (both labeled historical).

## Notes for Later

- Data dir default: `~/edupulse/captures` or `%USERPROFILE%\edupulse\captures`.
- Strain relief on 2.5mm and USB cables for long sessions.

## References

- **Primary:** `hardware/capture/WINDOWS_QUICKSTART.md`
- `hardware/capture/check_audio_environment.py`
- Historical Pi: `DAY1_UCA222_CHECKLIST.md`, `QUICKSTART_ALREADY_RUNNING_PI.md`
- Session archive: `SESSION_SUMMARY_2025-05-27.md`
If you have photos of the actual wiring or updated pin/jack details, add them here
or link to an album.

**Safety:** Never work on powered radio hardware with wet hands. Use appropriate
  audio levels to avoid hearing damage when testing with speakers/headsets.
