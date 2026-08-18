#!/bin/bash
# Sync NY_OPEN_LEGISLATION_KEY from local .env to production (gitignored secrets).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
WSL_DEPLOY_PATH="${WSL_DEPLOY_PATH:-/opt/policy-tracker}"
DEPLOY_HOST="${DEPLOY_HOST:-100.71.124.8}"
DEPLOY_USER="${DEPLOY_USER:-info@urbanindigenouscollective.org}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"
SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o BatchMode=yes)

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"
if [ -z "${NY_OPEN_LEGISLATION_KEY:-}" ]; then
  echo "NY_OPEN_LEGISLATION_KEY not set in local .env"
  exit 1
fi

TMP=$(mktemp)
printf 'NY_OPEN_LEGISLATION_KEY=%s\n' "$NY_OPEN_LEGISLATION_KEY" > "$TMP"
rsync -az -e "ssh ${SSH_OPTS[*]}" "$TMP" \
  "${DEPLOY_USER}@${DEPLOY_HOST}:/tmp/ny_key_line.txt" \
  --rsync-path="wsl -d Ubuntu -u root -- rsync"
rm -f "$TMP"

ssh "${SSH_OPTS[@]}" "${DEPLOY_USER}@${DEPLOY_HOST}" \
  "wsl -d Ubuntu -u root -- bash ${WSL_DEPLOY_PATH}/scripts/prod_install_ny_key.sh"

echo "Done. Restart discovery/backfill container to pick up the key."
