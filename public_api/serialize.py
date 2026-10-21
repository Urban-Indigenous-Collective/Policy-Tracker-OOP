"""Airtable Main v3 records → public JSON DTOs."""

from __future__ import annotations

import re
from typing import Any

from airtable_fields import BILL_OVERVIEW_LINK_FIELD, LIVE_REVIEW_STATUS_FIELD
from public_api.states import normalize_public_state

_SLUG_SAFE = re.compile(r"[^a-z0-9]+")


def _field(fields: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in fields and fields[name] not in (None, ""):
            return fields[name]
    return None


def bill_slug(record_id: str, fields: dict[str, Any]) -> str:
    bill_number = str(_field(fields, "Bill Number") or "bill")
    session = str(_field(fields, "Session") or "session")
    base = _SLUG_SAFE.sub("-", f"{bill_number}-{session}".lower()).strip("-")
    suffix = record_id.replace("rec", "")[-6:].lower() or "000000"
    return f"{base}-{suffix}"


def record_to_bill_dto(record: dict[str, Any], *, include_analysis: bool = False) -> dict[str, Any]:
    record_id = str(record.get("id") or "")
    fields = dict(record.get("fields") or {})

    dto: dict[str, Any] = {
        "id": record_id,
        "slug": bill_slug(record_id, fields),
        "name": str(_field(fields, "Name", "Title") or "").strip(),
        "state": normalize_public_state(fields.get("State")),
        "status": str(fields.get("Status") or "").strip(),
        "progression": str(fields.get("Progression") or "").strip(),
        "billNumber": str(_field(fields, "Bill Number") or "").strip(),
        "session": str(_field(fields, "Session") or "").strip(),
        "lastUpdate": str(_field(fields, "Last Update") or "").strip(),
        "summary": str(_field(fields, "Summary") or "").strip(),
        "billOverviewUrl": str(
            _field(fields, BILL_OVERVIEW_LINK_FIELD, "Bill Overview") or ""
        ).strip(),
        "categories": _field(fields, "Categories") or [],
    }
    if isinstance(dto["categories"], str):
        dto["categories"] = [dto["categories"]]

    if include_analysis:
        dto["uicPros"] = str(_field(fields, "UIC Pros") or "").strip()
        dto["uicCons"] = str(_field(fields, "UIC Cons") or "").strip()
        dto["reviewStatus"] = str(fields.get(LIVE_REVIEW_STATUS_FIELD) or "").strip()

    return dto
