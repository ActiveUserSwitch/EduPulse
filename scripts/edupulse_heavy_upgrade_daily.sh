#!/usr/bin/env bash
# Daily heavy Whisper upgrade (large-v3) for EduPulse captures.
# Intended for systemd --user timer after school (default 16:05).
#
# Guards:
#   - Skip unless on AC / shore power (laptop charging from wall)
#   - Only days with pending tx_*.wav whose sidecar model != large-v3
#   - By default only today + last EDUPULSE_HEAVY_MAX_AGE_DAYS (30)
#
# Env:
#   EDUPULSE_CAPTURES          default ~/edupulse/captures
#   EDUPULSE_ROOT              repo root
#   EDUPULSE_PYTHON            python with faster-whisper
#   EDUPULSE_HEAVY_MAX_AGE_DAYS  default 30; set 0 = all history with backlog
#   EDUPULSE_HEAVY_REQUIRE_AC  default 1; set 0 to allow battery
#   EDUPULSE_WHISPER_DEVICE    default cpu
#   EDUPULSE_HEAVY_DRY_RUN     set 1 to only print what would run

set -euo pipefail

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*"; }

is_on_ac() {
  local d online typ
  for d in /sys/class/power_supply/*; do
    [[ -f "$d/type" ]] || continue
    typ=$(cat "$d/type" 2>/dev/null || true)
    [[ "$typ" == "Mains" ]] || continue
    if [[ -f "$d/online" ]]; then
      online=$(cat "$d/online" 2>/dev/null || echo 0)
      [[ "$online" == "1" ]] && return 0
    fi
  done
  # No Mains device → desktop / always-plugged; treat as OK
  local found_mains=0
  for d in /sys/class/power_supply/*; do
    [[ -f "$d/type" ]] || continue
    [[ "$(cat "$d/type" 2>/dev/null)" == "Mains" ]] && found_mains=1
  done
  [[ "$found_mains" -eq 0 ]] && return 0
  return 1
}

resolve_root() {
  if [[ -n "${EDUPULSE_ROOT:-}" && -f "${EDUPULSE_ROOT}/hardware/capture/retro_upgrade_sidecars.py" ]]; then
    echo "$EDUPULSE_ROOT"
    return
  fi
  local c
  for c in \
    "$HOME/edupulse-code" \
    "$HOME/Documents/GrokBuild/EduPulse" \
    "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  do
    if [[ -f "$c/hardware/capture/retro_upgrade_sidecars.py" ]]; then
      echo "$c"
      return
    fi
  done
  log "ERROR: EduPulse repo not found"
  exit 1
}

day_needs_upgrade() {
  local day_dir="$1"
  local wav side model
  shopt -s nullglob
  for wav in "$day_dir"/tx_*.wav; do
    side="${wav%.wav}.json"
    if [[ ! -f "$side" ]]; then
      return 0
    fi
    model=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('model') or '')" "$side" 2>/dev/null || echo "")
    if [[ "$model" != "large-v3" ]]; then
      return 0
    fi
  done
  return 1
}

REQUIRE_AC="${EDUPULSE_HEAVY_REQUIRE_AC:-1}"
if [[ "$REQUIRE_AC" == "1" ]]; then
  if is_on_ac; then
    log "AC/shore power: yes"
  else
    log "SKIP: not on AC/shore power (battery only). Plug in and re-run, or wait for tomorrow."
    exit 0
  fi
else
  log "AC check disabled (EDUPULSE_HEAVY_REQUIRE_AC=0)"
fi

ROOT="$(resolve_root)"
CAPTURES="${EDUPULSE_CAPTURES:-$HOME/edupulse/captures}"
PY="${EDUPULSE_PYTHON:-$HOME/edupulse-env/bin/python}"
[[ -x "$PY" ]] || PY="$(command -v python3)"
RETRO="$ROOT/hardware/capture/retro_upgrade_sidecars.py"
MAX_AGE="${EDUPULSE_HEAVY_MAX_AGE_DAYS:-30}"
export EDUPULSE_WHISPER_DEVICE="${EDUPULSE_WHISPER_DEVICE:-cpu}"

LOG_DIR="${EDUPULSE_LOG_DIR:-$HOME/edupulse/logs}"
mkdir -p "$LOG_DIR" "$CAPTURES"
RUN_LOG="$LOG_DIR/heavy_upgrade_$(date +%F).log"

log "Repo=$ROOT"
log "Captures=$CAPTURES"
log "Python=$PY device=$EDUPULSE_WHISPER_DEVICE max_age_days=$MAX_AGE"
log "Run log=$RUN_LOG"

if [[ ! -f "$RETRO" ]]; then
  log "ERROR: missing $RETRO"
  exit 1
fi

# Collect day dirs with backlog (newest first)
mapfile -t ALL_DAYS < <(find "$CAPTURES" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)
PENDING=()
TODAY_PREFIX="$(date +%F)"
NOW_EPOCH=$(date +%s)

for name in "${ALL_DAYS[@]}"; do
  dir="$CAPTURES/$name"
  shopt -s nullglob
  wavs=("$dir"/tx_*.wav)
  shopt -u nullglob
  [[ ${#wavs[@]} -gt 0 ]] || continue

  # Age gate from leading YYYY-MM-DD in folder name
  if [[ "$MAX_AGE" != "0" && "$name" =~ ^([0-9]{4}-[0-9]{2}-[0-9]{2}) ]]; then
    day="${BASH_REMATCH[1]}"
    day_epoch=$(date -d "$day" +%s 2>/dev/null || echo 0)
    if [[ "$day_epoch" -gt 0 ]]; then
      age_days=$(( (NOW_EPOCH - day_epoch) / 86400 ))
      if [[ "$age_days" -gt "$MAX_AGE" ]]; then
        continue
      fi
    fi
  fi

  if day_needs_upgrade "$dir"; then
    PENDING+=("$name")
  fi
done

if [[ ${#PENDING[@]} -eq 0 ]]; then
  log "Nothing to do — no backlog within age window (or all already large-v3)."
  exit 0
fi

log "Pending days (${#PENDING[@]}): ${PENDING[*]}"

if [[ "${EDUPULSE_HEAVY_DRY_RUN:-0}" == "1" ]]; then
  log "DRY RUN — exiting without transcription"
  exit 0
fi

{
  echo "===== heavy upgrade start $(date -Is) ====="
  echo "pending: ${PENDING[*]}"
  for name in "${PENDING[@]}"; do
    echo
    echo "----- $name -----"
    # Prefer today first already via sort -r + date folders; process each day
    "$PY" -u "$RETRO" \
      --base-dir "$CAPTURES" \
      --day "$name" \
      --skip-pyannote \
      --skip-batch-info-scores \
      || echo "WARN: retro failed for $name (exit $?)"
  done
  echo "===== heavy upgrade end $(date -Is) ====="
} >>"$RUN_LOG" 2>&1

log "Finished. See $RUN_LOG"
exit 0
