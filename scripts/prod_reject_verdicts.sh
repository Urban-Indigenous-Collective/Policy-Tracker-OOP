#!/bin/bash
cd /opt/policy-tracker
docker compose run --rm -T scheduler python - <<'PY'
import os
import sqlite3
from collections import Counter

from discovery.seen_store import canonical_source

c = sqlite3.connect(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))
rows = c.execute(
    "SELECT source, verdict FROM seen_candidates WHERE status='rejected'"
).fetchall()
by_source: dict[str, Counter] = {}
for source, verdict in rows:
    key = canonical_source(source or "")
    if key not in ("state_site", "legiscan", "federal_site"):
        key = key or "(empty)"
    by_source.setdefault(key, Counter())[verdict or "(null)"] += 1

for label in ("state_site", "legiscan", "federal_site"):
    counts = by_source.get(label)
    print(f"\n{label} reject verdicts:")
    if not counts:
        print("  (none)")
        continue
    for verdict, n in counts.most_common():
        print(f"  {verdict}: {n}")

other = {k: v for k, v in by_source.items() if k not in ("state_site", "legiscan", "federal_site")}
if other:
    print("\nother source labels:")
    for label, counts in sorted(other.items()):
        print(f"  {label}:")
        for verdict, n in counts.most_common():
            print(f"    {verdict}: {n}")
PY
