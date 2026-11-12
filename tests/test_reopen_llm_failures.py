"""reopen_llm_failures writes a full audit before dry-run/apply deletes."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from discovery.seen_store import SeenStore
from scripts.reopen_llm_failures import reopen_llm_failures


def _seed(store: SeenStore) -> None:
    store.upsert(
        "https://example.com/llm-error-1",
        "legiscan",
        state="NM",
        status="rejected",
        verdict="llm_error",
        confidence=0.0,
    )
    store.upsert(
        "https://example.com/llm-fail-2",
        "federal_site",
        state="National",
        status="rejected",
        verdict="llm_fail",
        confidence=0.1,
    )
    store.upsert(
        "https://example.com/error-3",
        "state_site",
        state="AZ",
        status="error",
        verdict="RuntimeError: boom",
    )
    store.upsert(
        "https://example.com/genuine-reject",
        "legiscan",
        state="NM",
        status="rejected",
        verdict="llm",
        confidence=0.9,
    )


def test_dry_run_writes_full_audit_without_delete(tmp_path: Path):
    db_path = tmp_path / "discovery.db"
    audit_dir = tmp_path / "backups"
    store = SeenStore(db_path)
    _seed(store)

    summary = reopen_llm_failures(
        db_path=db_path,
        apply=False,
        audit_dir=audit_dir,
        list_all_urls=True,
    )

    assert summary["mode"] == "dry-run"
    assert summary["matched"] == 3
    assert summary["deleted"] == 0
    audit_path = Path(summary["audit_path"])
    assert audit_path.is_file()
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert payload["matched"] == 3
    assert len(payload["rows"]) == 3
    assert len(payload["urls"]) == 3
    urls = set(payload["urls"])
    assert "https://example.com/llm-error-1" in urls
    assert "https://example.com/llm-fail-2" in urls
    assert "https://example.com/error-3" in urls
    assert "https://example.com/genuine-reject" not in urls
    # Full row fields preserved for recovery
    by_url = {row["url"]: row for row in payload["rows"]}
    assert by_url["https://example.com/llm-error-1"]["verdict"] == "llm_error"
    assert by_url["https://example.com/llm-error-1"]["status"] == "rejected"
    assert by_url["https://example.com/llm-error-1"]["last_seen"]
    assert store.get("https://example.com/llm-error-1") is not None


def test_apply_writes_audit_and_db_backup_then_deletes(tmp_path: Path):
    db_path = tmp_path / "discovery.db"
    audit_dir = tmp_path / "backups"
    store = SeenStore(db_path)
    _seed(store)

    summary = reopen_llm_failures(
        db_path=db_path,
        apply=True,
        audit_dir=audit_dir,
        db_backup=True,
        list_all_urls=True,
    )

    assert summary["mode"] == "apply"
    assert summary["matched"] == 3
    assert summary["deleted"] == 3
    audit_path = Path(summary["audit_path"])
    assert audit_path.is_file()
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert payload["matched"] == 3
    assert len(payload["rows"]) == 3

    backup = Path(summary["db_backup_path"])
    assert backup.is_file()
    # Backup still has the pre-delete rows
    with sqlite3.connect(backup) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM seen_candidates WHERE verdict IN ('llm_error','llm_fail') OR status='error'"
        ).fetchone()[0]
    assert count == 3

    assert store.get("https://example.com/llm-error-1") is None
    assert store.get("https://example.com/llm-fail-2") is None
    assert store.get("https://example.com/error-3") is None
    # Genuine not-MMIP reject untouched
    assert store.get("https://example.com/genuine-reject") is not None


def test_no_error_status_skips_error_rows(tmp_path: Path):
    db_path = tmp_path / "discovery.db"
    audit_dir = tmp_path / "backups"
    store = SeenStore(db_path)
    _seed(store)

    summary = reopen_llm_failures(
        db_path=db_path,
        apply=True,
        include_error_status=False,
        audit_dir=audit_dir,
        db_backup=False,
    )

    assert summary["matched"] == 2
    assert summary["deleted"] == 2
    assert store.get("https://example.com/error-3") is not None
    payload = json.loads(Path(summary["audit_path"]).read_text(encoding="utf-8"))
    assert set(payload["urls"]) == {
        "https://example.com/llm-error-1",
        "https://example.com/llm-fail-2",
    }


def test_errors_only_matches_status_error(tmp_path: Path):
    db_path = tmp_path / "discovery.db"
    audit_dir = tmp_path / "backups"
    store = SeenStore(db_path)
    _seed(store)

    summary = reopen_llm_failures(
        db_path=db_path,
        apply=False,
        errors_only=True,
        audit_dir=audit_dir,
    )

    assert summary["matched"] == 1
    payload = json.loads(Path(summary["audit_path"]).read_text(encoding="utf-8"))
    assert payload["urls"] == ["https://example.com/error-3"]
