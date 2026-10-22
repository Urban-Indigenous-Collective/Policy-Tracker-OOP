"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_discovery_data_path(tmp_path, monkeypatch):
    """Never write pending_slack_report.json or discovery.db into repo data/ or prod mounts."""
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
