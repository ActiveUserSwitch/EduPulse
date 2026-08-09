#!/usr/bin/env bash
# Fail a commit/push if likely-sensitive paths or patterns are staged/tracked.
# Used by scripts/push_to_github.sh and ~/bin/edupulse-github-upload.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${ROOT}" ]]; then
  echo "check_git_secrets: not a git repo" >&2
  exit 1
fi
cd "$ROOT"

FAIL=0

# Paths that must never be committed
BLOCK_PATH_REGEX='(HuggingFaceToken|\.env$|\.env\.|/(secrets|credentials)/|staff_names\.txt$|common_words\.txt$|\.wav$|\.flac$|/captures/|session_manifest|tx_[0-9].*\.json$|validation/(aligned_validation_data|human_consensus|focused_transcription|graduation_vad|hand_coding_log|current_validity)|semantic_map_radio_traffic\.json$|speaker_feasibility_report\.md$)'

check_list() {
  local label="$1"
  shift
  local files=("$@")
  for f in "${files[@]}"; do
    [[ -z "$f" ]] && continue
    if echo "$f" | grep -Eiq "$BLOCK_PATH_REGEX"; then
      echo "BLOCKED ($label): $f" >&2
      FAIL=1
    fi
  done
}

# Staged adds/modifies only (deleting a formerly leaked path is allowed / required)
mapfile -t STAGED < <(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null || true)
if [[ ${#STAGED[@]} -gt 0 ]]; then
  check_list "staged" "${STAGED[@]}"
fi

# Files that will remain tracked after this commit (exclude staged deletions)
mapfile -t TRACKED < <(git ls-files)
mapfile -t STAGED_DEL < <(git diff --cached --name-only --diff-filter=D 2>/dev/null || true)
declare -A DEL_SET=()
for d in "${STAGED_DEL[@]:-}"; do
  [[ -n "$d" ]] && DEL_SET["$d"]=1
done
REMAIN=()
for f in "${TRACKED[@]:-}"; do
  [[ -z "$f" ]] && continue
  [[ -n "${DEL_SET[$f]:-}" ]] && continue
  REMAIN+=("$f")
done
if [[ ${#REMAIN[@]} -gt 0 ]]; then
  check_list "tracked" "${REMAIN[@]}"
fi

# Content sniff on staged text files being added/modified (tokens, private keys)
while IFS= read -r f; do
  [[ -z "$f" || ! -f "$f" ]] && continue
  case "$f" in
    *.png|*.jpg|*.jpeg|*.gif|*.pdf|*.wav|*.bin|*.pt) continue ;;
  esac
  if grep -EIq 'hf_[A-Za-z0-9]{20,}|BEGIN (RSA |OPENSSH )?PRIVATE KEY|AKIA[0-9A-Z]{16}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,}' "$f" 2>/dev/null; then
    echo "BLOCKED (token-like content): $f" >&2
    FAIL=1
  fi
done < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)

if [[ "$FAIL" -ne 0 ]]; then
  echo "" >&2
  echo "check_git_secrets: refusing to proceed. Remove sensitive files from the index:" >&2
  echo "  git rm --cached <file>   # keep local copy" >&2
  echo "  Ensure .gitignore covers the path, then re-stage." >&2
  echo "Synthetic demos OK: validation/demo_validation_sample.csv, *.example.txt" >&2
  exit 1
fi

echo "check_git_secrets: OK (no blocked paths/tokens detected in staged+tracked set)"
exit 0
