#!/bin/bash
# Stream live discovery logs from the production server.
# Usage: ./scripts/watch-discovery.sh
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"
DEPLOY_USER="${DEPLOY_USER:-info@urbanindigenouscollective.org}"
DEPLOY_HOST="${DEPLOY_HOST:-100.71.124.8}"

echo "Streaming discovery logs from ${DEPLOY_HOST}..."
echo "Press Ctrl+C to stop."
echo ""

ssh -i "$SSH_KEY" -o BatchMode=yes "${DEPLOY_USER}@${DEPLOY_HOST}" \
  "wsl -d Ubuntu -u root -- bash -lc 'CID=\$(docker ps -q --filter name=policy-tracker-web-run | head -1); if [ -z \"\$CID\" ]; then echo \"No discovery container running.\"; docker ps --filter name=policy-tracker; exit 1; fi; docker logs -f --tail 50 \$CID'"
