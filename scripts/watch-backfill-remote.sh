#!/bin/bash
# Run on production (WSL) — stream backfill logs or show progress bar.
set -euo pipefail
cd /opt/policy-tracker

MODE="${1:---progress}"
CID=$(docker ps -q --filter name=policy-tracker-scheduler-run | head -1)

if [ -z "$CID" ]; then
  if [ -f data/backfill-loop.log ]; then
    echo "Following data/backfill-loop.log"
    exec tail -f data/backfill-loop.log
  fi
  echo "No active backfill container or log file."
  docker ps --filter name=policy-tracker
  exit 1
fi

if [ "$MODE" = "--plain" ]; then
  echo "Following active discovery container: $CID"
  exec docker logs -f --tail 50 "$CID"
fi

echo "Progress for container: $CID"
exec python3 scripts/watch_backfill_progress.py --container "$CID" --interval 2
