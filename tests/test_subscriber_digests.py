"""Tests for Live-only morning subscriber digest queue + fan-out."""

from __future__ import annotations

import pytest


@pytest.fixture
def digest_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_SUBSCRIBE_ENABLED", "true")
    monkeypatch.setenv("STATE_SUBSCRIBE_STORE_PATH", str(tmp_path / "subs.json"))
    monkeypatch.setenv(
        "STATE_SUBSCRIBE_DIGEST_QUEUE_PATH", str(tmp_path / "digest_queue.json")
    )
    monkeypatch.setenv("STATE_SUBSCRIBE_MAIL_PROVIDER", "log")
    monkeypatch.setenv("PUBLIC_SITE_URL", "http://127.0.0.1:3000")

    from subscriptions.digest_queue import reset_digest_queue_for_tests
    from subscriptions.store import reset_store_for_tests

    reset_store_for_tests()
    reset_digest_queue_for_tests()
    yield tmp_path
    reset_store_for_tests()
    reset_digest_queue_for_tests()


def test_queue_dedupes_by_key(digest_env):
    from subscriptions.digest_queue import (
        enqueue_new_live,
        enqueue_live_status_changes,
        load_events,
    )

    assert enqueue_new_live(
        state="NC",
        title="HB 1",
        url="https://example.com/hb1",
        record_id="recABC",
        public_path="/states/NC/bills/hb-1-abc",
    )
    assert not enqueue_new_live(
        state="NC",
        title="HB 1",
        url="https://example.com/hb1",
        record_id="recABC",
        public_path="/states/NC/bills/hb-1-abc",
    )
    assert enqueue_live_status_changes(
        state="NC",
        title="HB 1",
        url="https://example.com/hb1",
        record_id="recABC",
        changes=[{"field": "Status", "old": "Introduced", "new": "Passed"}],
    )
    # Chamber-only is ignored
    assert not enqueue_live_status_changes(
        state="NC",
        title="HB 1",
        url="https://example.com/hb1",
        record_id="recABC",
        changes=[{"field": "Chamber", "old": "House", "new": "Senate"}],
    )
    events = load_events()
    assert len(events) == 2
    kinds = {e["kind"] for e in events}
    assert kinds == {"new_live", "status"}


def test_fanout_groups_by_subscriber_and_watermarks(digest_env, monkeypatch):
    from subscriptions.digest import send_morning_digests
    from subscriptions.digest_queue import enqueue_new_live, load_events
    from subscriptions.store import add_state, filter_unnotified_digest_keys

    add_state("nc@example.com", "NC")
    add_state("wa@example.com", "WA")
    enqueue_new_live(
        state="NC",
        title="NC Bill",
        url="https://example.com/nc",
        record_id="recNC1",
        public_path="/states/NC/bills/nc-bill",
    )
    enqueue_new_live(
        state="WA",
        title="WA Bill",
        url="https://example.com/wa",
        record_id="recWA1",
        public_path="/states/WA/bills/wa-bill",
    )

    sent: list[tuple[str, list[str], list[str], list[str]]] = []

    def fake_send(email, *, state_labels, items):
        sent.append(
            (
                email,
                list(state_labels),
                [i["title"] for i in items],
                [i["state"] for i in items],
            )
        )

    monkeypatch.setattr(
        "subscriptions.digest.send_subscription_digest", fake_send
    )

    stats = send_morning_digests()
    assert stats["emails_sent"] == 2
    assert stats["emails_failed"] == 0
    by_email = {email: (labels, titles, states) for email, labels, titles, states in sent}
    assert by_email["nc@example.com"][1] == ["NC Bill"]
    assert by_email["nc@example.com"][0] == ["North Carolina"]
    assert by_email["nc@example.com"][2] == ["North Carolina"]
    assert by_email["wa@example.com"][1] == ["WA Bill"]
    assert by_email["wa@example.com"][0] == ["Washington"]
    assert by_email["wa@example.com"][2] == ["Washington"]
    assert load_events() == []

    # Same event key re-queued after clear — watermark blocks a second email
    assert enqueue_new_live(
        state="NC",
        title="NC Bill",
        url="https://example.com/nc",
        record_id="recNC1",
        public_path="/states/NC/bills/nc-bill",
    )
    assert filter_unnotified_digest_keys(["recNC1|new_live|new_live"]) == []
    sent.clear()
    stats2 = send_morning_digests()
    assert stats2["emails_sent"] == 0
    assert sent == []
    assert load_events() == []


def test_fanout_skips_when_disabled(digest_env, monkeypatch):
    monkeypatch.setenv("STATE_SUBSCRIBE_ENABLED", "false")
    from subscriptions.digest import send_morning_digests
    from subscriptions.digest_queue import enqueue_new_live
    from subscriptions.store import add_state

    add_state("a@example.com", "NC")
    enqueue_new_live(
        state="NC",
        title="Bill",
        url="https://example.com/b",
        record_id="rec1",
    )
    stats = send_morning_digests()
    assert stats["skipped_disabled"] == 1
    assert stats["emails_sent"] == 0


def test_empty_queue_no_send(digest_env):
    from subscriptions.digest import send_morning_digests

    stats = send_morning_digests()
    assert stats["queued"] == 0
    assert stats["emails_sent"] == 0


def test_status_refresh_queues_live_status_only(digest_env):
    from subscriptions.digest_queue import (
        EMAIL_STATUS_FIELDS,
        enqueue_live_status_changes,
        load_events,
        status_fingerprint,
    )

    changes = [
        {"field": "Status", "old": "A", "new": "B"},
        {"field": "Last Update", "old": "1", "new": "2"},
        {"field": "Progression", "old": "X", "new": "Y"},
    ]
    assert enqueue_live_status_changes(
        state="OR",
        title="SB 2",
        url="https://example.com/sb2",
        record_id="recOR",
        changes=changes,
    )
    events = load_events()
    assert len(events) == 1
    assert events[0]["kind"] == "status"
    assert "Status:" in events[0]["summary"]
    assert "Progression:" in events[0]["summary"]
    assert "Last Update" not in events[0]["summary"]
    assert events[0]["status"] == "B"
    assert events[0]["progression"] == "Y"
    fp = status_fingerprint(changes)
    assert "Status=B" in fp and "Progression=Y" in fp
    assert EMAIL_STATUS_FIELDS == frozenset({"Status", "Progression"})


def test_fanout_passes_status_fields_into_digest_items(digest_env, monkeypatch):
    from subscriptions.digest import send_morning_digests
    from subscriptions.digest_queue import enqueue_live_status_changes, enqueue_new_live
    from subscriptions.store import add_state

    add_state("reader@example.com", "WA")
    enqueue_new_live(
        state="WA",
        title="New Live Bill",
        url="https://example.com/new",
        record_id="recNew",
        public_path="/states/WA/bills/new",
    )
    enqueue_live_status_changes(
        state="WA",
        title="Status Bill",
        url="https://example.com/status",
        record_id="recStatus",
        public_path="/states/WA/bills/status",
        changes=[
            {"field": "Status", "old": "Pending", "new": "Passed"},
            {"field": "Progression", "old": "Introduced", "new": "Enacted"},
        ],
    )

    captured: list[dict] = []

    def fake_send(email, *, state_labels, items):
        captured.extend(items)

    monkeypatch.setattr(
        "subscriptions.digest.send_subscription_digest", fake_send
    )

    stats = send_morning_digests()
    assert stats["emails_sent"] == 1
    by_title = {i["title"]: i for i in captured}
    new_item = by_title["New Live Bill"]
    assert new_item["kind"] == "new_live"
    assert "status" not in new_item
    status_item = by_title["Status Bill"]
    assert status_item["kind"] == "status"
    assert status_item["status"] == "Passed"
    assert status_item["progression"] == "Enacted"
