# Wiring: Cobra PX650 + Behringer UCA222 on Raspberry Pi 4

This document describes the physical connections for **Option A** (minimal control
via physical knobs only).

## Hardware

- Raspberry Pi 4 Model B (8GB)
- Cobra PX650 radio (2.5mm accessory / headset jack on the side or back)
- 2.5mm TRS male → dual RCA male cable (confirmed correct cable)
- Behringer UCA222 USB audio interface
- USB cable for the UCA222 (preferably to a blue USB 3.0 port on the Pi)
- (Optional but recommended for initial testing) Powered USB hub if power issues appear

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

3. **UCA222 → Pi**
   - Plug the UCA222's USB cable into a USB 3.0 port (the blue ones) on the Raspberry
     Pi 4.
   - Avoid the black USB 2.0 ports for best results with audio class devices.
   - If the Pi is powered via its official supply and you see dropouts, try a powered
     USB hub between the UCA222 and the Pi.

4. **Knob Philosophy (Option A)**
   - Primary level control: the volume knob on the Cobra PX650 itself.
   - Secondary/fine level control: the two hardware gain knobs on the front of the
     UCA222.
   - Do **not** rely on ALSA software gain in early testing unless the hardware knobs
     can't get you into a good range.
   - Start conservative: PX650 ~25-35%, UCA222 gains ~40-60%. Increase radio volume
     first if too quiet.

## First Power-Up Checklist

- [ ] Pi powered off before first connection (recommended).
- [ ] UCA222 plugged into blue USB port.
- [ ] 2.5mm seated fully in the PX650.
- [ ] RCA plugs fully seated in UCA222 Line In.
- [ ] PX650 turned on and volume at low-medium.
- [ ] Pi powered on.
- [ ] Verify detection:

```bash
arecord -l
lsusb | grep -i -E 'behringer|uca|2902'   # 08bb:2902 is common for UCA222 class devices
```

Expected to see something like:
```
card 1: UCA222 [BEHRINGER UCA222], device 0: USB Audio [USB Audio]
```

## Level Setting Tips

- Use `python hardware/capture/record_session.py --preview` (or the
  `edupulse-record --preview` launcher) to watch live RMS/peak levels without
  writing files.
- With the PX650 + 2.5mm cable, expect one channel to dominate. The script will
  highlight `[L active]` or `[R active]`.
- Watch for clipping (peaks near or above ~0 dBFS, or the warning in `test_px650.py`).
- Rule: turn the radio volume knob down before touching UCA222 knobs if you see
  clipping on normal speech.

## Troubleshooting Physical Layer

| Symptom                    | Likely cause                          | Fix |
|----------------------------|---------------------------------------|-----|
| No UCA222 in arecord -l    | Wrong USB port / cable / power        | Try blue port, different cable, powered hub, reboot |
| No audio in either channel | Cable not seated, radio off or volume 0, wrong jack on radio | Reseat 2.5mm, power on PX650, raise volume |
| Only one channel works     | Normal for this radio + cable         | Use the louder channel in analysis later |
| Crackling / USB dropouts   | Insufficient USB power or bandwidth   | Powered hub, shorter cable, USB 3 port |
| Very low levels            | Radio volume too low or UCA222 gain too low | Raise PX650 knob first |
| Heavy clipping             | Radio output hot for the gain setting | Lower PX650 volume significantly |

## Notes for Later

- Once basic capture is stable we may add a small ALSA config (see
  `alsa_config.md` and `asoundrc.example` in capture/).
- SSD mounting will change the recommended `--data-dir` / base path for recordings.
- For continuous / always-on later, consider a small enclosure or strain relief on
  the 2.5mm and USB cables.

## References

- `hardware/capture/DAY1_UCA222_CHECKLIST.md`
- `hardware/capture/QUICKSTART_ALREADY_RUNNING_PI.md`
- `hardware/capture/record_session.py --help`
- Session summary: `SESSION_SUMMARY_2025-05-27.md`

If you have photos of the actual wiring or updated pin/jack details, add them here
or link to an album.

**Safety:** Never work on powered radio hardware with wet hands. Use appropriate
  audio levels to avoid hearing damage when testing with speakers/headsets.
