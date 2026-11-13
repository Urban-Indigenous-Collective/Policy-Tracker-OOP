"""Tests for document_text_store and BillProcessor cache integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bill_processor import BillProcessor
from document_text_store import (
    DocumentTextStore,
    content_hash,
    get_document_text_store,
    infer_source_type,
    is_usable_cached_text,
    reset_document_text_store,
    url_key,
)
from discovery.seen_store import SeenStore


def test_url_key_normalizes_scheme_and_www():
    assert url_key("HTTP://WWW.Example.COM/bill/") == url_key("https://example.com/bill")


def test_content_hash_is_sha256_hex():
    digest = content_hash("hello")
    assert len(digest) == 64
    assert digest == content_hash("hello")
    assert digest != content_hash("world")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://legiscan.com/nm/bill/sb12/2022", "legiscan"),
        ("https://www.federalregister.gov/documents/2024/12345", "federal"),
        ("https://www.justice.gov/opa/pr/example", "federal"),
        ("https://legislature.utah.gov/bill/2024/HB001", "gov"),
    ],
)
def test_infer_source_type(url, expected):
    assert infer_source_type(url) == expected


def test_put_and_get_round_trip(tmp_path):
    store = DocumentTextStore(tmp_path / "doc_text.db")
    url = "https://legislature.utah.gov/bill/2024/HB001"
    text = "SECTION 1. Task force established for missing indigenous persons."
    store.put(url, text, source_type="gov", bill_id=None, doc_id=None)

    row = store.get(url)
    assert row is not None
    assert row["decoded_text"] == text
    assert row["content_hash"] == content_hash(text)
    assert row["char_len"] == len(text)
    assert row["source_type"] == "gov"
    assert row["fetched_at"]


def test_put_updates_existing_entry(tmp_path):
    store = DocumentTextStore(tmp_path / "doc_text.db")
    url = "https://example.gov/doc"
    store.put(url, "version one of the bill body with enough characters")
    store.put(url, "version two of the bill body with enough characters")

    row = store.get(url)
    assert row is not None
    assert row["decoded_text"] == "version two of the bill body with enough characters"
    assert row["content_hash"] == content_hash(
        "version two of the bill body with enough characters"
    )


def test_put_preserves_bill_id_when_not_provided(tmp_path):
    store = DocumentTextStore(tmp_path / "doc_text.db")
    url = "https://legiscan.com/nm/bill/sb12/2022"
    store.put(url, "text v1 with enough characters for cache keep", bill_id="123", doc_id="456")
    store.put(url, "text v2 with enough characters for cache keep")

    row = store.get(url)
    assert row["decoded_text"] == "text v2 with enough characters for cache keep"
    assert row["bill_id"] == "123"
    assert row["doc_id"] == "456"


def test_delete_removes_entry(tmp_path):
    store = DocumentTextStore(tmp_path / "doc_text.db")
    url = "https://example.gov/doc"
    store.put(url, "document body with enough characters to cache")
    assert store.delete(url) is True
    assert store.get(url) is None
    assert store.delete(url) is False


def test_is_usable_cached_text_rejects_nbsp_shell():
    assert is_usable_cached_text("   \xa0        ") is False
    assert is_usable_cached_text("") is False
    assert is_usable_cached_text("x" * 39) is False
    assert is_usable_cached_text("Missing and Murdered Indigenous Persons task force") is True


def test_put_refuses_bot_wall_shell(tmp_path):
    store = DocumentTextStore(tmp_path / "doc_text.db")
    url = "https://www.justice.gov/opa/pr/example"
    store.put(url, "real body that is long enough to keep in cache for retries")
    assert store.get(url) is not None

    result = store.put(url, "   \xa0        ")
    assert result.get("cached") is False
    assert store.get(url) is None


def test_get_usable_busts_short_shell(tmp_path):
    store = DocumentTextStore(tmp_path / "doc_text.db")
    url = "https://www.justice.gov/opa/pr/barr-strategy"
    # Bypass put() guard to simulate historically poisoned rows.
    with store._connect() as conn:
        conn.execute(
            "INSERT INTO document_text "
            "(url, decoded_text, content_hash, fetched_at, source_type, char_len) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url_key(url), "   \xa0        ", "deadbeef", "2026-08-01T00:00:00+00:00", "federal", 12),
        )
    assert store.get(url) is not None
    assert store.get_usable(url) is None
    assert store.get(url) is None


def test_get_document_text_store_respects_disabled(monkeypatch, tmp_path):
    reset_document_text_store()
    monkeypatch.setenv("DOCUMENT_TEXT_CACHE_ENABLED", "false")
    monkeypatch.setenv("DOCUMENT_TEXT_DB_PATH", str(tmp_path / "doc_text.db"))
    assert get_document_text_store() is None
    reset_document_text_store()


def test_get_document_text_store_uses_env_path(monkeypatch, tmp_path):
    reset_document_text_store()
    monkeypatch.setenv("DOCUMENT_TEXT_CACHE_ENABLED", "true")
    db_path = tmp_path / "custom_doc_text.db"
    monkeypatch.setenv("DOCUMENT_TEXT_DB_PATH", str(db_path))
    store = get_document_text_store()
    assert store is not None
    assert store.db_path == db_path
    reset_document_text_store()


@patch.object(BillProcessor, "_write_doc_text_cache")
@patch.object(BillProcessor, "_seen_content_hash", return_value=None)
def test_get_doc_text_busts_short_shell_and_refetches(_seen_hash, _write_cache, tmp_path, monkeypatch):
    reset_document_text_store()
    db_path = tmp_path / "doc_text.db"
    monkeypatch.setenv("DOCUMENT_TEXT_CACHE_ENABLED", "true")
    monkeypatch.setenv("DOCUMENT_TEXT_DB_PATH", str(db_path))

    url = "https://www.justice.gov/opa/pr/barr-strategy"
    store = DocumentTextStore(db_path)
    with store._connect() as conn:
        conn.execute(
            "INSERT INTO document_text "
            "(url, decoded_text, content_hash, fetched_at, source_type, char_len) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url_key(url), "   \xa0        ", "deadbeef", "2026-08-01T00:00:00+00:00", "federal", 12),
        )

    processor = BillProcessor(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    processor.gov_processor = MagicMock()
    processor.gov_processor.is_gov_url.return_value = True
    fresh = "Attorney General launches national strategy for missing and murdered indigenous persons."
    processor.gov_processor.get_gov_document_text.return_value = (fresh, None)

    ok, msg = processor.get_doc_text(url)
    assert ok is True
    assert "cache" not in msg.lower()
    assert processor.compiled_bill["decoded_text"] == fresh
    processor.gov_processor.get_gov_document_text.assert_called_once_with(url)
    assert store.get(url) is None  # poison deleted; write mocked so no new row
    reset_document_text_store()


@patch.object(BillProcessor, "_write_doc_text_cache")
@patch.object(BillProcessor, "_seen_content_hash", return_value=None)
def test_get_doc_text_returns_cache_on_hit(_seen_hash, _write_cache, tmp_path, monkeypatch):
    reset_document_text_store()
    db_path = tmp_path / "doc_text.db"
    monkeypatch.setenv("DOCUMENT_TEXT_CACHE_ENABLED", "true")
    monkeypatch.setenv("DOCUMENT_TEXT_DB_PATH", str(db_path))

    url = "https://legislature.utah.gov/bill/2024/HB001"
    cached = "Cached bill body with enough characters for usable cache"
    DocumentTextStore(db_path).put(url, cached, source_type="gov")

    processor = BillProcessor(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    processor.gov_processor = MagicMock()
    processor.gov_processor.is_gov_url.return_value = True
    processor.gov_processor.get_gov_document_text = MagicMock(
        return_value=("Fresh body with enough characters after refetch path", None)
    )

    ok, msg = processor.get_doc_text(url)
    assert ok is True
    assert "cache" in msg.lower()
    assert processor.compiled_bill["decoded_text"] == cached
    processor.gov_processor.get_gov_document_text.assert_not_called()
    reset_document_text_store()


@patch.object(BillProcessor, "_write_doc_text_cache")
def test_get_doc_text_refresh_bypasses_cache(_write_cache, tmp_path, monkeypatch):
    reset_document_text_store()
    db_path = tmp_path / "doc_text.db"
    monkeypatch.setenv("DOCUMENT_TEXT_CACHE_ENABLED", "true")
    monkeypatch.setenv("DOCUMENT_TEXT_DB_PATH", str(db_path))

    url = "https://legislature.utah.gov/bill/2024/HB001"
    DocumentTextStore(db_path).put(
        url, "Cached bill body with enough characters for usable cache", source_type="gov"
    )

    processor = BillProcessor(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    processor.gov_processor = MagicMock()
    processor.gov_processor.is_gov_url.return_value = True
    fresh = "Fresh body with enough characters after refetch path"
    processor.gov_processor.get_gov_document_text.return_value = (fresh, None)

    ok, _msg = processor.get_doc_text(url, refresh=True)
    assert ok is True
    assert processor.compiled_bill["decoded_text"] == fresh
    processor.gov_processor.get_gov_document_text.assert_called_once_with(url)
    reset_document_text_store()


@patch.object(BillProcessor, "_write_doc_text_cache")
def test_get_doc_text_stale_seen_hash_refetches(_write_cache, tmp_path, monkeypatch):
    reset_document_text_store()
    doc_db = tmp_path / "doc_text.db"
    seen_db = tmp_path / "seen.db"
    monkeypatch.setenv("DOCUMENT_TEXT_CACHE_ENABLED", "true")
    monkeypatch.setenv("DOCUMENT_TEXT_DB_PATH", str(doc_db))
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(seen_db))

    url = "https://legislature.utah.gov/bill/2024/HB001"
    DocumentTextStore(doc_db).put(
        url, "Cached bill body with enough characters for usable cache", source_type="gov"
    )
    seen = SeenStore(seen_db)
    seen.upsert(
        url,
        source="state_site",
        content_hash=content_hash("Different body with enough characters for hash"),
    )

    processor = BillProcessor(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    processor.gov_processor = MagicMock()
    processor.gov_processor.is_gov_url.return_value = True
    fresh = "Fresh body with enough characters after refetch path"
    processor.gov_processor.get_gov_document_text.return_value = (fresh, None)

    ok, _msg = processor.get_doc_text(url)
    assert ok is True
    assert processor.compiled_bill["decoded_text"] == fresh
    processor.gov_processor.get_gov_document_text.assert_called_once()
    reset_document_text_store()


@patch("bill_processor.get_document_text_store")
def test_get_doc_text_writes_cache_after_fetch(mock_get_store, tmp_path):
    store = DocumentTextStore(tmp_path / "doc_text.db")
    mock_get_store.return_value = store

    processor = BillProcessor(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    processor.gov_processor = MagicMock()
    processor.gov_processor.is_gov_url.return_value = True
    fetched = "Fetched body with enough characters to persist in cache"
    processor.gov_processor.get_gov_document_text.return_value = (fetched, None)

    url = "https://legislature.utah.gov/bill/2024/HB001"
    ok, _msg = processor.get_doc_text(url)
    assert ok is True

    row = store.get(url)
    assert row is not None
    assert row["decoded_text"] == fetched
