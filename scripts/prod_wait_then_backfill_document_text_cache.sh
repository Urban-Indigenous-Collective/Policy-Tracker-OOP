#!/bin/bash
# Wait for tonight's nightly pipeline status refresh step to finish, then backfill cache.
set -euo pipefail
cd /opt/policy-tracker

LOG="${1:-data/backfill_document_text_cache.log}"
TZ="${DISCOVERY_TZ:-America/New_York}"

echo "$(date) prod_wait_then_backfill: tz=$TZ (status refresh runs inside nightly pipeline)" | tee -a "$LOG"

wait_for_status_refresh_done() {
  local saw_start=0
  local deadline=$(( $(date +%s) + 7200 ))  # 2h max wait
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if docker compose logs --no-color scheduler 2>&1 | tail -400 | grep -q "status refresh — starting"; then
      saw_start=1
      echo "$(date) status refresh started — waiting for finish" | tee -a "$LOG"
    fi
    if [ "$saw_start" -eq 1 ]; then
      if docker compose logs --no-color scheduler 2>&1 | tail -400 | grep -q "Status refresh finished:"; then
        echo "$(date) status refresh finished" | tee -a "$LOG"
        return 0
      fi
    else
      # After 4:00 AM ET, if no start logged tonight, assume idle/skipped
      local now_et
      now_et="$(TZ="$TZ" date +%H%M)"
      if [ "$now_et" -ge 0400 ]; then
        echo "$(date) no status refresh start seen after 04:00 ET; proceeding" | tee -a "$LOG"
        return 0
      fi
    fi
    sleep 30
  done
  echo "$(date) ERROR: timed out waiting for status refresh" | tee -a "$LOG"
  return 1
}

# If we're before 2:55 AM ET, sleep until just before the nightly pipeline
now_et="$(TZ="$TZ" date +%H%M)"
if [ "$now_et" -lt 0255 ]; then
  echo "$(date) waiting until 02:55 ET before polling nightly pipeline" | tee -a "$LOG"
  while [ "$(TZ="$TZ" date +%H%M)" -lt 0255 ]; do
    sleep 20
  done
fi

wait_for_status_refresh_done

echo "$(date) starting document text cache backfill" | tee -a "$LOG"
nohup docker compose exec -T scheduler python scripts/backfill_document_text_cache.py >> "$LOG" 2>&1 &
echo "document_text backfill pid=$! log=$LOG"
