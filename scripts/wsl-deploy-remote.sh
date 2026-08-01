#!/bin/bash
# Run on the server via WSL after files are synced.
set -euo pipefail

DEPLOY_PATH="${1:-/opt/policy-tracker}"

cd "$DEPLOY_PATH"
test -f .env || { echo "Missing .env on server"; exit 1; }
test -f cloudflared/credentials.json || { echo "Missing cloudflared/credentials.json on server"; exit 1; }

chmod 644 cloudflared/credentials.json

docker compose build
docker compose --profile tunnel up -d --remove-orphans
docker compose ps
