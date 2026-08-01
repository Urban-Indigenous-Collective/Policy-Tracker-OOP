#!/bin/bash
# Deploy Policy Tracker to the remote server over SSH.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

DEPLOY_HOST="${DEPLOY_HOST:-100.71.124.8}"
DEPLOY_USER="${DEPLOY_USER:-info@urbanindigenouscollective.org}"
WSL_DEPLOY_PATH="${WSL_DEPLOY_PATH:-/opt/policy-tracker}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/uic-learning-deploy}"
SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o BatchMode=yes)

echo "=== Deploying to ${DEPLOY_USER}@${DEPLOY_HOST}:${WSL_DEPLOY_PATH} ==="

rsync -az --delete \
  --exclude '.git' \
  --exclude '.env' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'cloudflared/credentials.json' \
  --exclude '.DS_Store' \
  --exclude 'bill_details.xlsx' \
  -e "ssh ${SSH_OPTS[*]}" \
  --rsync-path="wsl -d Ubuntu -u root -- rsync" \
  ./ "${DEPLOY_USER}@${DEPLOY_HOST}:${WSL_DEPLOY_PATH}/"

ssh "${SSH_OPTS[@]}" "${DEPLOY_USER}@${DEPLOY_HOST}" \
  "wsl -d Ubuntu -u root -- bash ${WSL_DEPLOY_PATH}/scripts/wsl-deploy-remote.sh ${WSL_DEPLOY_PATH}"

echo ""
echo "Deploy complete."
echo "  Tailscale: http://${DEPLOY_HOST}:${POLICY_HOST_PORT:-8002}/health-check"
echo "  Public:    https://policy.urbanindigenouscollective.org/health-check"
