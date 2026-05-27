# ALSA Configuration for Behringer UCA222 on Raspberry Pi 4

This document contains recommended ALSA settings for reliable capture with the UCA222 on a Pi 4.

## Quick Start

Create or edit `~/.asoundrc` on the Pi:

```bash
nano ~/.asoundrc
```

### Recommended Minimal Config

```alsa
# ~/.asoundrc - EduPulse / UCA222 friendly settings

pcm.!default {
    type hw
    card UCA222
    device 0
}

ctl.!default {
    type hw
    card UCA222
}

# Higher quality capture settings (used by our Python scripts)
pcm.edupulse_capture {
    type hw
    card UCA222
    device 0
    format S16_LE
    rate 16000
    channels 2
    period_size 1024
    buffer_size 4096
}
```

## Useful Commands

Check the card index:

```bash
arecord -l
aplay -l
```

Test recording directly with ALSA:

```bash
arecord -D hw:UCA222,0 -f S16_LE -r 16000 -c 2 -d 10 test.wav
```

View current controls (very useful for gain staging):

```bash
alsamixer -c UCA222
```

You can also use:

```bash
amixer -c UCA222 scontrols
```

## Tips Specific to EduPulse + PX650

- The UCA222 input gain knobs on the front are the primary controls.
- In alsamixer, the "Mic" or "Line" capture controls can be left at 0–20% in most cases.
- We do most level management with the radio volume knob + the physical knobs on the UCA222.
- 16kHz / 2 channels (or mono if you prefer) is sufficient for Whisper and acoustic feature extraction.

## Future Use

Once we move to continuous recording, we will likely reference `pcm.edupulse_capture` in the Python scripts for more deterministic buffer behavior.

For now, the default `hw` device works well for short sessions.
