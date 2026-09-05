#!/usr/bin/env bash
# Build a sneakernet update pack for desk hosts with little/no internet (Pi or locked laptop).
# Run from a networked machine that has this git clone (typically home Linux lab).
#
# Usage:
#   ./scripts/make_offline_update_pack.sh /path/to/UsbStick/EduPulse-update-2026-08-10
#
# Optional env:
#   INCLUDE_WHEELS=1          # pip download into wheels/ (needs network)
#   OFFLINE_PIP_PLATFORM=...  # e.g. manylinux_2_34_aarch64 for Pi OS 64-bit
#   INCLUDE_WHISPER_HINT=1    # write a note about copying models (does not download huge models)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:?Usage: $0 /path/to/EduPulse-update-YYYY-MM-DD}"
BRANCH="${BRANCH:-main}"

mkdir -p "$DEST"
cd "$ROOT"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git fetch origin "$BRANCH" 2>/dev/null || true
  REF="origin/$BRANCH"
  if ! git rev-parse --verify "$REF" >/dev/null 2>&1; then
    REF="$BRANCH"
  fi
  git bundle create "$DEST/edupulse.bundle" "$REF"
  git rev-parse "$REF" >"$DEST/COMMIT.txt"
  echo "bundle: $REF -> $(cat "$DEST/COMMIT.txt")"
else
  echo "ERROR: not a git repo: $ROOT" >&2
  exit 1
fi

cp -f "$ROOT/requirements.txt" "$DEST/requirements.txt"
if [[ -f "$ROOT/pyproject.toml" ]]; then
  cp -f "$ROOT/pyproject.toml" "$DEST/pyproject.toml"
fi

if [[ "${INCLUDE_WHEELS:-0}" == "1" ]]; then
  mkdir -p "$DEST/wheels"
  # Default: download for *this* machine. For a Pi, set OFFLINE_PIP_PLATFORM and prefer
  # building the pack on an aarch64 box, or use pip download with --platform/--only-binary.
  if [[ -n "${OFFLINE_PIP_PLATFORM:-}" ]]; then
    pip download -r "$DEST/requirements.txt" -d "$DEST/wheels" \
      --platform "$OFFLINE_PIP_PLATFORM" --only-binary=:all: || {
      echo "WARN: platform wheel download failed; try building pack on a Pi once online" >&2
    }
  else
    pip download -r "$DEST/requirements.txt" -d "$DEST/wheels"
  fi
fi

if [[ "${INCLUDE_WHISPER_HINT:-1}" == "1" ]]; then
  cat >"$DEST/MODELS.txt" <<'EOF'
Whisper / faster-whisper model files are large. Prefetch them once while the
desk machine (or a sibling Pi) has internet, then leave them on local disk.

Do not put live radio captures or staff_names.txt into this update pack.
EOF
fi

cat >"$DEST/README-APPLY.txt" <<EOF
EduPulse offline update pack
============================
Built from: $ROOT
Commit:     $(cat "$DEST/COMMIT.txt")
Branch:     $BRANCH

ON THE DESK MACHINE (Pi or laptop), with this folder on a USB stick:

1) Code update (existing clone, e.g. ~/edupulse or ~/Documents/GrokBuild/EduPulse):

     cd ~/edupulse
     git pull /path/to/this/pack/edupulse.bundle $BRANCH
     # If pull complains about unrelated histories, use:
     #   git fetch /path/to/this/pack/edupulse.bundle $BRANCH:refs/remotes/usb/$BRANCH
     #   git merge refs/remotes/usb/$BRANCH

2) Python deps (only if requirements changed and wheels/ exists):

     source ~/edupulse-env/bin/activate
     pip install --no-index --find-links=/path/to/this/pack/wheels -r /path/to/this/pack/requirements.txt

3) Do NOT overwrite:
     - captures / ~/edupulse/captures
     - hardware/capture/staff_names.txt
     - hardware/capture/common_words.txt
     - HuggingFaceToken.txt / secrets

4) Smoke:

     python -c "from edupulse.analysis import categorize_transmission; print('ok')"
     python hardware/capture/check_audio_environment.py

See hardware/capture/OFFLINE_AND_PI_PATH.md in the repo for the full dual-path plan.
EOF

echo "Pack ready: $DEST"
ls -la "$DEST"
