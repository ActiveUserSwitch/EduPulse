# LAST TWO DAYS OF SCHOOL — Final Data Collection Push

**You have (at most) two full days left.** The June 3 run gave us a lot of raw
  audio but was mostly ruined by gain/VAD (82% of the 918 segments were
  static/hallucination). We have since added:

- Loud startup calibration + live RMS during the critical first 3 seconds so you
  can fix the knob *before* the long run starts.
- Automatic "Noise / Squelch / Hallucination" bucketing (with the new Testing category).
- Better defaults and guidance.

**Do not start a full day without doing a 15-30 minute real test first (today).**

The goal for the remaining days is still the same: per-tx .wav + sidecar JSON +
manifest with clean INC + category + students/roles on the *actual* radio traffic
(logistics, dismissals, checks, etc.). The saved WAVs will let us do much better
offline with bigger models after the year ends.

**See also: hardware/capture/LAST_TWO_DAYS_AND_BREAK_PLAN.md** — this document
  explicitly calls out the "this + one more full day + one quick iteration window
  before 3-month break" reality and what "success" looks like for data collection
  vs. live perfection.

(The previous "First Long-Run..." content below is kept for reference but the
pre-run test is now mandatory before any full-day attempt.)

## Pre-Run (do today)

1. **Hardware / levels**
   - Plug in the UCA222 (use a powered USB hub if possible for stability).
   - Run a short test with the new tool or `record_session.py --preview` and adjust
     radio volume + UCA222 knobs until you see good RMS on one channel during a
     real key-up.
   - Note the device index if auto-detect is flaky (`--device N`).

2. **Environment**
   - `pip install -r requirements.txt` (or in your venv).
   - `python -m py_compile hardware/capture/record_with_transcribe.py test/test_*.py
     edupulse/analysis.py`
   - Run `python hardware/capture/record_with_transcribe.py --skip-calibration
     --list-categories` (quick smoke, test the cold start path).

3. **Storage**
   - Decide on base dir. Laptop: `~/edupulse/captures` is fine (or an external SSD).
   - Create it: `mkdir -p ~/edupulse/captures`
   - Estimate: ~64 kB/sec while someone is talking. With radio PTT duty cycle you
     will be fine for a full school day even on a modest drive. The tool will warn
     on low space.

4. **COLD START — NO PRE-FLIGHT POSSIBLE (you only have access to the radio during
  the school day)**
   - Both remaining full days start "cold" with whatever gain/knob position was left
     from the previous run (which on June 3 produced ~82% noise because idle
     background was way too hot, around -2 dB instead of -45..-55).
   - **Use --skip-calibration** on both days (see the recommended command below and
     the COLD START banner the script will print).
   - The code is now hardened for this:
     - Skips the 1.5s measurement.
     - Seeds quiet conservatively.
     - Faster adaptation + higher initial margin for the first 5 minutes.
     - Live line always shows q~ (learned quiet from gaps) and thr~.
     - If q~ > -35 it appends loud "[!!! GAIN TOO HIGH ...]" and every ~45s prints full
       urgent instructions.
   - **On the school day morning (Cold Start Protocol)**:
     - Start the tmux session and the capture command as early as you can (before or
       right when the day begins).
     - The first transmissions (and possibly first 20-40+ minutes) may produce
       long/noisy segments if the knob is still high.
     - **At the very first quiet gap** you get (after arrival, during passing period,
       after a bell when the radio goes silent, between classes):
       - Watch the live metering line.
       - Turn the UCA222 input knob DOWN until the q~ number drops to the -45 to -55
         range.
       - New segments after that point should be short, clean, and properly VAD'd.
     - Bad early segments are auto-flagged as "Noise / Squelch / Hallucination", do not
       create INC-xxx, and are excluded from the quality stats.
   - After each full day: run the analyzer immediately and look at the "DATA QUALITY
     SUMMARY" at the bottom. It will tell you usable % , how much was protected by
     the noise filter, etc.
   - See LAST_TWO_DAYS_AND_BREAK_PLAN.md for the full cold-start schedule and "one
     quick iteration between the two days" guidance using retag_session.py.

5. **Tmux / persistence**
   - Practice the full sequence (the scripts now auto-find the local `edupulse/`
     package):
     ```
     tmux new -s edupulse
     cd ~/Documents/GrokBuild
     source ~/edupulse-env/bin/activate
     python hardware/capture/record_with_transcribe.py --skip-calibration --help
     ```
   - Start the real capture inside the tmux session (see the command block below).
   - Detach: Ctrl-b then d
   - Re-attach later: `tmux attach -t edupulse`
   - Alternative (no tmux install): `nohup python ... >
     ~/edupulse/captures/capture.log 2>&1 &` (then `tail -f` the log).

6. **VAD / radio tuning (critical lesson from June 3 real run)**
   - The script now does a *short* (1.5s) best-effort background measurement at start
     + **continuous live adaptation** of the quiet floor from the actual gaps
     between transmissions.
   - You said it: real transmissions break the floor almost instantaneously. The
     system now learns the real "quiet gap" level from those short silences
     between PTTs instead of relying only on the startup sample.
   - In the live metering line you will see `q~NN.N` (current learned
     quiet/background) and `thr~NN.N` (the effective threshold being used right
     now = max of your --speech-threshold and q + 10dB).
   - Main thing for you to do: turn the physical UCA222 knob until the *quiet gaps*
     (when no one is keyed) show q around -45 to -55 dB.
   - The live line updates every ~0.3s so you get immediate feedback.
   - Good starting point: `--speech-threshold -32 --silence-timeout 1.0
     --tail-padding-sec 0.5 --pre-roll-sec 0.3`
     (pre-roll prevents slight beginning cutoffs by including audio from just before
     the energy threshold; tail padding prevents early end cutoffs and makes clips
     sound less choppy/abrupt).
   - If traffic is constant at the exact moment you start the program, just let it
     run — as soon as a quiet gap appears the `q~` will drop and the threshold
     will adapt. You can still tweak the knob live.

## Tomorrow Morning - Start the Run

Recommended command for the last two full days (only after the pre-flight test
above passes):

```bash
cd ~/Documents/GrokBuild
source ~/edupulse-env/bin/activate
python hardware/capture/record_with_transcribe.py \
  --data-dir ~/edupulse/captures \
  --session "last-day-1" \
  --skip-calibration \
  --model tiny \
  --speech-threshold -32 \
  --silence-timeout 1.0 \
  --tail-padding-sec 0.5 \
  --pre-roll-sec 0.3 \      # include a bit before energy crosses threshold, to fix slight beginning cutoffs
  --initial-prompt "..." \
  --known-staff-file hardware/capture/staff_names.txt \
  --common-words-file hardware/capture/common_words.txt
```

**At the very start the script does a short 1.5s background measurement and then
  shows live RMS + q~ (learned quiet floor) and thr~ (current effective threshold)
  on every update.**

Use the live line (especially the q~ number) to adjust the UCA222 knob until quiet
gaps between real PTTs sit at -45..-55 dB.

The adaptation is continuous — even if the initial 1.5s had traffic, the first
real quiet gap will pull q~ down and the system will start using a sensible
threshold.

If after 30-60s you are still seeing constant triggering or very long segments,
Ctrl-C and turn the knob down more, then restart.

- Leave it running. Watch the live metering and occasional transcription lines.
- If the laptop sleeps or you close the lid, the tmux session may survive or you
  may need to restart (the tool is designed for one continuous run).

## During the Day (light monitoring)

- `tmux attach -t edupulse` or `tail -f .../capture.log`
- Occasionally look at the growing manifest or the latest .json files.
- If you see something interesting on the radio that the tool should have caught,
  note the wall time — you can later correlate with the tx files.

## End of Day / Shutdown

- Ctrl+C in the capture (or kill the process).
- The tool will flush the queue, finish any in-flight transcription, write
  `session_summary.json` + update the info file.
- Safely copy / rsync the whole session dir to a backup drive if you have one.
- Quick review:
  ```bash
  python hardware/capture/analyze_manifest.py ~/edupulse/captures/2026-06-05_finals-day3/session_manifest.jsonl
  ls ~/edupulse/captures/2026-06-05_finals-day3/ | head
  du -sh ~/edupulse/captures/2026-06-05_finals-day3/
  ```

## Iteration After the Run (the whole point) — especially tight with only two days left

- **Quick look**: the manifest + sidecars give you transcription + INC + category
  for everything. Run the analyzer — it now prints a "DATA QUALITY SUMMARY"
  (usable %, noise rate, meaningful tx count, real INC count) designed for fast
  go/no-go decisions.
- **Between Day 1 and Day 2 (your one quick live iteration window)**: edit
  `edupulse/analysis.py`, then
  `python hardware/capture/retag_session.py
  <day1-session>/session_manifest.reprocessed.jsonl`
  This re-applies current rules to the transcripts, patches sidecars, and gives you
  a .retagged.jsonl. Re-analyze to see if the problem is fixed before committing
  the final day.
- **Heavier models** (great for the 3-month break): point `test/test_whisper.py`
  at individual tx_*.wav (or loop). The saved raw stereo 16-bit files are perfect
  for base/medium/large-v3.
- **Rules tuning during break**: edit `edupulse/analysis.py` (single source), use
  `retag_session.py` on any previous manifests, produce validated versions. The
  .wav + sidecar metadata let you do proper validation by listening.
- **Metrics & validation**: count tx per hour, average INC length, busiest
  categories, student mention rate, role usage (Athletic/JROTC vs admin), etc.
  Sample 30-50 real tx, listen + score transcription/category/INC quality.
- See `LAST_TWO_DAYS_AND_BREAK_PLAN.md` for the explicit schedule and what "good
  enough for live" vs. "improve offline" looks like.

## Gotchas / Notes

- On laptop: watch CPU temp / fan if using a heavier real-time model. `tiny` +
  int8 is the safe "set and forget" choice.
- Disk: the tool stops itself if space gets critically low.
- Multiple runs in one day: each gets its own dated+label dir. You can concatenate
  manifests later if you want one view.
- Student names: the full "First Last" logic is deliberately strict (prevents
  "Bobby" alone from linking unrelated dismissals).
- Sensitive content: everything stays local for now. We can add redaction tooling later.

## Next (after we have real data)

- Better categorization (perhaps a small fine-tune or embedding classifier on the
  collected transcripts).
- Persist INC state across restarts.
- Continuous background "heavy" analysis pipeline.
- Return the whole thing to the Pi + SSD once the laptop run proves the data model.

Good luck tomorrow — this should give us exactly the corpus we need to make the
analysis real.
