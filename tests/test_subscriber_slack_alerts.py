"""Subscriber Slack alerts (#mmiwr-subscribers webhook)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_SUBSCRIBE_ENABLED", "true")
    monkeypatch.setenv("STATE_SUBSCRIBE_STORE_PATH", str(tmp_path / "subs.json"))
    monkeypatch.setenv("STATE_SUBSCRIBE_FIXED_OTP", "123456")
    monkeypatch.setenv("STATE_SUBSCRIBE_RATE_MAX", "50")
    monkeypatch.setenv("STATE_SUBSCRIBE_MAIL_PROVIDER", "log")
    monkeypatch.setenv(
        "SLACK_SUBSCRIBERS_WEBHOOK_URL", "https://hooks.slack.com/services/TEST"
    )

    from subscriptions.routes import reset_rate_limits_for_tests
    from subscriptions.store import reset_store_for_tests

    reset_rate_limits_for_tests()
    reset_store_for_tests()

    from app import app

    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client

    reset_rate_limits_for_tests()
    reset_store_for_tests()


def test_notify_helpers_post_expected_copy(monkeypatch):
    monkeypatch.setenv(
        "SLACK_SUBSCRIBERS_WEBHOOK_URL", "https://hooks.slack.com/services/TEST"
    )
    from subscriptions import slack_alerts

    with patch.object(slack_alerts, "_post", return_value=True) as mock_post:
        assert slack_alerts.notify_state_subscribed("a@example.com", "WA")
        assert "Washington" in mock_post.call_args[0][0]
        assert "a@example.com" in mock_post.call_args[0][0]

        assert slack_alerts.notify_state_subscribed("a@example.com", "National")
        assert "National" in mock_post.call_args[0][0]

        assert slack_alerts.notify_monthly_subscribed("b@example.com")
        assert "monthly digest" in mock_post.call_args[0][0].lower()

        assert slack_alerts.notify_state_unsubscribed(
            "a@example.com", removed="WA", remaining=["OR"]
        )
        assert "Unsubscribed" in mock_post.call_args[0][0]

        assert slack_alerts.notify_monthly_digest_run(
            {
                "month": "2026-10",
                "events": 3,
                "subscribers": 2,
                "emails_sent": 2,
                "emails_failed": 0,
                "emails_skipped": 0,
            }
        )
        assert "Monthly digest sent" in mock_post.call_args[0][0]
        assert "2026-10" in mock_post.call_args[0][0]


def test_notify_skipped_without_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_SUBSCRIBERS_WEBHOOK_URL", raising=False)
    from subscriptions import slack_alerts

    with patch.object(slack_alerts.requests, "post") as mock_post:
        assert slack_alerts.notify_monthly_subscribed("a@example.com") is False
        mock_post.assert_not_called()


def test_signup_posts_slack_once(client):
    with patch(
        "subscriptions.routes.notify_state_subscribed", return_value=True
    ) as mock_notify:
        first = client.post(
            "/api/v1/subscriptions/signup",
            json={"email": "new@example.com", "state": "WA"},
        )
        assert first.status_code == 200
        mock_notify.assert_called_once_with("new@example.com", "WA")

        again = client.post(
            "/api/v1/subscriptions/signup",
            json={"email": "new@example.com", "state": "WA"},
        )
        assert again.get_json()["alreadySubscribed"] is True
        mock_notify.assert_called_once()


def test_national_signup_posts_slack(client):
    with patch(
        "subscriptions.routes.notify_state_subscribed", return_value=True
    ) as mock_notify:
        resp = client.post(
            "/api/v1/subscriptions/signup",
            json={"email": "nat@example.com", "state": "National"},
        )
        assert resp.status_code == 200
        mock_notify.assert_called_once_with("nat@example.com", "National")


def test_monthly_signup_posts_slack_once(client):
    with patch(
        "subscriptions.routes.notify_monthly_subscribed", return_value=True
    ) as mock_notify:
        first = client.post(
            "/api/v1/subscriptions/monthly",
            json={"email": "digest@example.com"},
        )
        assert first.status_code == 200
        mock_notify.assert_called_once_with("digest@example.com")

        again = client.post(
            "/api/v1/subscriptions/monthly",
            json={"email": "digest@example.com"},
        )
        assert again.get_json()["alreadySubscribed"] is True
        mock_notify.assert_called_once()


def test_unsubscribe_posts_slack(client):
    client.post(
        "/api/v1/subscriptions/signup",
        json={"email": "u@example.com", "state": "WA"},
    )
    client.post(
        "/api/v1/subscriptions/signup",
        json={"email": "u@example.com", "state": "OR"},
    )
    client.post(
        "/api/v1/subscriptions/request-code",
        json={"email": "u@example.com", "state": "WA"},
    )
    verified = client.post(
        "/api/v1/subscriptions/verify",
        json={"email": "u@example.com", "code": "123456"},
    )
    token = verified.get_json()["sessionToken"]

    with patch(
        "subscriptions.routes.notify_state_unsubscribed", return_value=True
    ) as mock_notify:
        unsub = client.post(
            "/api/v1/subscriptions/unsubscribe",
            json={"state": "WA"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert unsub.status_code == 200
        mock_notify.assert_called_once()
        kwargs = mock_notify.call_args.kwargs
        assert mock_notify.call_args.args[0] == "u@example.com"
        assert kwargs["removed"] == "WA"
        assert "OR" in kwargs["remaining"]
