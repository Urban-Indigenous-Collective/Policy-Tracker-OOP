import json

from public_api.policy_freshness import last_successful_status_refresh_at


def test_last_successful_status_refresh_skips_errored_runs(tmp_path, monkeypatch):
    log = tmp_path / "status_refresh_runs.jsonl"
    log.write_text(
        json.dumps({"run_at": "2026-10-20T06:00:00+00:00", "errors": ["boom"]})
        + "\n"
        + json.dumps({"run_at": "2026-10-21T06:00:00+00:00", "errors": []})
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))

    result = last_successful_status_refresh_at()
    assert result is not None
    assert result.isoformat().startswith("2026-10-21")
