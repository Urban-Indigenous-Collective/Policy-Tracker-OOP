#!/bin/bash
# Retry discovery for URLs that failed with error status in seen_store.
set -euo pipefail
cd /opt/policy-tracker
mkdir -p data

docker compose stop scheduler || true

echo "=== Clearing error rows from seen_store ==="
docker compose run --rm -T scheduler python - <<'PY'
import os
import sqlite3

db = os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM seen_candidates WHERE status='error'")
before = cur.fetchone()[0]
cur.execute("DELETE FROM seen_candidates WHERE status='error'")
conn.commit()
cur.execute("SELECT COUNT(*) FROM seen_candidates WHERE status='error'")
after = cur.fetchone()[0]
print(f"Cleared {before} error row(s); remaining errors: {after}")
conn.close()
PY

echo "=== Retry pass (errors only via cleared seen_store) ==="
docker compose run --rm -T \
  -e DISCOVERY_MAX_ANALYSES_PER_RUN=9999 \
  -e SLACK_BACKFILL_SUMMARY=true \
  scheduler python scripts/run_discovery.py 2>&1 | tee -a data/backfill-retry-errors.log

docker compose up -d scheduler
echo "=== Scheduler restarted ==="
