import json
import tempfile
from pathlib import Path

import pytest

from discovery.models import Candidate
from discovery.seen_store import SeenStore


@pytest.fixture
def store(tmp_path):
    return SeenStore(tmp_path / "test.db")


def test_seen_store_new_candidate(store):
    should, reason = store.should_process("https://example.com/bill/1")
    assert should is True
    assert reason == "new"


def test_seen_store_rejected_skipped(store):
    store.upsert(
        "https://example.com/bill/1",
        "legiscan",
        status="rejected",
        verdict="prescreen_fail",
    )
    should, reason = store.should_process("https://example.com/bill/1")
    assert should is False
    assert reason == "already_rejected"


def test_seen_store_change_hash_requeue(store):
    store.upsert(
        "https://example.com/bill/1",
        "legiscan",
        change_hash="abc123",
        status="discovered",
    )
    should, reason = store.should_process(
        "https://example.com/bill/1", change_hash="def456"
    )
    assert should is True
    assert reason == "change_hash_updated"


def test_seen_store_move_log(store):
    payload = {"Title": "Test Bill", "State": "NY"}
    log_id = store.log_move("pending_to_live", "https://example.com/bill/1", payload)
    assert log_id > 0


def test_seen_store_update_status(store):
    store.upsert("https://example.com/bill/1", "legiscan", status="pending")
    store.update_status("https://example.com/bill/1", "approved")
    row = store.get("https://example.com/bill/1")
    assert row["status"] == "approved"
