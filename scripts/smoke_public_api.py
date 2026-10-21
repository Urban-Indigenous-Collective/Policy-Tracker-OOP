#!/usr/bin/env python3
"""Smoke-test /api/v1 against a running Policy Tracker Flask app.

Default base URL matches ``python app.py`` (Flask on port 5000).

Other common bases:
  SMOKE_API_BASE=http://127.0.0.1:8002  # docker compose web (POLICY_HOST_PORT)
  SMOKE_API_BASE=http://127.0.0.1:8095  # nginx frontend profile (proxies /api to web)

Do NOT use port 8000 on macOS unless you know Policy Tracker is bound there —
another service often listens on 8000 and returns unrelated 404 JSON.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("SMOKE_API_BASE", "http://127.0.0.1:5000").rstrip("/")


def get(path: str) -> tuple[int, dict]:
    req = urllib.request.Request(f"{BASE}{path}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {"raw": body}
        return exc.code, data


def _hint_wrong_server() -> None:
    probe_status, probe = get("/health-check")
    print(f"Probe GET /health-check -> HTTP {probe_status}", file=sys.stderr)
    if probe_status == 404 and probe.get("error") == "Resource not found":
        print(
            f"\nNothing at {BASE} looks like Policy Tracker Flask "
            "(expected JSON health-check and /api/v1/*).\n"
            "Start the app:\n"
            "  source .venv/bin/activate && python app.py   # http://127.0.0.1:5000\n"
            "  # or: docker compose up --build web           # http://127.0.0.1:8002\n"
            "Then:\n"
            "  SMOKE_API_BASE=http://127.0.0.1:5000 python3 scripts/smoke_public_api.py\n",
            file=sys.stderr,
        )


def main() -> int:
    print(f"SMOKE_API_BASE={BASE}\n")
    for path in ("/api/v1/health", "/api/v1/states"):
        status, data = get(path)
        print(f"{path} -> HTTP {status}")
        print(json.dumps(data, indent=2)[:2000])
        if status >= 400:
            _hint_wrong_server()
            print("FAIL", file=sys.stderr)
            return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
