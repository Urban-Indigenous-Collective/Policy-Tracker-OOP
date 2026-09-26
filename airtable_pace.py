"""Cross-process spacing for Airtable API calls.

The web and scheduler containers share the discovery_data volume, so a
timestamp in SQLite guarded by a FileLock keeps their combined traffic under
Airtable's ~5 req/s per-base limit. This prevents 429 bursts; it does not
reduce how many calls count toward the monthly billing cap.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from filelock import FileLock


def pace_enabled() -> bool:
    return os.getenv("AIRTABLE_PACE_ENABLED", "true").lower() in ("1", "true", "yes")


def min_interval() -> float:
    return float(os.getenv("AIRTABLE_MIN_INTERVAL_SEC", "0.21"))


def pace_db_path() -> Path:
    db_path = Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))
    return db_path.parent / "airtable_pace.db"


def wait_turn(db_path: Path | None = None, interval: float | None = None) -> None:
    """Block until at least `interval` seconds have passed since the last Airtable call."""
    path = db_path or pace_db_path()
    gap = min_interval() if interval is None else interval
    path.parent.mkdir(parents=True, exist_ok=True)
    # The lock is held through the sleep so a waiting process cannot claim the same slot.
    with FileLock(str(path.with_suffix(".lock"))):
        conn = sqlite3.connect(path)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS pace (id INTEGER PRIMARY KEY CHECK (id = 1), last REAL)")
            row = conn.execute("SELECT last FROM pace WHERE id = 1").fetchone()
            if row:
                remaining = gap - (time.time() - row[0])
                if remaining > 0:
                    time.sleep(remaining)
            conn.execute("INSERT OR REPLACE INTO pace (id, last) VALUES (1, ?)", (time.time(),))
            conn.commit()
        finally:
            conn.close()
