#!/usr/bin/env bash
# Thin wrapper: run the laptop daily uploader (also usable manually).
# Canonical runtime script: ~/bin/edupulse-github-upload.sh
set -euo pipefail
exec "$HOME/bin/edupulse-github-upload.sh" "$@"
