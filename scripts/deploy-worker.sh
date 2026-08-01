#!/bin/bash
# Deploy passthrough Cloudflare Worker (replaces Render wake-up proxy).
# Requires CLOUDFLARE_API_TOKEN with Workers Scripts:Edit permission.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  echo "Set CLOUDFLARE_API_TOKEN in .env (Workers Scripts:Edit + Zone:Read)."
  echo "Create at: https://dash.cloudflare.com/profile/api-tokens"
  exit 1
fi

export CLOUDFLARE_API_TOKEN
npx wrangler@4 deploy

echo "Worker render-redirect updated to passthrough (tunnel origin)."
