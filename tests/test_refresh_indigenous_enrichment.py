"""Post-refresh ethnicity enrichment wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import scheduler
from scripts import refresh_indigenous_db


def test_cmd_refresh_calls_post_refresh_enrichment():
    mock_db = MagicMock()
    mock_db.refresh.return_value = {
        "count": 600,
        "built_at": "2026-08-05T00:00:00Z",
        "backup_path": "/tmp/backup.json",
        "path": "/tmp/roster.json",
    }
    mock_enrich = MagicMock(
        return_value={"skipped": False, "targets": 10, "accepted": 2, "applied": 2}
    )
    args = MagicMock(path="/tmp/roster.json", backup_dir="/tmp/backups", min_count=None)

    with patch.object(refresh_indigenous_db, "IndigenousDatabase", return_value=mock_db):
        with patch.object(refresh_indigenous_db.Path, "is_file", return_value=False):
            with patch.object(
                refresh_indigenous_db,
                "run_post_refresh_enrichment",
                mock_enrich,
            ):
                rc = refresh_indigenous_db.cmd_refresh(args)

    assert rc == 0
    mock_db.refresh.assert_called_once_with(min_count=None)
    mock_enrich.assert_called_once_with(db_path="/tmp/roster.json")


def test_cmd_dedupe_only_calls_post_refresh_enrichment():
    mock_db = MagicMock()
    mock_db.dedupe_disk_cache.return_value = {
        "before": 610,
        "after": 600,
        "backup_path": "/tmp/backup.json",
        "path": "/tmp/roster.json",
    }
    mock_enrich = MagicMock(return_value={"skipped": True, "reason": "disabled"})
    args = MagicMock(path="/tmp/roster.json", backup_dir="/tmp/backups")

    with patch.object(refresh_indigenous_db, "IndigenousDatabase", return_value=mock_db):
        with patch.object(
            refresh_indigenous_db,
            "run_post_refresh_enrichment",
            mock_enrich,
        ):
            rc = refresh_indigenous_db.cmd_dedupe_only(args)

    assert rc == 0
    mock_db.dedupe_disk_cache.assert_called_once()
    mock_enrich.assert_called_once_with(db_path="/tmp/roster.json")


def test_run_indigenous_roster_refresh_job_calls_enrichment():
    mock_db = MagicMock()
    mock_db.db_path = "/data/roster.json"
    mock_db.refresh.return_value = {
        "count": 600,
        "built_at": "2026-08-05T00:00:00Z",
        "backup_path": "/tmp/backup.json",
    }
    mock_app = MagicMock()
    mock_app.indigenous_db.reload_if_stale.return_value = True
    mock_enrich = MagicMock(
        return_value={"skipped": False, "targets": 5, "accepted": 1, "applied": 1}
    )

    with patch.object(scheduler, "IndigenousDatabase", return_value=mock_db):
        with patch.object(scheduler, "get_main_app", return_value=mock_app):
            with patch.object(scheduler, "SlackNotifier"):
                with patch(
                    "scripts.enrich_indigenous_ethnicity.run_post_refresh_enrichment",
                    mock_enrich,
                ):
                    scheduler.run_indigenous_roster_refresh_job()

    mock_db.refresh.assert_called_once()
    mock_enrich.assert_called_once_with(db_path="/data/roster.json")
    mock_app.indigenous_db.reload_if_stale.assert_called_once()


def test_run_post_refresh_enrichment_skips_when_disabled(monkeypatch):
    from scripts.enrich_indigenous_ethnicity import run_post_refresh_enrichment

    monkeypatch.delenv("INDIGENOUS_ETHNICITY_ENRICH_ON_REFRESH", raising=False)
    stats = run_post_refresh_enrichment(enrich_enabled=False)
    assert stats == {"skipped": True, "reason": "disabled"}
