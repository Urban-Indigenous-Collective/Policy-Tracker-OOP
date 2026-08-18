#!/bin/bash
# Stream live backfill/discovery logs from production.
# Usage: ./scripts/watch-backfill.sh [--plain]
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"
DEPLOY_USER="${DEPLOY_USER:-info@urbanindigenouscollective.org}"
DEPLOY_HOST="${DEPLOY_HOST:-100.71.124.8}"
PLAIN=false
if [ "${1:-}" = "--plain" ]; then
  PLAIN=true
fi

echo "Watching backfill on ${DEPLOY_HOST}..."
echo "Press Ctrl+C to stop."
echo ""

REMOTE="wsl -d Ubuntu -u root -- bash /opt/policy-tracker/scripts/watch-backfill-remote.sh"
if [ "$PLAIN" = true ]; then
  REMOTE="$REMOTE --plain"
else
  REMOTE="$REMOTE --progress"
fi

ssh -i "$SSH_KEY" -o BatchMode=yes "${DEPLOY_USER}@${DEPLOY_HOST}" "$REMOTE"
