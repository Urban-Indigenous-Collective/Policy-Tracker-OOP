#!/bin/bash
set -euo pipefail
cd /opt/policy-tracker

touch .env
grep -q '^SLACK_DEFER_DISCOVERY=' .env || echo 'SLACK_DEFER_DISCOVERY=true' >> .env
grep -q '^SLACK_SUMMARY_CRON=' .env || echo 'SLACK_SUMMARY_CRON=30 7 * * *' >> .env

echo "=== Slack env ==="
grep SLACK .env

docker compose stop scheduler || true

if [ -f backfill-loop.log ]; then
  echo "=== Backfill tail ==="
  tail -8 backfill-loop.log
fi
