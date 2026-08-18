import json
import sqlite3
from pathlib import Path
from typing import Any, Optional


VALID_STATUSES = frozenset(
    {"discovered", "rejected", "analyzed", "pending", "approved", "error"}
)


class SeenStore:
    """SQLite persistence for discovery candidates and Airtable move audit log."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
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
                CREATE TABLE IF NOT EXISTS seen_candidates (
                    url TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    state TEXT,
                    external_id TEXT,
                    session_id TEXT,
                    change_hash TEXT,
                    content_hash TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    verdict TEXT,
                    confidence REAL,
                    status TEXT NOT NULL DEFAULT 'discovered'
                );
                CREATE INDEX IF NOT EXISTS idx_seen_status ON seen_candidates(status);
                CREATE INDEX IF NOT EXISTS idx_seen_external ON seen_candidates(external_id);

                CREATE TABLE IF NOT EXISTS move_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    direction TEXT NOT NULL,
                    url TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    moved_at TEXT NOT NULL
                );
                """
            )
            self._ensure_session_id_column(conn)

    def _ensure_session_id_column(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(seen_candidates)")}
        if "session_id" not in cols:
            conn.execute("ALTER TABLE seen_candidates ADD COLUMN session_id TEXT")

    def get(self, url: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM seen_candidates WHERE url = ?", (url.strip().lower(),)
            ).fetchone()
            return dict(row) if row else None

    def get_by_state_bill(self, state: str, bill_number: str) -> Optional[dict[str, Any]]:
        """Find a seen row with external_id matching state and normalized bill number."""
        from legiscan_processor import normalize_bill_number, parse_legiscan_bill_url

        state_key = (state or "").strip().upper()
        target = normalize_bill_number(bill_number)
        if not state_key or not target:
            return None
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM seen_candidates
                WHERE upper(state) = ? AND external_id IS NOT NULL AND external_id != ''
                """,
                (state_key,),
            ).fetchall()
        for row in rows:
            record = dict(row)
            parsed = parse_legiscan_bill_url(record.get("url") or "")
            if parsed:
                _, url_bill, _ = parsed
                if normalize_bill_number(url_bill) == target:
                    return record
            if target in normalize_bill_number(record.get("url") or ""):
                return record
        return None

    def should_process(
        self,
        url: str,
        change_hash: str = "",
        content_hash: str = "",
    ) -> tuple[bool, str]:
        """Return (should_process, reason)."""
        existing = self.get(url)
        if not existing:
            return True, "new"
        status = existing.get("status", "")
        if status in ("rejected", "approved"):
            return False, f"already_{status}"
        if status in ("pending", "analyzed"):
            return False, f"already_{status}"
        if change_hash and existing.get("change_hash") and change_hash != existing.get("change_hash"):
            return True, "change_hash_updated"
        if content_hash and existing.get("content_hash") and content_hash != existing.get("content_hash"):
            return True, "content_hash_updated"
        return False, "already_seen"

    def upsert(
        self,
        url: str,
        source: str,
        state: str = "",
        external_id: str = "",
        session_id: str = "",
        change_hash: str = "",
        content_hash: str = "",
        verdict: str = "",
        confidence: float | None = None,
        status: str = "discovered",
    ) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        url_key = url.strip().lower()
        from discovery.models import utc_now_iso

        now = utc_now_iso()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT url FROM seen_candidates WHERE url = ?", (url_key,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE seen_candidates SET
                        source = ?, state = ?, external_id = ?,
                        session_id = COALESCE(NULLIF(?, ''), session_id),
                        change_hash = ?,
                        content_hash = ?, last_seen = ?, verdict = COALESCE(?, verdict),
                        confidence = COALESCE(?, confidence), status = ?
                    WHERE url = ?
                    """,
                    (
                        source,
                        state,
                        external_id,
                        session_id or None,
                        change_hash,
                        content_hash,
                        now,
                        verdict or None,
                        confidence,
                        status,
                        url_key,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO seen_candidates (
                        url, source, state, external_id, session_id, change_hash, content_hash,
                        first_seen, last_seen, verdict, confidence, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        url_key,
                        source,
                        state,
                        external_id,
                        session_id or None,
                        change_hash,
                        content_hash,
                        now,
                        now,
                        verdict or None,
                        confidence,
                        status,
                    ),
                )

    def update_metadata(
        self,
        url: str,
        external_id: str = "",
        session_id: str = "",
        change_hash: str = "",
    ) -> None:
        """Update LegiScan identifiers without changing workflow status."""
        from discovery.models import utc_now_iso

        url_key = url.strip().lower()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE seen_candidates SET
                    external_id = COALESCE(NULLIF(?, ''), external_id),
                    session_id = COALESCE(NULLIF(?, ''), session_id),
                    change_hash = COALESCE(NULLIF(?, ''), change_hash),
                    last_seen = ?
                WHERE url = ?
                """,
                (external_id, session_id, change_hash, utc_now_iso(), url_key),
            )

    def update_status(self, url: str, status: str, verdict: str = "") -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        from discovery.models import utc_now_iso

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE seen_candidates SET status = ?, verdict = COALESCE(?, verdict),
                last_seen = ? WHERE url = ?
                """,
                (status, verdict or None, utc_now_iso(), url.strip().lower()),
            )

    def log_move(self, direction: str, url: str, payload: dict[str, Any]) -> int:
        from discovery.models import utc_now_iso

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO move_log (direction, url, payload_json, moved_at)
                VALUES (?, ?, ?, ?)
                """,
                (direction, url, json.dumps(payload, default=str), utc_now_iso()),
            )
            return cursor.lastrowid or 0
