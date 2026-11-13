"""Persistent SQLite cache for fetched/decoded document text.

Separate from LLM analysis cache (cache/) and SeenStore metadata (discovery.db).
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from discovery.url_utils import normalize_url

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "data/document_text.db"

# Cache entries shorter than this are treated as bot-wall / empty shells and
# must not poison retries. Aligns with content_guard.HARD_MIN_DOC_CHARS.
MIN_USABLE_CACHE_CHARS = 40


def is_usable_cached_text(text: str, *, min_chars: int = MIN_USABLE_CACHE_CHARS) -> bool:
    """False for empty/whitespace/nbsp shells that should not be cache hits."""
    stripped = (text or "").replace("\xa0", " ").strip()
    return len(stripped) >= min_chars


def url_key(url: str) -> str:
    """Normalize a URL for cache lookup (dedup-friendly, lowercase)."""
    normalized = normalize_url(url)
    if normalized:
        return normalized.lower()
    return (url or "").strip().lower()


def content_hash(text: str) -> str:
    """SHA-256 hex digest of decoded text."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def infer_source_type(url: str) -> str:
    lower = (url or "").lower()
    if "legiscan.com" in lower:
        return "legiscan"
    if "federalregister.gov" in lower or "justice.gov" in lower:
        return "federal"
    if ".gov" in lower:
        return "gov"
    return "unknown"


def _env_enabled() -> bool:
    raw = os.getenv("DOCUMENT_TEXT_CACHE_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def default_db_path() -> Path:
    return Path(os.getenv("DOCUMENT_TEXT_DB_PATH", DEFAULT_DB_PATH))


class DocumentTextStore:
    """SQLite persistence for decoded document bodies keyed by normalized URL."""

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
                CREATE TABLE IF NOT EXISTS document_text (
                    url TEXT PRIMARY KEY,
                    decoded_text TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    char_len INTEGER NOT NULL,
                    bill_id TEXT,
                    doc_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_document_text_hash
                    ON document_text(content_hash);
                CREATE INDEX IF NOT EXISTS idx_document_text_fetched
                    ON document_text(fetched_at);
                """
            )

    def get(self, url: str) -> Optional[dict[str, Any]]:
        key = url_key(url)
        if not key:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM document_text WHERE url = ?", (key,)
            ).fetchone()
            return dict(row) if row else None

    def get_usable(self, url: str) -> Optional[dict[str, Any]]:
        """Return a cache row only when decoded text is long enough to be real content.

        Deletes poisoned short/empty shell rows so retries re-fetch instead of
        looping on ~12-char nbsp Akamai leftovers.
        """
        row = self.get(url)
        if not row:
            return None
        if is_usable_cached_text(row.get("decoded_text") or ""):
            return row
        logger.info(
            "Busting unusable document_text cache for %s (char_len=%s)",
            url_key(url)[:80],
            row.get("char_len"),
        )
        self.delete(url)
        return None

    def put(
        self,
        url: str,
        decoded_text: str,
        *,
        source_type: str = "",
        bill_id: str | None = None,
        doc_id: str | None = None,
    ) -> dict[str, Any]:
        key = url_key(url)
        if not key:
            raise ValueError("URL required for document text cache")
        text = decoded_text or ""
        if not is_usable_cached_text(text):
            # Never persist bot-wall shells; drop any prior poison for this URL.
            self.delete(url)
            logger.info(
                "Refusing to cache unusable document text for %s (%d chars)",
                key[:80],
                len(text),
            )
            return {
                "url": key,
                "decoded_text": text,
                "content_hash": content_hash(text),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source_type": source_type or infer_source_type(url),
                "char_len": len(text),
                "bill_id": str(bill_id) if bill_id else None,
                "doc_id": str(doc_id) if doc_id else None,
                "cached": False,
            }
        digest = content_hash(text)
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "url": key,
            "decoded_text": text,
            "content_hash": digest,
            "fetched_at": now,
            "source_type": source_type or infer_source_type(url),
            "char_len": len(text),
            "bill_id": str(bill_id) if bill_id else None,
            "doc_id": str(doc_id) if doc_id else None,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO document_text (
                    url, decoded_text, content_hash, fetched_at,
                    source_type, char_len, bill_id, doc_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    decoded_text = excluded.decoded_text,
                    content_hash = excluded.content_hash,
                    fetched_at = excluded.fetched_at,
                    source_type = excluded.source_type,
                    char_len = excluded.char_len,
                    bill_id = COALESCE(excluded.bill_id, document_text.bill_id),
                    doc_id = COALESCE(excluded.doc_id, document_text.doc_id)
                """,
                (
                    row["url"],
                    row["decoded_text"],
                    row["content_hash"],
                    row["fetched_at"],
                    row["source_type"],
                    row["char_len"],
                    row["bill_id"],
                    row["doc_id"],
                ),
            )
        logger.debug("Cached document text for %s (%d chars)", key[:80], row["char_len"])
        return row

    def delete(self, url: str) -> bool:
        key = url_key(url)
        if not key:
            return False
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM document_text WHERE url = ?", (key,))
            return cur.rowcount > 0


_store: DocumentTextStore | None | bool = False


def get_document_text_store() -> DocumentTextStore | None:
    """Return the shared store, or None when caching is disabled."""
    global _store
    if _store is False:
        if not _env_enabled():
            _store = None
        else:
            _store = DocumentTextStore(default_db_path())
    return _store


def reset_document_text_store() -> None:
    """Reset the module singleton (for tests)."""
    global _store
    _store = False
