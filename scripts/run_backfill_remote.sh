#!/bin/bash
# Run on production host (via WSL) — discovery backfill loop.
set -euo pipefail

DEPLOY_PATH="${1:-/opt/policy-tracker}"
LOG="${DEPLOY_PATH}/data/backfill-loop.log"
MAX_PASSES="${BACKFILL_MAX_PASSES:-50}"

cd "$DEPLOY_PATH"
mkdir -p data

echo "=== Backfill started $(date -Iseconds) ===" | tee -a "$LOG"

# Backup and optionally clear rejected/error so we re-evaluate
docker compose run --rm -T scheduler bash -lc '
  cp data/discovery.db "data/discovery.db.bak-$(date +%Y%m%d-%H%M)" 2>/dev/null || true
  echo "Seen store before purge:"
  sqlite3 data/discovery.db "SELECT status, COUNT(*) FROM seen_candidates GROUP BY status;" 2>/dev/null || echo "(empty)"
  sqlite3 data/discovery.db "DELETE FROM seen_candidates WHERE status IN ('"'"'rejected'"'"','"'"'error'"'"');"
  echo "Purged rejected/error rows"
'

for i in $(seq 1 "$MAX_PASSES"); do
  echo "" | tee -a "$LOG"
  echo "=== Backfill pass $i/$(date -Iseconds) ===" | tee -a "$LOG"
  docker compose run --rm -T \
    -e DISCOVERY_MAX_ANALYSES_PER_RUN=9999 \
    -e SLACK_BACKFILL_SUMMARY=true \
    -e CRAWLER_IGNORE_ROBOTS=false \
    scheduler python scripts/run_discovery.py 2>&1 | tee -a "$LOG"
  ANALYZED=$(grep -oE 'analyzed=[0-9]+' "$LOG" 2>/dev/null | tail -1 | cut -d= -f2 || echo "0")
  DISCOVERED=$(grep -oE 'discovered=[0-9]+' "$LOG" 2>/dev/null | tail -1 | cut -d= -f2 || echo "?")
  echo "Pass $i: discovered=${DISCOVERED:-?} analyzed=${ANALYZED:-?}" | tee -a "$LOG"
  if [ "${ANALYZED:-0}" = "0" ]; then
    echo "=== Backfill complete (no new analyses) $(date -Iseconds) ===" | tee -a "$LOG"
    break
  fi
  sleep 30
done

docker compose up -d scheduler
echo "=== Scheduler restarted $(date -Iseconds) ===" | tee -a "$LOG"
