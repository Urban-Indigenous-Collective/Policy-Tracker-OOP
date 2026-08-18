#!/bin/bash
cd /opt/policy-tracker
docker compose run --rm -T scheduler python - <<'PY'
import os, sqlite3
db=os.getenv("DISCOVERY_DB_PATH","data/discovery.db")
conn=sqlite3.connect(db)
print("=== by source + status ===")
for row in conn.execute("SELECT source, status, COUNT(*) FROM seen_candidates GROUP BY source, status ORDER BY source, status"):
    print(f"  {row[0]:12} {row[1]:10} {row[2]}")
print("\n=== state_site analyzed/pending (if any) ===")
rows=list(conn.execute("SELECT url, state, status FROM seen_candidates WHERE source='state_site' AND status IN ('analyzed','pending') LIMIT 10"))
print(f"  count={len(rows)}")
for r in rows: print(f"  {r}")
PY
