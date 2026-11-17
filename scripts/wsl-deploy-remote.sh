#!/bin/bash
# Run on the server via WSL after files are synced.
set -euo pipefail

DEPLOY_PATH="${1:-/opt/policy-tracker}"

cd "$DEPLOY_PATH"
test -f .env || { echo "Missing .env on server"; exit 1; }
test -f cloudflared/credentials.json || { echo "Missing cloudflared/credentials.json on server"; exit 1; }

chmod 644 cloudflared/credentials.json

# tunnel profile also brings nginx + Next (Phase 5: public UI on policy.*).
# Profiles must be active on `build` too — otherwise frontend/nginx images are skipped.
docker compose --profile tunnel build
docker compose --profile tunnel up -d --remove-orphans --force-recreate frontend nginx
# cloudflared does not hot-reload ingress; force recreate so volume-mounted
# cloudflared-docker.yml changes take effect even when the service def is unchanged.
docker compose --profile tunnel up -d --force-recreate tunnel
docker compose ps

PUBLIC_PORT="${PUBLIC_HOST_PORT:-8095}"
if [[ -f .env ]]; then
  env_port="$(grep -E '^PUBLIC_HOST_PORT=' .env | tail -1 | cut -d= -f2- || true)"
  PUBLIC_PORT="${env_port:-$PUBLIC_PORT}"
fi

echo "Smoke: nginx → Next + Flask API (localhost:${PUBLIC_PORT})"
ok=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  code="$(curl -sS -o /tmp/pt-home.html -w '%{http_code}' "http://127.0.0.1:${PUBLIC_PORT}/" || echo 000)"
  if [[ "$code" == "200" ]] && grep -qi 'html\|__next\|MMIP\|Urban Indigenous' /tmp/pt-home.html 2>/dev/null; then
    echo "home:200 (Next UI)"
    ok=1
    break
  fi
  echo "home wait ${i}/10 (got ${code})"
  sleep 3
done
[[ "$ok" == "1" ]] || { echo "FAIL: Next UI not serving on :${PUBLIC_PORT}"; exit 1; }
curl -fsS -o /dev/null -w "api:%{http_code}\n" "http://127.0.0.1:${PUBLIC_PORT}/api/v1/health"
curl -fsS -o /dev/null -w "health:%{http_code}\n" "http://127.0.0.1:${PUBLIC_PORT}/health-check"
