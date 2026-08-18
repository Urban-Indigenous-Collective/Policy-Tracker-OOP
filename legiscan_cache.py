"""Persistent SQLite cache for LegiScan list endpoints (session/master)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_cache_db_path() -> Path:
    db_path = Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))
    return db_path.parent / "legiscan_api_cache.db"


class LegiScanCache:
    """TTL cache for getSessionList / getMasterList / getMasterListRaw responses."""

    TTL_SECONDS = {
        "getSessionList": 7 * 24 * 3600,
        "getMasterList": 18 * 3600,
        "getMasterListRaw": 18 * 3600,
    }

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or default_cache_db_path())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS legiscan_api_cache (
                    op TEXT NOT NULL,
                    param_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (op, param_key)
                );
                """
            )

    def get(self, op: str, param_key: str) -> Optional[dict[str, Any]]:
        ttl = self.TTL_SECONDS.get(op)
        if ttl is None:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, fetched_at FROM legiscan_api_cache WHERE op = ? AND param_key = ?",
                (op, param_key),
            ).fetchone()
        if not row:
            return None
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - fetched_at
        if age > timedelta(seconds=ttl):
            return None
        try:
            return json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return None

    def set(self, op: str, param_key: str, payload: dict[str, Any]) -> None:
        if op not in self.TTL_SECONDS:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO legiscan_api_cache (op, param_key, payload_json, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(op, param_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    fetched_at = excluded.fetched_at
                """,
                (op, param_key, json.dumps(payload), _utc_now_iso()),
            )
