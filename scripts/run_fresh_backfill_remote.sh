#!/bin/bash
# Fresh discovery backfill: backup Pending + seen_store, wipe Pending, reset seen_store, rerun.
#
# Usage on production host:
#   bash scripts/run_fresh_backfill_remote.sh
#   BACKUP_ONLY=1 bash scripts/run_fresh_backfill_remote.sh   # backup without clearing
#
set -euo pipefail

DEPLOY_PATH="${1:-/opt/policy-tracker}"
LOG="${DEPLOY_PATH}/data/fresh-backfill.log"
MAX_PASSES="${BACKFILL_MAX_PASSES:-50}"
BACKUP_ONLY="${BACKUP_ONLY:-0}"
SKIP_RESET="${SKIP_RESET:-0}"  # 1 = skip backup/clear/wipe; run backfill passes only
WIPE_SEEN="${WIPE_SEEN:-full}"  # full | reanalyze | rejected_only

cd "$DEPLOY_PATH"
mkdir -p data/backups

copy_volume_backup() {
  # Named Docker volume holds /app/data; mirror artifacts to host deploy tree.
  local pattern="$1"
  local name
  name="$(docker compose run --rm -T scheduler bash -lc "ls -t ${pattern} 2>/dev/null | head -1")"
  name="$(basename "$name")"
  if [ -z "$name" ] || [ "$name" = "." ]; then
    echo "No backup matched pattern: $pattern"
    return 1
  fi
  docker compose run --rm -T scheduler cat "/app/data/backups/${name}" > "data/backups/${name}"
  echo "Mirrored volume backup to data/backups/${name}"
}

echo "=== Fresh backfill started $(date -Iseconds) ===" | tee -a "$LOG"

docker compose stop scheduler || true

if [ "$SKIP_RESET" = "1" ]; then
  echo "SKIP_RESET=1 — running backfill passes only" | tee -a "$LOG"
else

echo "=== Backing up Pending table ===" | tee -a "$LOG"
docker compose run --rm -T scheduler python scripts/pending_snapshot.py backup \
  --output-dir data/backups 2>&1 | tee -a "$LOG"
copy_volume_backup "data/backups/pending-*.json" | tee -a "$LOG" || true

echo "=== Backing up seen_store ===" | tee -a "$LOG"
docker compose run --rm -T scheduler python - <<'PY' 2>&1 | tee -a "$LOG"
import os, shutil, sqlite3
from datetime import datetime, timezone

db = os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")
stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
if os.path.isfile(db):
    shutil.copy2(db, f"data/backups/discovery-{stamp}.db")
conn = sqlite3.connect(db)
cur = conn.cursor()
print("Seen store before reset:")
try:
    rows = cur.execute("SELECT status, COUNT(*) FROM seen_candidates GROUP BY status").fetchall()
    print(rows if rows else "(empty)")
except sqlite3.OperationalError as exc:
    print(f"(no seen_candidates table: {exc})")
conn.close()
PY
copy_volume_backup "data/backups/discovery-*.db" | tee -a "$LOG" || true

if [ "$BACKUP_ONLY" = "1" ]; then
  echo "BACKUP_ONLY=1 — skipping Pending clear and seen_store reset" | tee -a "$LOG"
  docker compose up -d scheduler
  exit 0
fi

echo "=== Clearing Pending table ===" | tee -a "$LOG"
docker compose run --rm -T scheduler python scripts/pending_snapshot.py clear --confirm \
  2>&1 | tee -a "$LOG"

echo "=== Resetting seen_store (WIPE_SEEN=$WIPE_SEEN) ===" | tee -a "$LOG"
docker compose run --rm -T scheduler python - <<PY 2>&1 | tee -a "$LOG"
import os, sqlite3

db = os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")
mode = "${WIPE_SEEN}"
conn = sqlite3.connect(db)
cur = conn.cursor()
if mode == "full":
    cur.execute("DELETE FROM seen_candidates")
    print("Wiped all seen_candidates rows")
elif mode == "reanalyze":
    cur.execute("DELETE FROM seen_candidates WHERE status IN ('pending','analyzed','rejected','error')")
    print("Purged pending/analyzed/rejected/error rows")
elif mode == "rejected_only":
    cur.execute("DELETE FROM seen_candidates WHERE status IN ('rejected','error')")
    print("Purged rejected/error rows only")
else:
    raise SystemExit(f"Unknown WIPE_SEEN={mode}")
conn.commit()
rows = cur.execute("SELECT status, COUNT(*) FROM seen_candidates GROUP BY status").fetchall()
print("After reset:", rows if rows else "(empty)")
conn.close()
PY

fi

for i in $(seq 1 "$MAX_PASSES"); do
  echo "" | tee -a "$LOG"
  echo "=== Fresh backfill pass $i/$(date -Iseconds) ===" | tee -a "$LOG"
  docker compose run --rm -T \
    -e DISCOVERY_MAX_ANALYSES_PER_RUN=9999 \
    -e SLACK_BACKFILL_SUMMARY=true \
    -e CRAWLER_IGNORE_ROBOTS=false \
    scheduler python scripts/run_discovery.py 2>&1 | tee -a "$LOG"
  ANALYZED=$(grep -oE 'analyzed=[0-9]+' "$LOG" 2>/dev/null | tail -1 | cut -d= -f2 || echo "0")
  DISCOVERED=$(grep -oE 'discovered=[0-9]+' "$LOG" 2>/dev/null | tail -1 | cut -d= -f2 || echo "?")
  echo "Pass $i: discovered=${DISCOVERED:-?} analyzed=${ANALYZED:-?}" | tee -a "$LOG"
  if [ "${ANALYZED:-0}" = "0" ]; then
    echo "=== Fresh backfill complete (no new analyses) $(date -Iseconds) ===" | tee -a "$LOG"
    break
  fi
  sleep 30
done

echo "=== Post-run Pending backup (for compare) ===" | tee -a "$LOG"
docker compose run --rm -T scheduler python scripts/pending_snapshot.py backup \
  --output-dir data/backups \
  --label "after-fresh-$(date +%Y%m%d-%H%M%S)" 2>&1 | tee -a "$LOG"
copy_volume_backup "data/backups/pending-after-fresh-*.json" | tee -a "$LOG" || true

docker compose up -d scheduler
echo "=== Scheduler restarted $(date -Iseconds) ===" | tee -a "$LOG"
echo "Compare snapshots: python scripts/pending_snapshot.py compare data/backups/pending-<before>.json data/backups/pending-after-fresh-<ts>.json" | tee -a "$LOG"
