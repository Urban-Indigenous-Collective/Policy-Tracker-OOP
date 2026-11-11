"""Tests for env-gated state subscription API."""

from __future__ import annotations

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_SUBSCRIBE_ENABLED", "true")
    monkeypatch.setenv("STATE_SUBSCRIBE_STORE_PATH", str(tmp_path / "subs.json"))
    monkeypatch.setenv("STATE_SUBSCRIBE_FIXED_OTP", "123456")
    monkeypatch.setenv("STATE_SUBSCRIBE_RATE_MAX", "50")
    # Never hit real Gmail during unit tests (local .env may set provider=gmail).
    monkeypatch.setenv("STATE_SUBSCRIBE_MAIL_PROVIDER", "log")

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


@pytest.fixture
def disabled_client(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_SUBSCRIBE_ENABLED", "false")
    monkeypatch.setenv("STATE_SUBSCRIBE_STORE_PATH", str(tmp_path / "subs.json"))

    from app import app

    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_status_disabled_returns_404(disabled_client):
    resp = disabled_client.get("/api/v1/subscriptions/status")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_signup_disabled_returns_404(disabled_client):
    resp = disabled_client.post(
        "/api/v1/subscriptions/signup",
        json={"email": "a@example.com", "state": "WA"},
    )
    assert resp.status_code == 404


def test_status_enabled(client):
    resp = client.get("/api/v1/subscriptions/status")
    assert resp.status_code == 200
    assert resp.get_json()["enabled"] is True


def test_signup_rejects_bad_email(client):
    resp = client.post(
        "/api/v1/subscriptions/signup",
        json={"email": "not-an-email", "state": "WA"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_email"


def test_signup_rejects_bad_state(client):
    resp = client.post(
        "/api/v1/subscriptions/signup",
        json={"email": "a@example.com", "state": "ZZ"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_state"


def test_new_signup_subscribes_immediately(client):
    email = "new@example.com"
    resp = client.post(
        "/api/v1/subscriptions/signup",
        json={"email": email, "state": "WA"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "subscribed"
    assert body["states"] == ["WA"]
    assert body["hasExistingSubscriptions"] is False


def test_existing_email_adds_state_without_otp_then_manage_optional(client):
    email = "subscriber@example.com"

    first = client.post(
        "/api/v1/subscriptions/signup",
        json={"email": email, "state": "WA"},
    )
    assert first.get_json()["status"] == "subscribed"
    assert first.get_json()["hasExistingSubscriptions"] is False

    again = client.post(
        "/api/v1/subscriptions/signup",
        json={"email": email, "state": "OR"},
    )
    assert again.status_code == 200
    body = again.get_json()
    assert body["status"] == "subscribed"
    assert body["hasExistingSubscriptions"] is True
    assert body["alreadySubscribed"] is False
    assert set(body["states"]) == {"OR", "WA"}

    duplicate = client.post(
        "/api/v1/subscriptions/signup",
        json={"email": email, "state": "OR"},
    )
    assert duplicate.get_json()["alreadySubscribed"] is True
    assert set(duplicate.get_json()["states"]) == {"OR", "WA"}

    # Manage path still requires OTP via request-code (not signup).
    code_resp = client.post(
        "/api/v1/subscriptions/request-code",
        json={"email": email, "state": "OR"},
    )
    assert code_resp.get_json()["status"] == "verification_required"

    bad = client.post(
        "/api/v1/subscriptions/verify",
        json={"email": email, "code": "000000"},
    )
    assert bad.status_code == 400

    verified = client.post(
        "/api/v1/subscriptions/verify",
        json={"email": email, "code": "123456"},
    )
    assert verified.status_code == 200
    token = verified.get_json()["sessionToken"]
    assert set(verified.get_json()["states"]) == {"OR", "WA"}

    unsub = client.post(
        "/api/v1/subscriptions/unsubscribe",
        json={"state": "WA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unsub.get_json()["states"] == ["OR"]

    unsub_all = client.post(
        "/api/v1/subscriptions/unsubscribe",
        json={"all": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unsub_all.get_json()["states"] == []
    assert unsub_all.get_json()["removed"] == "all"


def test_request_code_requires_existing(client):
    resp = client.post(
        "/api/v1/subscriptions/request-code",
        json={"email": "nobody@example.com", "state": "WA"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "not_subscribed"


def test_request_code_resends_for_existing(client):
    email = "resend@example.com"
    client.post("/api/v1/subscriptions/signup", json={"email": email, "state": "AK"})
    resp = client.post(
        "/api/v1/subscriptions/request-code",
        json={"email": email, "state": "CA"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "verification_required"


def test_magic_link_verifies_and_opens_session(client, monkeypatch, caplog):
    import logging

    email = "magic@example.com"
    client.post("/api/v1/subscriptions/signup", json={"email": email, "state": "WA"})
    # Adding another state via signup is frictionless; manage OTP comes from request-code.
    client.post("/api/v1/subscriptions/signup", json={"email": email, "state": "OR"})

    with caplog.at_level(logging.INFO, logger="subscriptions.mail"):
        client.post(
            "/api/v1/subscriptions/request-code",
            json={"email": email, "state": "OR"},
        )

    magic_url = None
    for record in caplog.records:
        msg = record.getMessage()
        if "state_subscribe magic link" in msg and "token=" in msg:
            magic_url = msg.rsplit(" ", 1)[-1]
            break
    assert magic_url, "expected magic link in logs"
    token = magic_url.split("token=", 1)[1]

    verified = client.post(
        "/api/v1/subscriptions/verify-link",
        json={"token": token},
    )
    assert verified.status_code == 200
    body = verified.get_json()
    assert body["email"] == email
    assert "WA" in body["states"]
    assert body["sessionToken"]

    # One-time use
    again = client.post(
        "/api/v1/subscriptions/verify-link",
        json={"token": token},
    )
    assert again.status_code == 400


def test_national_state_allowed(client):
    resp = client.post(
        "/api/v1/subscriptions/signup",
        json={"email": "nat@example.com", "state": "National"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "subscribed"
    assert resp.get_json()["state"] == "National"


def test_me_requires_session(client):
    resp = client.get("/api/v1/subscriptions/me")
    assert resp.status_code == 401
