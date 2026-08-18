#!/usr/bin/env python3
"""Reset justice.gov federal_site seen_store rows for a clean DOJ re-run."""
import os
import sqlite3

db = os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")
conn = sqlite3.connect(db)
cur = conn.cursor()
for status in ("rejected", "error"):
    cur.execute(
        "SELECT COUNT(*) FROM seen_candidates "
        "WHERE instr(url, 'justice.gov') > 0 AND source='federal_site' AND status=?",
        (status,),
    )
    count = cur.fetchone()[0]
    cur.execute(
        "DELETE FROM seen_candidates "
        "WHERE instr(url, 'justice.gov') > 0 AND source='federal_site' AND status=?",
        (status,),
    )
    print(f"deleted {count} {status} justice.gov federal_site rows")
conn.commit()
conn.close()
