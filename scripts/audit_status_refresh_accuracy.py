#!/usr/bin/env python3
"""Audit status refresh accuracy: Airtable vs LegiScan ground truth."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, BILL_TEXT_FIELD, REVIEW_STATUS_REJECTED
from api_client import APIClient
from discovery.status_refresh import StatusRefreshPipeline, _year_from_fields
from legiscan_processor import LegiScanProcessor, normalize_bill_number, parse_legiscan_bill_url

TRACKED = ("Status", "Progression", "Chamber", "Chamber Details", "Last Update")


@dataclass
class AuditRow:
    table: str
    record_id: str
    name: str
    state: str
    bill_number: str
    session: str
    overview: str
    resolved_bill_id: str = ""
    legiscan_bill_number: str = ""
    legiscan_session: str = ""
    legiscan_title: str = ""
    legiscan_url: str = ""
    field_mismatches: dict[str, dict[str, str]] = field(default_factory=dict)
    identity_issues: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


class AuditPipeline:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.airtable = AirtableClient()
        self.api = APIClient(os.environ["LEGISCAN_KEY"])
        self.legiscan = LegiScanProcessor(indigenous_db=None, api_client=self.api)
        self.seen_store = None
        from discovery.seen_store import SeenStore

        self.seen_store = SeenStore(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))

    def _record_url(self, fields: dict[str, Any]) -> str:
        return fields.get(BILL_OVERVIEW_LINK_FIELD) or fields.get("Bill Overview") or fields.get(BILL_TEXT_FIELD) or ""

    def _resolve(self, fields: dict[str, Any], url: str) -> str | None:
        from discovery.status_refresh import StatusRefreshPipeline

        pipe = StatusRefreshPipeline(self.api, self.legiscan, self.airtable, self.seen_store, dry_run=True)
        return pipe._resolve_bill_id_for_record(fields, url)

    def audit_record(self, record: dict, table: str) -> AuditRow | None:
        fields = record.get("fields") or {}
        url = self._record_url(fields)
        if not url and not (fields.get("State") and fields.get("Bill Number")):
            return None
        if url and not self.legiscan.is_legiscan_url(url) and not fields.get("Bill Number"):
            return None

        row = AuditRow(
            table=table,
            record_id=record["id"],
            name=str(fields.get("Name") or ""),
            state=str(fields.get("State") or ""),
            bill_number=str(fields.get("Bill Number") or ""),
            session=str(fields.get("Session") or ""),
            overview=url,
        )

        bill_id = self._resolve(fields, url)
        if not bill_id:
            row.flags.append("unresolved_bill_id")
            return row

        details = self.api.get_bill_details(bill_id)
        if not details or "bill" not in details:
            row.flags.append("getbill_failed")
            return row

        bill = details["bill"]
        fresh = self.legiscan.extract_status_fields(details)
        row.resolved_bill_id = bill_id
        row.legiscan_bill_number = str(bill.get("bill_number") or "")
        session_obj = bill.get("session") or {}
        row.legiscan_session = (
            session_obj.get("session_title", "") if isinstance(session_obj, dict) else str(session_obj)
        )
        row.legiscan_title = str(bill.get("title") or bill.get("description") or "")
        row.legiscan_url = self.legiscan.get_bill_link(bill)

        airtable_norm = normalize_bill_number(row.bill_number)
        legiscan_norm = normalize_bill_number(row.legiscan_bill_number)
        if airtable_norm and legiscan_norm and airtable_norm != legiscan_norm:
            row.identity_issues.append(
                f"bill_number mismatch: airtable={row.bill_number} legiscan={row.legiscan_bill_number}"
            )

        if row.state and bill.get("state"):
            airtable_state = row.state.strip().upper()
            legiscan_state = str(bill.get("state")).strip().upper()
            equivalent = {airtable_state, legiscan_state}
            if airtable_state != legiscan_state and equivalent != {"NATIONAL", "US"}:
                row.identity_issues.append(
                    f"state mismatch: airtable={row.state} legiscan={bill.get('state')}"
                )

        parsed = parse_legiscan_bill_url(url) if url else None
        if parsed and row.legiscan_bill_number:
            _, _, url_year = parsed
            session_year = _year_from_fields(fields, url)
            if session_year and row.legiscan_session and str(session_year) not in row.legiscan_session:
                row.flags.append("session_year_mismatch")

        for name in TRACKED:
            old = str(fields.get(name, "") or "")
            new = str(fresh.get(name, "") or "")
            if old != new:
                row.field_mismatches[name] = {"airtable": old, "legiscan": new}

        if str(fields.get("Status") or "") == "Passed" and fresh.get("Status") == "Failed":
            row.flags.append("passed_to_failed_risk")
        if str(fields.get("Progression") or "") in ("Progression", "Unknown Status", ""):
            row.flags.append("placeholder_progression")

        title_blob = (row.name + " " + row.legiscan_title).lower()
        if "ida" in title_blob and "law" in title_blob:
            if row.bill_number == "HB2733" and fresh.get("Status") == "Failed":
                row.flags.append("idas_law_house_failed_companion")
            if row.bill_number == "SB172" and fresh.get("Status") == "Passed":
                row.flags.append("idas_law_passed_canonical")

        return row

    def run(self) -> dict[str, Any]:
        rows: list[AuditRow] = []
        for record in self.airtable.list_pending_for_refresh():
            if (record.get("fields") or {}).get("Review Status") == REVIEW_STATUS_REJECTED:
                continue
            row = self.audit_record(record, "Pending")
            if row:
                rows.append(row)
        for record in self.airtable.all_live_records():
            row = self.audit_record(record, "Live")
            if row:
                rows.append(row)

        by_table = defaultdict(int)
        mismatches = []
        identity = []
        flagged = []
        for row in rows:
            by_table[row.table] += 1
            if row.field_mismatches:
                mismatches.append(row)
            if row.identity_issues:
                identity.append(row)
            if row.flags:
                flagged.append(row)

        ida_rows = [r for r in rows if "ida" in (r.name + r.legiscan_title).lower() and "law" in (r.name + r.legiscan_title).lower()]

        return {
            "summary": {
                "audited": len(rows),
                "pending": by_table["Pending"],
                "live": by_table["Live"],
                "field_mismatches": len(mismatches),
                "identity_issues": len(identity),
                "flagged": len(flagged),
            },
            "mismatches": [self._serialize(r) for r in mismatches],
            "identity_issues": [self._serialize(r) for r in identity],
            "flagged": [self._serialize(r) for r in flagged],
            "idas_law_records": [self._serialize(r) for r in ida_rows],
        }

    @staticmethod
    def _serialize(row: AuditRow) -> dict[str, Any]:
        return {
            "table": row.table,
            "record_id": row.record_id,
            "name": row.name,
            "state": row.state,
            "bill_number": row.bill_number,
            "session": row.session,
            "overview": row.overview,
            "resolved_bill_id": row.resolved_bill_id,
            "legiscan_bill_number": row.legiscan_bill_number,
            "legiscan_session": row.legiscan_session,
            "legiscan_title": row.legiscan_title,
            "legiscan_url": row.legiscan_url,
            "field_mismatches": row.field_mismatches,
            "identity_issues": row.identity_issues,
            "flags": row.flags,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()
    report = AuditPipeline().run()
    text = json.dumps(report, indent=2)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
