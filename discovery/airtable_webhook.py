"""Airtable change pings → approval sync (no 10-minute polling).

Airtable POSTs a thin ping to Flask when Review Status changes. We verify the
HMAC, then run the same ApprovalSync movers. PAT webhooks expire after 7 days
unless refreshed; nightly refresh extends them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable

from airtable_fields import LIVE_REVIEW_STATUS_FIELD

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/webhooks/airtable"
DEFAULT_PUBLIC_BASE_URL = "https://policy.urbanindigenouscollective.org"


def webhook_state_path() -> Path:
    db_path = Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))
    return db_path.parent / "airtable_webhooks.json"


def notification_url() -> str:
    explicit = (os.getenv("AIRTABLE_WEBHOOK_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    base = (os.getenv("PUBLIC_BASE_URL") or DEFAULT_PUBLIC_BASE_URL).rstrip("/")
    return f"{base}{WEBHOOK_PATH}"


def review_status_specification(table_id: str, field_id: str) -> dict:
    """Ping only when Review Status is updated on this table (not discovery inserts)."""
    return {
        "options": {
            "filters": {
                "dataTypes": ["tableData"],
                "changeTypes": ["update"],
                "recordChangeScope": table_id,
                "watchDataInFieldIds": [field_id],
            }
        }
    }


def load_webhook_state(path: Path | None = None) -> dict:
    state_path = path or webhook_state_path()
    if not state_path.is_file():
        return {"hooks": []}
    return json.loads(state_path.read_text())


def save_webhook_state(state: dict, path: Path | None = None) -> None:
    state_path = path or webhook_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(state_path)
    try:
        os.chmod(state_path, 0o600)
    except OSError:
        pass


def verify_airtable_mac(body: bytes, header: str | None, mac_secret_base64: str) -> bool:
    if not header or not mac_secret_base64:
        return False
    prefix = "hmac-sha256="
    if not header.startswith(prefix):
        return False
    given = header[len(prefix) :].strip()
    try:
        secret = base64.b64decode(mac_secret_base64)
    except Exception:
        return False
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(given, expected)


def verify_ping(body: bytes, mac_header: str | None, webhook_id: str, state: dict) -> bool:
    for hook in state.get("hooks") or []:
        if hook.get("id") == webhook_id:
            return verify_airtable_mac(body, mac_header, hook.get("mac_secret_base64") or "")
    return False


def _table_by_name(schema: dict, name: str) -> dict:
    for table in schema.get("tables") or []:
        if table.get("name") == name:
            return table
    raise ValueError(f"Airtable table {name!r} not found")


def _field_id(table: dict, field_name: str) -> str:
    for field in table.get("fields") or []:
        if field.get("name") == field_name:
            return field["id"]
    raise ValueError(f"Field {field_name!r} not found on table {table.get('name')}")


def ensure_review_status_webhooks(airtable=None) -> dict:
    """Create (or replace) Review Status webhooks for Pending and Live.

    macSecretBase64 is only returned at creation; the state file must be kept.
    """
    from airtable_client import AirtableClient

    client = airtable or AirtableClient()
    url = notification_url()
    schema = client.get_base_schema()
    live_name = os.getenv("AIRTABLE_TABLE", "Main v3").strip('"')
    pending_name = os.getenv("AIRTABLE_PENDING_TABLE", "Pending")

    wanted = []
    for table_name, field_name in (
        (pending_name, "Review Status"),
        (live_name, LIVE_REVIEW_STATUS_FIELD),
    ):
        table = _table_by_name(schema, table_name)
        field_id = _field_id(table, field_name)
        wanted.append(
            {
                "table_name": table_name,
                "table_id": table["id"],
                "field_id": field_id,
                "specification": review_status_specification(table["id"], field_id),
            }
        )

    for existing in client.list_webhooks():
        if (existing.get("notificationUrl") or "").rstrip("/") == url.rstrip("/"):
            client.delete_webhook(existing["id"])

    hooks = []
    for item in wanted:
        created = client.create_webhook(url, item["specification"])
        hooks.append(
            {
                "id": created["id"],
                "mac_secret_base64": created["macSecretBase64"],
                "table_name": item["table_name"],
                "table_id": item["table_id"],
                "field_id": item["field_id"],
                "expiration_time": created.get("expirationTime"),
            }
        )
    state = {"notification_url": url, "hooks": hooks}
    save_webhook_state(state)
    logger.info("Registered %d Airtable review-status webhooks at %s", len(hooks), url)
    return state


def refresh_registered_webhooks(airtable=None) -> dict[str, int]:
    """Extend PAT webhook lifetime. No-op when none are registered."""
    from airtable_client import AirtableClient, is_airtable_rate_limit_error

    stats = {"refreshed": 0, "errors": 0, "skipped": 0}
    state = load_webhook_state()
    hooks = state.get("hooks") or []
    if not hooks:
        stats["skipped"] = 1
        logger.info("Airtable webhook refresh skipped (none registered)")
        return stats

    client = airtable or AirtableClient()
    for hook in hooks:
        try:
            refreshed = client.refresh_webhook(hook["id"])
            if refreshed.get("expirationTime"):
                hook["expiration_time"] = refreshed["expirationTime"]
            stats["refreshed"] += 1
        except Exception as exc:
            if is_airtable_rate_limit_error(exc):
                logger.warning("Airtable webhook refresh rate-limited: %s", exc)
                stats["errors"] += 1
                break
            logger.exception("Failed to refresh Airtable webhook %s", hook.get("id"))
            stats["errors"] += 1
    if stats["refreshed"]:
        save_webhook_state(state)
    return stats


def run_locked_approval_sync() -> dict[str, int]:
    from approval_sync import ApprovalSync

    return ApprovalSync().run()


def process_webhook_request(
    body: bytes,
    mac_header: str | None,
    payload: dict[str, Any],
    *,
    state: dict | None = None,
    run_sync: Callable[[], Any] | None = None,
    background: bool = True,
) -> tuple[int, str]:
    """Return (http_status, body). 200/204 with empty body as Airtable requires."""
    state = state if state is not None else load_webhook_state()
    webhook_id = ((payload.get("webhook") or {}).get("id")) or ""
    if not (state.get("hooks") or []):
        logger.warning("Airtable webhook ping with no registered hooks")
        return 503, ""
    if not verify_ping(body, mac_header, webhook_id, state):
        logger.warning("Airtable webhook MAC/id check failed")
        return 401, ""

    sync = run_sync or run_locked_approval_sync
    if background:
        threading.Thread(target=_run_sync_safe, args=(sync,), daemon=True).start()
    else:
        _run_sync_safe(sync)
    return 200, ""


def _run_sync_safe(sync: Callable[[], Any]) -> None:
    try:
        stats = sync()
        logger.info("Approval sync from Airtable ping: %s", stats)
    except Exception as exc:
        from airtable_client import is_airtable_rate_limit_error

        if is_airtable_rate_limit_error(exc):
            logger.warning("Approval sync from Airtable ping rate-limited; nightly catch-up will retry: %s", exc)
            return
        logger.exception("Approval sync from Airtable ping failed")
