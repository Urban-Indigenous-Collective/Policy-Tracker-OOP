import multiprocessing
import time
from unittest.mock import patch

import airtable_pace
from airtable_client import PacedApi


def _worker(db_path, interval, count, out):
    for _ in range(count):
        airtable_pace.wait_turn(db_path=db_path, interval=interval)
        out.put(time.time())


def test_wait_turn_spaces_calls_across_processes(tmp_path):
    db_path = tmp_path / "airtable_pace.db"
    interval = 0.1
    out = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(target=_worker, args=(db_path, interval, 3, out))
        for _ in range(2)
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=10)

    stamps = sorted(out.get(timeout=1) for _ in range(6))
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert min(gaps) >= interval * 0.9


def test_paced_api_waits_before_every_request(monkeypatch):
    monkeypatch.setenv("AIRTABLE_PACE_ENABLED", "true")
    api = PacedApi("key")
    with patch.object(airtable_pace, "wait_turn") as mock_wait, patch(
        "pyairtable.Api.request", return_value={"ok": True}
    ):
        api.request("GET", "https://api.airtable.com/v0/app/tbl")
        api.request("PATCH", "https://api.airtable.com/v0/app/tbl/rec", json={})
    assert mock_wait.call_count == 2


def test_paced_api_skips_pacing_when_disabled(monkeypatch):
    monkeypatch.setenv("AIRTABLE_PACE_ENABLED", "false")
    api = PacedApi("key")
    with patch.object(airtable_pace, "wait_turn") as mock_wait, patch(
        "pyairtable.Api.request", return_value={}
    ):
        api.request("GET", "https://api.airtable.com/v0/app/tbl")
    mock_wait.assert_not_called()
