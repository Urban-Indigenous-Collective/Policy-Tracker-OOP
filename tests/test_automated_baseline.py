"""Creation-time automated baseline: capture, never-raise, and automated-vs-corrected diffs."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import automated_baseline as ab
from airtable_client import AirtableClient

URL = "https://legiscan.com/NM/bill/HB1/2024"


def _fields(**overrides):
    base = {
        "Name": "Task force",
        "State": "NM",
        "Bill Number": "HB1",
        "Bill Overview (Link)": URL,
        "Summary": "Automated summary.",
        "UIC Pros": "1. Pro one\n2. Pro two",
        "Gender Inclusive Language": "Yes.",
        "Review Status": "Pending Review",
        "Progression": "Introduced",
    }
    base.update(overrides)
    return base


def _baseline_files(directory):
    return sorted(directory.glob("pending-created-*.jsonl"))


def test_baseline_dir_defaults_beside_discovery_db(monkeypatch, tmp_path):
    monkeypatch.delenv("AUTOMATED_BASELINE_DIR", raising=False)
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "sub" / "discovery.db"))
    assert ab.baseline_dir() == tmp_path / "sub" / "automated_baseline"


def test_record_pending_creation_appends_automated_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOMATED_BASELINE_DIR", str(tmp_path / "bl"))
    monkeypatch.setenv("LLM_MODEL", "qwen-test")
    created = {"id": "recAAA", "createdTime": "2026-11-19T12:00:00.000Z", "fields": _fields()}

    path = ab.record_pending_creation(
        created, {"Summary": "ignored"}, source="LegiScan", relevance_confidence=0.9, discovered_on="2026-11-19"
    )

    assert path is not None and path.parent == tmp_path / "bl"
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["kind"] == "creation"
    assert entry["record_id"] == "recAAA"
    assert entry["identity"].startswith("url:")
    assert entry["fields"]["Summary"] == "Automated summary."
    assert entry["llm_model"] == "qwen-test"
    assert entry["prompt_version"]
    assert entry["pipeline_source"] == "LegiScan"
    assert entry["airtable_created_time"] == "2026-11-19T12:00:00.000Z"


def test_record_pending_creation_falls_back_to_sent_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOMATED_BASELINE_DIR", str(tmp_path / "bl"))
    path = ab.record_pending_creation({"id": "recB"}, _fields(Summary="from sent"))
    assert json.loads(path.read_text())["fields"]["Summary"] == "from sent"


def test_record_pending_creation_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOMATED_BASELINE_DIR", str(tmp_path / "bl"))
    monkeypatch.setenv("AUTOMATED_BASELINE_ENABLED", "false")
    assert ab.record_pending_creation({"id": "recC", "fields": _fields()}) is None
    assert not (tmp_path / "bl").exists()


def test_record_pending_creation_never_raises(monkeypatch, tmp_path):
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("file in the way")
    monkeypatch.setenv("AUTOMATED_BASELINE_DIR", str(blocker / "child"))
    assert ab.record_pending_creation({"id": "recD", "fields": _fields()}) is None


def test_load_baseline_first_entry_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOMATED_BASELINE_DIR", str(tmp_path / "bl"))
    ab.record_pending_creation({"id": "rec1", "fields": _fields(Summary="original")})
    ab.record_pending_creation({"id": "rec2", "fields": _fields(Summary="rediscovered")})

    baseline = ab.load_baseline()

    assert len(baseline) == 1
    assert next(iter(baseline.values()))["fields"]["Summary"] == "original"


def test_load_baseline_skips_corrupt_lines(monkeypatch, tmp_path):
    directory = tmp_path / "bl"
    monkeypatch.setenv("AUTOMATED_BASELINE_DIR", str(directory))
    path = ab.record_pending_creation({"id": "rec1", "fields": _fields()})
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("{truncated\n")
    assert len(ab.load_baseline()) == 1


def _stub_client(created_holder):
    client = AirtableClient.__new__(AirtableClient)
    client.pending_table = MagicMock()

    def fake_create(table, fields):
        record = {"id": "recNEW", "createdTime": "2026-11-19T12:00:00.000Z", "fields": dict(fields)}
        created_holder["record"] = record
        return record

    client.create_record = fake_create
    return client


def test_create_pending_record_writes_baseline(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOMATED_BASELINE_DIR", str(tmp_path / "bl"))
    holder: dict = {}
    client = _stub_client(holder)

    result = client.create_pending_record(
        bill_data={
            "State": "NM",
            "Name": "Task force",
            "Bill Number": "HB1",
            "Bill Overview (Link)": URL,
            "Summary": "Automated summary.",
        },
        source="LegiScan",
        relevance_confidence=0.88,
        relevance_rationale="MMIP",
        discovered_on="2026-11-19",
    )

    assert result is holder["record"]
    entries = list(ab.iter_entries(tmp_path / "bl"))
    assert len(entries) == 1
    assert entries[0]["record_id"] == "recNEW"
    assert entries[0]["fields"]["Summary"] == "Automated summary."
    assert entries[0]["fields"]["Review Status"] == "Pending Review"
    assert entries[0]["relevance_confidence"] == 0.88


def test_create_pending_record_failure_leaves_no_baseline(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOMATED_BASELINE_DIR", str(tmp_path / "bl"))
    client = AirtableClient.__new__(AirtableClient)
    client.pending_table = MagicMock()

    def boom(table, fields):
        raise RuntimeError("422")

    client.create_record = boom
    try:
        client.create_pending_record(
            bill_data={"State": "NM", "Name": "x", "Bill Overview (Link)": URL},
            source="LegiScan",
            relevance_confidence=0.5,
            relevance_rationale="",
            discovered_on="2026-11-19",
        )
    except RuntimeError:
        pass
    assert not list(ab.iter_entries(tmp_path / "bl"))


def test_create_pending_record_survives_baseline_failure(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("AUTOMATED_BASELINE_DIR", str(blocker / "child"))
    holder: dict = {}
    client = _stub_client(holder)

    result = client.create_pending_record(
        bill_data={"State": "NM", "Name": "x", "Bill Overview (Link)": URL},
        source="LegiScan",
        relevance_confidence=0.5,
        relevance_rationale="",
        discovered_on="2026-11-19",
    )
    assert result is holder["record"]


def _baseline_for(fields, kind="creation"):
    entry = ab._build_entry(
        kind=kind,
        record_id="recP",
        airtable_created_time=None,
        captured_at="2026-11-19T12:00:00+00:00",
        fields=fields,
    )
    return {ab._entry_key(entry): entry}


def test_compare_reports_real_edits_and_ignores_noise():
    baseline = _baseline_for(_fields())
    corrected = _fields(
        Summary="Human-corrected summary.",
        **{"UIC Pros": "Pro one\nPro two"},  # numerals stripped only -> not a correction
    )
    corrected["Progression"] = "Passed"  # volatile
    corrected["Review Status"] = "Live"

    report = ab.compare_to_current(baseline, [("Live", {"id": "recLIVE", "fields": corrected})])

    assert report["matched"] == 1
    item = report["records"][0]
    assert set(item["changed"]) == {"Summary"}
    assert item["changed"]["Summary"]["automated"] == "Automated summary."
    assert item["current_table"] == "Live"
    assert report["field_change_counts"] == {"Summary": 1}


def test_compare_include_volatile_flag():
    baseline = _baseline_for(_fields())
    corrected = _fields(Progression="Passed")
    report = ab.compare_to_current(
        baseline, [("Live", {"id": "r", "fields": corrected})], include_volatile=True
    )
    assert "Progression" in report["records"][0]["changed"]


def test_compare_ignores_airtable_system_fields():
    baseline = _baseline_for(_fields())
    live_row = _fields(**{"Created By": {"name": "Reviewer"}})
    report = ab.compare_to_current(baseline, [("Live", {"id": "r", "fields": live_row})])
    assert report["records"][0]["changed"] == {}


def test_compare_does_not_match_records_with_no_identity():
    """Blank-URL rows must not collapse onto each other (earlier ad-hoc check did)."""
    baseline = _baseline_for({"Summary": "no url, no bill number"})
    assert all(key.startswith("id:") for key in baseline)
    report = ab.compare_to_current(baseline, [("Live", {"id": "other", "fields": {"Summary": "x"}})])
    assert report["matched"] == 0


def test_compare_skips_fields_the_current_table_does_not_carry():
    baseline = _baseline_for(_fields(**{"Level of Survivor / Relative Input": "No"}))
    live_row = _fields()  # Live schema has no such field
    report = ab.compare_to_current(baseline, [("Live", {"id": "r", "fields": live_row})])
    assert report["records"][0]["changed"] == {}


def test_compare_prefers_live_over_pending_and_supports_approved_only():
    baseline = _baseline_for(_fields())
    pending_row = ("Pending", {"id": "recPEND", "fields": _fields(Summary="pending edit")})
    live_row = ("Live", {"id": "recLIVE", "fields": _fields(Summary="live edit")})

    both = ab.compare_to_current(baseline, [pending_row, live_row])
    assert both["records"][0]["current_table"] == "Live"
    assert both["records"][0]["changed"]["Summary"]["current"] == "live edit"

    pending_only = ab.compare_to_current(baseline, [pending_row], approved_only=True)
    assert pending_only["matched"] == 0
    assert pending_only["baseline_without_current"]


def test_compare_matches_by_url_across_record_ids():
    """Approval creates a new Live record id; the join must be the bill identity."""
    baseline = _baseline_for(_fields())
    report = ab.compare_to_current(
        baseline,
        [("Live", {"id": "recTotallyDifferent", "fields": _fields(**{"Bill Overview (Link)": URL + "/"})})],
    )
    assert report["matched"] == 1 and report["matched_unchanged"] == 1


def test_baseline_from_snapshots_and_creation_precedence(tmp_path):
    snapshot = tmp_path / "pending.json"
    snapshot.write_text(
        json.dumps(
            {
                "exported_at": "2026-08-08T16:42:56+00:00",
                "table": "Pending",
                "records": [{"id": "recOLD", "fields": _fields(Summary="snapshot value")}],
            }
        )
    )
    seeded = ab.baseline_from_snapshots([snapshot])
    assert next(iter(seeded.values()))["kind"] == "snapshot"

    creation = _baseline_for(_fields(Summary="creation value"))
    merged = {**seeded, **creation}
    assert next(iter(merged.values()))["fields"]["Summary"] == "creation value"


def test_snapshot_tables_handles_combined_and_single_formats(tmp_path):
    combined = tmp_path / "combined.json"
    combined.write_text(
        json.dumps({"live": [{"id": "a", "fields": {}}], "pending": [{"id": "b", "fields": {}}]})
    )
    assert [label for label, _ in ab.snapshot_tables(combined)] == ["Live", "Pending"]

    live = tmp_path / "live.json"
    live.write_text(json.dumps({"table": "Main v3", "records": [{"id": "c", "fields": {}}]}))
    assert [label for label, _ in ab.snapshot_tables(live)] == ["Live"]
