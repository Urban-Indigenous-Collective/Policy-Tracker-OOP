#!/usr/bin/env python3
import os
import sqlite3

db = os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")
conn = sqlite3.connect(db)
print("=== by source + status ===")
for row in conn.execute(
    "SELECT source, status, COUNT(*) FROM seen_candidates "
    "GROUP BY source, status ORDER BY source, status"
):
    print(f"  {row[0]:12} {row[1]:10} {row[2]}")
print("\n=== sample state_site analyzed ===")
for row in conn.execute(
    "SELECT url, state, status FROM seen_candidates "
    "WHERE source='state_site' AND status IN ('analyzed','pending') LIMIT 10"
):
    print(f"  {row}")
conn.close()
