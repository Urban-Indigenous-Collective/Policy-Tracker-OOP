#!/usr/bin/env python3
"""Create Airtable Review Status webhooks that ping the public Flask app.

macSecretBase64 is only returned at creation and is stored in
data/airtable_webhooks.json (gitignored volume). Re-run after a volume wipe.

Airtable Free monthly quota blocks this call until the workspace can write again.
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from airtable_client import is_airtable_rate_limit_error
from discovery.airtable_webhook import ensure_review_status_webhooks, notification_url


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    load_dotenv()
    print(f"Notification URL: {notification_url()}")
    try:
        state = ensure_review_status_webhooks()
    except Exception as exc:
        if is_airtable_rate_limit_error(exc):
            print(
                "Airtable refused the request (rate or monthly billing limit). "
                "Register after quota resets or after a Team upgrade.",
                file=sys.stderr,
            )
            return 2
        raise
    print(f"Registered {len(state.get('hooks') or [])} webhook(s)")
    for hook in state.get("hooks") or []:
        print(f"  {hook.get('table_name')}: {hook.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
