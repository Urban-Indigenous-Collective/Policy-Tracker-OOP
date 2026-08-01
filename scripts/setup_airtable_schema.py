#!/usr/bin/env python3
"""Create Pending table fields and Main v3 Review Status via Airtable Metadata API."""

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
LIVE_TABLE = os.getenv("AIRTABLE_TABLE", "Main v3")
PENDING_TABLE = os.getenv("AIRTABLE_PENDING_TABLE", "Pending")

META_BASE = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}"


def headers():
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def get_base_schema():
    r = requests.get(f"{META_BASE}/tables", headers=headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def find_table(schema, name: str):
    for table in schema.get("tables", []):
        if table.get("name") == name:
            return table
    return None


def existing_field_names(table) -> set[str]:
    return {f["name"] for f in table.get("fields", [])}


def create_field(table_id: str, field_def: dict) -> dict:
    url = f"{META_BASE}/tables/{table_id}/fields"
    r = requests.post(url, headers=headers(), json=field_def, timeout=30)
    if r.status_code == 422:
        # Field may already exist under slightly different handling
        return {"error": r.json()}
    r.raise_for_status()
    return r.json()


YES_NO_SOMEWHAT = {
    "type": "singleSelect",
    "options": {"choices": [{"name": "Yes"}, {"name": "No"}, {"name": "Somewhat"}]},
}

YES_NO = {
    "type": "singleSelect",
    "options": {"choices": [{"name": "Yes"}, {"name": "No"}]},
}

PENDING_FIELDS = [
    {"name": "State", "type": "singleLineText"},
    {"name": "Title", "type": "singleLineText"},
    {"name": "Bill Number", "type": "singleLineText"},
    {"name": "Status", "type": "singleLineText"},
    {"name": "Progression", "type": "singleLineText"},
    {"name": "Chamber", "type": "singleLineText"},
    {"name": "Chamber Details", "type": "multilineText"},
    {"name": "Bill Overview", "type": "url"},
    {"name": "Bill Text", "type": "url"},
    {"name": "Optional Link", "type": "url"},
    {"name": "Summary", "type": "multilineText"},
    {"name": "UIC Pros", "type": "multilineText"},
    {"name": "UIC Cons", "type": "multilineText"},
    {"name": "Mechanisms for Evaluation?", **YES_NO_SOMEWHAT},
    {"name": "Mechanisms for Evaluation", "type": "multilineText"},
    {"name": "Gender Inclusive Language?", **YES_NO_SOMEWHAT},
    {"name": "Gender Inclusive Explanation", "type": "multilineText"},
    {"name": "Prevention Efforts?", **YES_NO},
    {"name": "Prevention Efforts", "type": "multilineText"},
    {"name": "Level of Survivor / Relative Input?", **YES_NO_SOMEWHAT},
    {"name": "Level of Survivor / Relative Input", "type": "multilineText"},
    {"name": "Centering of Indigenous Voices?", **YES_NO_SOMEWHAT},
    {"name": "Centering of Indigenous Voices", "type": "multilineText"},
    {"name": "Sponsors", "type": "multilineText"},
    {"name": "Indigenous Sponsorship", "type": "multilineText"},
    {"name": "Session", "type": "singleLineText"},
    {"name": "Categories", "type": "singleLineText"},
    {"name": "Last Update", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
    {"name": "Validation Warnings", "type": "multilineText"},
    {
        "name": "Review Status",
        "type": "singleSelect",
        "options": {
            "choices": [
                {"name": "Pending Review"},
                {"name": "Approved"},
                {"name": "Rejected"},
            ]
        },
    },
    {
        "name": "Source",
        "type": "singleSelect",
        "options": {"choices": [{"name": "LegiScan"}, {"name": "State Site"}]},
    },
    {"name": "Relevance Confidence", "type": "number", "options": {"precision": 2}},
    {"name": "Relevance Rationale", "type": "multilineText"},
    {"name": "Discovered On", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
]

MAIN_V3_NEW_FIELDS = [
    {
        "name": "Review Status",
        "type": "singleSelect",
        "options": {
            "choices": [{"name": "Live"}, {"name": "Send Back to Pending"}]
        },
    },
]


def apply_fields(table_name: str, table_id: str, existing: set[str], field_defs: list[dict]):
    created = []
    skipped = []
    errors = []

    for field_def in field_defs:
        name = field_def["name"]
        if name in existing:
            skipped.append(name)
            continue
        try:
            result = create_field(table_id, field_def)
            if "error" in result:
                errors.append((name, result["error"]))
            else:
                created.append(name)
                existing.add(name)
                print(f"  + {table_name}: {name}")
            time.sleep(0.25)  # gentle rate limit
        except requests.HTTPError as exc:
            errors.append((name, exc.response.text if exc.response else str(exc)))
            print(f"  ! {table_name}: {name} — {errors[-1][1][:120]}")

    return created, skipped, errors


def main():
    if not API_KEY or not BASE_ID:
        print("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in .env")
        sys.exit(1)

    print(f"Fetching schema for base {BASE_ID[:8]}...")
    try:
        schema = get_base_schema()
    except requests.HTTPError as exc:
        print(f"Failed to fetch schema: {exc}")
        if exc.response is not None:
            print(exc.response.text)
        print(
            "\nYour token may need schema.bases:read and schema.bases:write scopes.\n"
            "Create a new Personal Access Token at https://airtable.com/create/tokens"
        )
        sys.exit(1)

    pending = find_table(schema, PENDING_TABLE)
    live = find_table(schema, LIVE_TABLE)

    if not pending:
        print(f"Table '{PENDING_TABLE}' not found. Create an empty table named '{PENDING_TABLE}' first.")
        sys.exit(1)
    if not live:
        print(f"Table '{LIVE_TABLE}' not found.")
        sys.exit(1)

    print(f"\nPending table ({PENDING_TABLE}) id={pending['id']}")
    print(f"Main table ({LIVE_TABLE}) id={live['id']}")
    print(f"Existing Pending fields: {len(pending.get('fields', []))}")
    print(f"Existing Main v3 fields: {len(live.get('fields', []))}")

    pending_existing = existing_field_names(pending)
    live_existing = existing_field_names(live)

    print(f"\nAdding Pending fields...")
    p_created, p_skipped, p_errors = apply_fields(
        PENDING_TABLE, pending["id"], pending_existing, PENDING_FIELDS
    )

    print(f"\nAdding Main v3 fields...")
    m_created, m_skipped, m_errors = apply_fields(
        LIVE_TABLE, live["id"], live_existing, MAIN_V3_NEW_FIELDS
    )

    print("\n--- Summary ---")
    print(f"Pending: {len(p_created)} created, {len(p_skipped)} already existed, {len(p_errors)} errors")
    print(f"Main v3: {len(m_created)} created, {len(m_skipped)} already existed, {len(m_errors)} errors")

    if p_errors or m_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
