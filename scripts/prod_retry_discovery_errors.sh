#!/bin/bash
# Retry discovery for URLs that failed with error status in seen_store.
# Uses reopen_llm_failures.py so matching rows are audited (JSON + sqlite backup)
# before delete — do not inline DELETE again.
set -euo pipefail
cd /opt/policy-tracker
mkdir -p data/backups

docker compose stop scheduler || true

echo "=== Clearing error rows from seen_store (audited reopen) ==="
docker compose run --rm -T scheduler python scripts/reopen_llm_failures.py \
  --errors-only --apply

echo "=== Retry pass (errors only via cleared seen_store) ==="
docker compose run --rm -T \
  -e DISCOVERY_MAX_ANALYSES_PER_RUN=9999 \
  -e SLACK_BACKFILL_SUMMARY=true \
  scheduler python scripts/run_discovery.py 2>&1 | tee -a data/backfill-retry-errors.log

docker compose up -d scheduler
echo "=== Scheduler restarted ==="
