#!/usr/bin/env python3
"""Ensure Pending.Source single-select includes all SOURCE_CHOICES (Pending-only).

Does NOT add Source to Main v3 — that field is workflow-only on Pending.

Uses Meta API when possible; falls back to a typecast record write (then delete),
which Airtable allows even when choice-list PATCH is rejected.

    python scripts/ensure_pending_source_choices.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from pyairtable import Api

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from airtable_schema import SOURCE_CHOICES  # noqa: E402

load_dotenv(ROOT / ".env")

API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
PENDING_TABLE = os.getenv("AIRTABLE_PENDING_TABLE", "Pending")
META_BASE = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}"


def headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def fetch_source_field() -> tuple[dict, dict]:
    r = requests.get(f"{META_BASE}/tables", headers=headers(), timeout=30)
    r.raise_for_status()
    pending = next(
        (t for t in r.json().get("tables", []) if t.get("name") == PENDING_TABLE),
        None,
    )
    if not pending:
        raise SystemExit(f"Table '{PENDING_TABLE}' not found")
    source_field = next(
        (f for f in pending.get("fields", []) if f.get("name") == "Source"),
        None,
    )
    if not source_field:
        raise SystemExit("Pending has no Source field — run create_pending_table.py first")
    return pending, source_field


def choice_names(source_field: dict) -> list[str]:
    return [
        c.get("name")
        for c in (source_field.get("options") or {}).get("choices") or []
        if c.get("name")
    ]


def ensure_via_meta(pending: dict, source_field: dict, missing: list[str]) -> bool:
    existing_choices = list((source_field.get("options") or {}).get("choices") or [])
    merged_choices = []
    for choice in existing_choices:
        entry = {"name": choice["name"]}
        if choice.get("id"):
            entry["id"] = choice["id"]
        if choice.get("color"):
            entry["color"] = choice["color"]
        merged_choices.append(entry)
    for name in missing:
        merged_choices.append({"name": name, "color": "grayLight2"})

    patch = requests.patch(
        f"{META_BASE}/tables/{pending['id']}/fields/{source_field['id']}",
        headers=headers(),
        json={"options": {"choices": merged_choices}},
        timeout=30,
    )
    if patch.ok:
        print(f"Updated Pending.Source via Meta API: {[c['name'] for c in merged_choices]}")
        return True
    print(f"Meta API choice update failed ({patch.status_code}): {patch.text[:200]}")
    return False


def ensure_via_typecast(missing: list[str]) -> None:
    """Create+delete a probe record per missing choice so Airtable registers it."""
    table = Api(API_KEY).table(BASE_ID, PENDING_TABLE)
    for name in missing:
        rec = table.create(
            {
                "Name": f"[schema probe] {name}",
                "State": "National",
                "Status": "Pending",
                "Progression": "Progression",
                "Chamber": "Executive",
                "Bill Overview (Link)": f"https://example.gov/schema-probe-{name.lower().replace(' ', '-')}",
                "Review Status": "Pending Review",
                "Source": name,
                "Discovered On": time.strftime("%Y-%m-%d"),
                "Last Update": time.strftime("%Y-%m-%d"),
                "Summary": f"Temporary probe to register Source={name}",
            },
            typecast=True,
        )
        table.delete(rec["id"])
        print(f"Registered Source choice via typecast: {name}")


def main() -> int:
    if not API_KEY or not BASE_ID:
        print("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in .env")
        return 1

    pending, source_field = fetch_source_field()
    if source_field.get("type") != "singleSelect":
        print(f"Source is type={source_field.get('type')}, expected singleSelect")
        return 1

    existing = choice_names(source_field)
    missing = [c for c in SOURCE_CHOICES if c not in existing]
    if not missing:
        print(f"Pending.Source already has all choices: {existing}")
        print("Note: Source remains Pending-only — not on Main v3.")
        return 0

    if not ensure_via_meta(pending, source_field, missing):
        print("Falling back to typecast record probe...")
        ensure_via_typecast(missing)

    _, source_field = fetch_source_field()
    final = choice_names(source_field)
    still_missing = [c for c in SOURCE_CHOICES if c not in final]
    if still_missing:
        print(f"Still missing choices: {still_missing}")
        return 1
    print(f"Pending.Source choices: {final}")
    print("Note: Source remains Pending-only — not added to Main v3.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
