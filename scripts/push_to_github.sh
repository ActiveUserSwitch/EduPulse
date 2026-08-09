#!/usr/bin/env bash
# Thin wrapper: run the laptop daily uploader (also usable manually).
# Canonical runtime script: ~/bin/edupulse-github-upload.sh
# Always runs scripts/check_git_secrets.sh (via the uploader) before push.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/scripts/check_git_secrets.sh" ]]; then
  bash "$ROOT/scripts/check_git_secrets.sh" || exit 1
fi
exec "$HOME/bin/edupulse-github-upload.sh" "$@"
