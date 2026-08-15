#!/usr/bin/env python3
"""Create Pending table as an exact Main v3 mirror plus review workflow fields.

Delete the existing Pending table in Airtable first, then run:

    python scripts/create_pending_table.py
"""

import copy
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from airtable_schema import (  # noqa: E402
    PENDING_REVIEW_STATUS_CHOICES,
    discovery_metadata_field_defs,
    pending_workflow_field_defs,
)

load_dotenv(ROOT / ".env")

API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
LIVE_TABLE = os.getenv("AIRTABLE_TABLE", "Main v3")
PENDING_TABLE = os.getenv("AIRTABLE_PENDING_TABLE", "Pending")

META_BASE = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}"

# System/computed fields — not copied to Pending
SKIP_FIELD_TYPES = {"createdBy", "createdTime", "lastModifiedTime", "autoNumber"}
SKIP_FIELD_NAMES = {"Created By"}


def headers():
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def get_schema():
    r = requests.get(f"{META_BASE}/tables", headers=headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def find_table(schema, name: str):
    for table in schema.get("tables", []):
        if table.get("name") == name:
            return table
    return None


def sanitize_choices(options: dict) -> dict:
    out = copy.deepcopy(options)
    if "choices" in out:
        out["choices"] = [{"name": c["name"]} for c in out["choices"]]
    return out


def field_to_create_def(field: dict, review_status_choices: list[str] | None = None) -> dict:
    """Convert a Metadata API field schema to a create-table field definition."""
    name = field["name"]
    ftype = field["type"]

    if review_status_choices is not None:
        return {
            "name": name,
            "type": "singleSelect",
            "options": {"choices": [{"name": c} for c in review_status_choices]},
        }

    out: dict = {"name": name, "type": ftype}
    if "options" in field and ftype not in SKIP_FIELD_TYPES:
        out["options"] = sanitize_choices(field["options"])
    return out


def build_pending_fields(live_table: dict) -> list[dict]:
    """Clone Main v3 bill fields; swap Review Status options; append workflow fields."""
    fields = []
    for field in live_table.get("fields", []):
        if field["type"] in SKIP_FIELD_TYPES or field["name"] in SKIP_FIELD_NAMES:
            continue
        if field["name"] == "Review Status":
            fields.append(field_to_create_def(field, review_status_choices=PENDING_REVIEW_STATUS_CHOICES))
        else:
            fields.append(field_to_create_def(field))

    existing = {f["name"] for f in fields}
    for extra in discovery_metadata_field_defs() + pending_workflow_field_defs():
        if extra["name"] not in existing:
            fields.append(extra)

    return fields


def ensure_main_v3_discovery_metadata(live_table: dict) -> None:
    """Add Validation Warnings and relevance fields to Main v3 if missing."""
    existing = {f["name"] for f in live_table.get("fields", [])}
    for field_def in discovery_metadata_field_defs():
        if field_def["name"] in existing:
            continue
        r = requests.post(
            f"{META_BASE}/tables/{live_table['id']}/fields",
            headers=headers(),
            json=field_def,
            timeout=30,
        )
        if r.ok:
            print(f"Added Main v3 field: {field_def['name']}")
        else:
            print(f"Warning: could not add {field_def['name']} to Main v3: {r.text[:200]}")
        time.sleep(0.25)


def create_pending_table(fields: list[dict]) -> dict:
    payload = {
        "name": PENDING_TABLE,
        "description": "MMIP policy review queue — exact mirror of Main v3 bill fields",
        "fields": fields,
    }
    r = requests.post(f"{META_BASE}/tables", headers=headers(), json=payload, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Create table failed ({r.status_code}): {r.text[:500]}")
    return r.json()


def ensure_main_v3_review_status(live_table: dict) -> None:
    """Ensure Main v3 has Review Status (Live / Send Back to Pending)."""
    names = {f["name"] for f in live_table.get("fields", [])}
    if "Review Status" in names:
        print(f"Main v3 Review Status already present")
        return
    from airtable_schema import LIVE_REVIEW_STATUS_CHOICES

    field_def = {
        "name": "Review Status",
        "type": "singleSelect",
        "options": {"choices": [{"name": c} for c in LIVE_REVIEW_STATUS_CHOICES]},
    }
    r = requests.post(
        f"{META_BASE}/tables/{live_table['id']}/fields",
        headers=headers(),
        json=field_def,
        timeout=30,
    )
    if r.ok:
        print("Added Review Status to Main v3")
    else:
        print(f"Warning: could not add Main v3 Review Status: {r.text[:200]}")


def main():
    if not API_KEY or not BASE_ID:
        print("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in .env")
        sys.exit(1)

    schema = get_schema()
    live = find_table(schema, LIVE_TABLE)
    if not live:
        print(f"Table '{LIVE_TABLE}' not found")
        sys.exit(1)

    pending = find_table(schema, PENDING_TABLE)
    if pending:
        print(
            f"Table '{PENDING_TABLE}' already exists ({len(pending.get('fields', []))} fields).\n"
            f"Delete it in the Airtable UI, then re-run this script."
        )
        sys.exit(1)

    ensure_main_v3_review_status(live)
    ensure_main_v3_discovery_metadata(live)
    time.sleep(0.25)

    fields = build_pending_fields(live)
    print(f"Creating '{PENDING_TABLE}' with {len(fields)} fields (cloned from '{LIVE_TABLE}')...")
    print("  + discovery metadata: Validation Warnings, Relevance Confidence, Relevance Rationale")
    print("  + workflow: Source, Discovered On")
    for f in fields:
        print(f"  • {f['name']} ({f['type']})")

    result = create_pending_table(fields)
    print(f"\nCreated table '{result.get('name')}' id={result.get('id')}")
    print("Pending is now an exact Main v3 mirror plus discovery workflow fields.")


if __name__ == "__main__":
    main()
