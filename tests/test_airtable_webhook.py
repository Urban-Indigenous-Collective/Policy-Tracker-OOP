import base64
import hashlib
import hmac
import json

from discovery.airtable_webhook import (
    ensure_review_status_webhooks,
    notification_url,
    process_webhook_request,
    refresh_registered_webhooks,
    review_status_specification,
    save_webhook_state,
    verify_airtable_mac,
    verify_ping,
)


def _mac_header(body: bytes, secret: bytes) -> str:
    digest = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return f"hmac-sha256={digest}"


def test_verify_airtable_mac_accepts_matching_header():
    secret = b"webhook-secret"
    body = b'{"base":{"id":"app1"},"webhook":{"id":"ach1"}}'
    header = _mac_header(body, secret)
    assert verify_airtable_mac(body, header, base64.b64encode(secret).decode())


def test_verify_airtable_mac_rejects_tampered_body():
    secret = b"webhook-secret"
    body = b'{"webhook":{"id":"ach1"}}'
    header = _mac_header(body, secret)
    assert not verify_airtable_mac(b'{"webhook":{"id":"ach2"}}', header, base64.b64encode(secret).decode())


def test_review_status_specification_watches_updates_only():
    spec = review_status_specification("tblPending", "fldReview")
    filters = spec["options"]["filters"]
    assert filters["dataTypes"] == ["tableData"]
    assert filters["changeTypes"] == ["update"]
    assert filters["recordChangeScope"] == "tblPending"
    assert filters["watchDataInFieldIds"] == ["fldReview"]


def test_notification_url_uses_public_base(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.delenv("AIRTABLE_WEBHOOK_URL", raising=False)
    assert notification_url() == "https://example.test/webhooks/airtable"


def test_process_webhook_request_runs_sync_on_valid_ping(tmp_path, monkeypatch):
    secret = b"hook-secret"
    webhook_id = "achValid"
    state = {
        "hooks": [
            {"id": webhook_id, "mac_secret_base64": base64.b64encode(secret).decode()}
        ]
    }
    payload = {"base": {"id": "app1"}, "webhook": {"id": webhook_id}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    calls = []
    status, _ = process_webhook_request(
        body,
        _mac_header(body, secret),
        payload,
        state=state,
        run_sync=lambda: calls.append("sync") or {"approved": 1},
        background=False,
    )
    assert status == 200
    assert calls == ["sync"]


def test_process_webhook_request_rejects_bad_mac():
    state = {"hooks": [{"id": "achValid", "mac_secret_base64": base64.b64encode(b"x").decode()}]}
    payload = {"webhook": {"id": "achValid"}}
    body = b"{}"
    calls = []
    status, _ = process_webhook_request(
        body,
        "hmac-sha256=deadbeef",
        payload,
        state=state,
        run_sync=lambda: calls.append("sync"),
        background=False,
    )
    assert status == 401
    assert calls == []


def test_process_webhook_request_503_when_unregistered():
    payload = {"webhook": {"id": "achValid"}}
    status, _ = process_webhook_request(
        b"{}",
        None,
        payload,
        state={"hooks": []},
        background=False,
    )
    assert status == 503


def test_verify_ping_requires_matching_webhook_id():
    secret = b"s"
    state = {"hooks": [{"id": "achA", "mac_secret_base64": base64.b64encode(secret).decode()}]}
    body = b"{}"
    header = _mac_header(body, secret)
    assert verify_ping(body, header, "achA", state)
    assert not verify_ping(body, header, "achOther", state)


class FakeWebhookClient:
    def __init__(self):
        self.webhooks = [
            {"id": "achOld", "notificationUrl": "https://policy.urbanindigenouscollective.org/webhooks/airtable"}
        ]
        self.deleted = []
        self.created = []
        self.refreshed = []

    def get_base_schema(self):
        return {
            "tables": [
                {
                    "id": "tblPending",
                    "name": "Pending",
                    "fields": [{"id": "fldP", "name": "Review Status"}],
                },
                {
                    "id": "tblLive",
                    "name": "Main v3",
                    "fields": [{"id": "fldL", "name": "Review Status"}],
                },
            ]
        }

    def list_webhooks(self):
        return list(self.webhooks)

    def delete_webhook(self, webhook_id):
        self.deleted.append(webhook_id)
        self.webhooks = [h for h in self.webhooks if h["id"] != webhook_id]

    def create_webhook(self, notification_url, specification):
        hook_id = f"ach{len(self.created) + 1}"
        secret = base64.b64encode(f"secret-{hook_id}".encode()).decode()
        created = {
            "id": hook_id,
            "macSecretBase64": secret,
            "expirationTime": "2026-09-10T00:00:00.000Z",
        }
        self.created.append({"url": notification_url, "spec": specification, **created})
        return created

    def refresh_webhook(self, webhook_id):
        self.refreshed.append(webhook_id)
        return {"expirationTime": "2026-09-17T00:00:00.000Z"}


def test_ensure_review_status_webhooks_replaces_matching_url(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://policy.urbanindigenouscollective.org")
    monkeypatch.delenv("AIRTABLE_WEBHOOK_URL", raising=False)
    client = FakeWebhookClient()
    state = ensure_review_status_webhooks(airtable=client)
    assert client.deleted == ["achOld"]
    assert len(state["hooks"]) == 2
    assert {h["table_name"] for h in state["hooks"]} == {"Pending", "Main v3"}
    saved = json.loads((tmp_path / "airtable_webhooks.json").read_text())
    assert saved["hooks"][0]["mac_secret_base64"]


def test_refresh_registered_webhooks_extends_expiry(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    save_webhook_state(
        {
            "hooks": [
                {"id": "ach1", "mac_secret_base64": "abc", "expiration_time": "old"}
            ]
        }
    )
    client = FakeWebhookClient()
    stats = refresh_registered_webhooks(airtable=client)
    assert stats["refreshed"] == 1
    assert client.refreshed == ["ach1"]
    saved = json.loads((tmp_path / "airtable_webhooks.json").read_text())
    assert saved["hooks"][0]["expiration_time"] == "2026-09-17T00:00:00.000Z"


def test_refresh_skips_when_unregistered(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_DB_PATH", str(tmp_path / "discovery.db"))
    stats = refresh_registered_webhooks(airtable=FakeWebhookClient())
    assert stats["skipped"] == 1
    assert stats["refreshed"] == 0
