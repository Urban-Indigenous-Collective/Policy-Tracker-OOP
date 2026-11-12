"""Tests for monthly digest archive, summarize fallback, and fan-out."""

from __future__ import annotations

import pytest


@pytest.fixture
def monthly_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_SUBSCRIBE_ENABLED", "true")
    monkeypatch.setenv("STATE_SUBSCRIBE_STORE_PATH", str(tmp_path / "subs.json"))
    monkeypatch.setenv(
        "STATE_SUBSCRIBE_DIGEST_QUEUE_PATH", str(tmp_path / "digest_queue.json")
    )
    monkeypatch.setenv(
        "STATE_SUBSCRIBE_MONTHLY_ARCHIVE_PATH",
        str(tmp_path / "monthly_archive.json"),
    )
    monkeypatch.setenv("STATE_SUBSCRIBE_MAIL_PROVIDER", "log")
    monkeypatch.setenv("PUBLIC_SITE_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("DISCOVERY_TZ", "America/New_York")

    from subscriptions.digest_queue import reset_digest_queue_for_tests
    from subscriptions.monthly_archive import reset_monthly_archive_for_tests
    from subscriptions.store import reset_store_for_tests

    reset_store_for_tests()
    reset_digest_queue_for_tests()
    reset_monthly_archive_for_tests()
    yield tmp_path
    reset_store_for_tests()
    reset_digest_queue_for_tests()
    reset_monthly_archive_for_tests()


def test_enqueue_dual_writes_monthly_archive(monthly_env):
    from subscriptions.digest_queue import enqueue_new_live
    from subscriptions.monthly_archive import load_events_for_month, month_key_for

    assert enqueue_new_live(
        state="NC",
        title="HB 1",
        url="https://example.com/hb1",
        record_id="recMonthly1",
        public_path="/states/NC/bills/hb-1",
    )
    month = month_key_for()
    archived = load_events_for_month(month)
    assert len(archived) == 1
    assert archived[0]["title"] == "HB 1"
    assert archived[0]["month"] == month


def test_period_label_and_previous_month(monthly_env):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from subscriptions.monthly_archive import (
        period_label_for_month_key,
        previous_month_key,
    )

    assert period_label_for_month_key("2026-11") == "November 2026"
    jan = datetime(2026, 1, 15, tzinfo=ZoneInfo("America/New_York"))
    assert previous_month_key(jan) == "2025-12"


def test_summarize_fallback_without_llm(monthly_env, monkeypatch):
    from subscriptions.monthly_summarize import summarize_month

    def boom(*_a, **_k):
        raise RuntimeError("no llm")

    monkeypatch.setattr(
        "llm.factory.get_llm_provider",
        boom,
    )
    overview, overrides = summarize_month(
        period_label="November 2026",
        events=[
            {
                "key": "a|new_live|new_live",
                "kind": "new_live",
                "state": "NC",
                "title": "HB 1",
                "summary": "New on the tracker",
            }
        ],
    )
    assert "November 2026" in overview
    assert "1 new policy" in overview
    assert "stands out" in overview.lower()
    assert overrides["a|new_live|new_live"]
    assert len(overrides["a|new_live|new_live"]) <= 160


def test_send_monthly_digests_fans_out_and_watermarks(monthly_env, monkeypatch):
    from subscriptions.digest_queue import enqueue_new_live
    from subscriptions.monthly_archive import month_key_for
    from subscriptions.monthly_digest import send_monthly_digests
    from subscriptions.store import (
        filter_unnotified_monthly_keys,
        set_monthly_digest,
    )

    set_monthly_digest("alice@example.com", True)
    set_monthly_digest("bob@example.com", True)

    enqueue_new_live(
        state="NC",
        title="HB 99",
        url="https://example.com/hb99",
        record_id="recM99",
        public_path="/states/NC/bills/hb-99",
    )
    month = month_key_for()

    monkeypatch.setattr(
        "subscriptions.monthly_digest.summarize_month",
        lambda **_kwargs: (
            "Quiet overview for tests.\n\nSecond paragraph.",
            {},
        ),
    )

    sent: list[str] = []

    def fake_send(email, *, period_label, overview, items, manage_url=None):
        sent.append(email)
        assert period_label
        assert "Quiet overview" in overview
        assert items
        assert items[0]["title"] == "HB 99"

    monkeypatch.setattr(
        "subscriptions.monthly_digest.send_monthly_subscription_digest",
        fake_send,
    )

    stats = send_monthly_digests(month_key=month)
    assert stats["emails_sent"] == 2
    assert stats["events_cleared"] == 1
    assert sorted(sent) == ["alice@example.com", "bob@example.com"]
    assert filter_unnotified_monthly_keys(
        [f"alice@example.com|{month}", f"bob@example.com|{month}"]
    ) == []

    # Archive cleared after successful fan-out; watermarks still block if re-queued.
    stats2 = send_monthly_digests(month_key=month)
    assert stats2["emails_sent"] == 0
    assert stats2["skipped_empty"] == 1


def test_send_monthly_skips_when_empty(monthly_env):
    from subscriptions.monthly_digest import send_monthly_digests
    from subscriptions.store import set_monthly_digest

    set_monthly_digest("alice@example.com", True)
    stats = send_monthly_digests(month_key="2020-01")
    assert stats["skipped_empty"] == 1
    assert stats["emails_sent"] == 0
