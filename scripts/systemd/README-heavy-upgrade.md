# EduPulse daily `large-v3` upgrade (systemd user timer)

After ~16:05 each day, upgrade today’s captures (and recent backlog) to **`large-v3`**, **only if the laptop is on AC / shore power**.

## What it does

1. Checks `/sys/class/power_supply/*/type=Mains` → `online=1` (wall power).  
   - On battery → **skip** (exit 0).  
   - No Mains device (desktop) → allow.  
2. Scans `~/edupulse/captures/*` for `tx_*.wav` whose sidecar `model` ≠ `large-v3`.  
3. Limits to folders dated within the last **30 days** (configurable).  
4. Runs `retro_upgrade_sidecars.py --skip-pyannote` per pending day.  
5. Appends to `~/edupulse/logs/heavy_upgrade_YYYY-MM-DD.log`.

## Install (this Linux user)

```bash
REPO=~/Documents/GrokBuild/EduPulse   # or ~/edupulse-code
chmod +x "$REPO/scripts/edupulse_heavy_upgrade_daily.sh"
ln -sfn "$REPO/scripts/edupulse_heavy_upgrade_daily.sh" ~/bin/edupulse-heavy-upgrade-daily.sh

mkdir -p ~/.config/systemd/user
cp "$REPO/scripts/systemd/edupulse-heavy-upgrade.service" ~/.config/systemd/user/
cp "$REPO/scripts/systemd/edupulse-heavy-upgrade.timer" ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now edupulse-heavy-upgrade.timer
systemctl --user list-timers | grep edupulse-heavy
```

Linger is already on for Joseph (`loginctl show-user … Linger=yes`) so the timer can fire without an active GUI session.

## Manual test

```bash
# Dry run (lists pending, respects AC check)
EDUPULSE_HEAVY_DRY_RUN=1 ~/bin/edupulse-heavy-upgrade-daily.sh

# Force run now (still AC-gated unless you override)
systemctl --user start edupulse-heavy-upgrade.service
journalctl --user -u edupulse-heavy-upgrade.service -n 50 --no-pager

# Allow on battery for a one-off
EDUPULSE_HEAVY_REQUIRE_AC=0 ~/bin/edupulse-heavy-upgrade-daily.sh
```

## Knobs (service `Environment=` or shell)

| Variable | Default | Meaning |
|----------|---------|---------|
| `EDUPULSE_HEAVY_REQUIRE_AC` | `1` | Must be on wall power |
| `EDUPULSE_HEAVY_MAX_AGE_DAYS` | `30` | `0` = all history with backlog |
| `EDUPULSE_WHISPER_DEVICE` | `cpu` | `cpu` (safe here; CUDA cublas broken) |
| `EDUPULSE_CAPTURES` | `~/edupulse/captures` | Capture root |
| `EDUPULSE_HEAVY_DRY_RUN` | `0` | Print pending only |

## Change the time

Edit `~/.config/systemd/user/edupulse-heavy-upgrade.timer` (`OnCalendar=`), then:

```bash
systemctl --user daemon-reload
systemctl --user restart edupulse-heavy-upgrade.timer
```
