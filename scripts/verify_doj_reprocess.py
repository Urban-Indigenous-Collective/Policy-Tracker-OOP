#!/usr/bin/env python3
"""Verify DOJ reprocess Pending rows and Slack the early batch of 3."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from airtable_client import AirtableClient
from slack_client import SlackNotifier

load_dotenv(ROOT / ".env")

DATA = Path("/app/data")
URLS = json.loads((DATA / "doj_reprocess_urls.json").read_text())
EARLY = [
    "https://www.justice.gov/archives/opa/pr/attorney-general-william-p-barr-launches-national-strategy-address-missing-and-murdered",
    "https://www.justice.gov/archives/opa/pr/department-justice-collaborates-canadian-and-mexican-partners-programs-and-best-practices",
    "https://www.justice.gov/archives/opa/pr/justice-and-interior-departments-outline-commitment-next-steps-effort-address-missing-or",
]


def main() -> int:
    client = AirtableClient()
    rows = client.pending_table.all()
    idx: dict[str, list] = {}
    for rec in rows:
        fields = rec.get("fields") or {}
        url = (fields.get("Bill Overview (Link)") or "").strip().lower()
        if url:
            idx.setdefault(url, []).append(rec)

    report = []
    empty = missing = multi = 0
    for url in URLS:
        recs = idx.get(url.strip().lower()) or []
        if not recs:
            missing += 1
            report.append({"url": url, "status": "MISSING", "pending_ids": [], "title": ""})
            continue
        if len(recs) > 1:
            multi += 1
        titles = []
        ids = []
        for rec in recs:
            fields = rec.get("fields") or {}
            title = (fields.get("Name") or fields.get("Title") or "").strip()
            titles.append(title)
            ids.append(rec["id"])
        title = titles[0]
        is_empty = title.lower() in ("executive order", "untitled", "")
        if is_empty:
            empty += 1
        report.append(
            {
                "url": url,
                "status": "EMPTY" if is_empty else "OK",
                "pending_ids": ids,
                "title": title,
            }
        )

    early_items = []
    for url in EARLY:
        recs = idx.get(url.strip().lower()) or []
        if not recs:
            continue
        fields = recs[0].get("fields") or {}
        early_items.append(
            {
                "state": fields.get("State") or "US",
                "title": fields.get("Name") or "",
                "summary": (fields.get("Summary") or "")[:300],
                "categories": fields.get("Categories") or "",
                "confidence": fields.get("Relevance Confidence") or 0,
                "source_url": fields.get("Bill Overview (Link)") or url,
                "pending_url": "",
            }
        )
    slack_early = bool(SlackNotifier().notify_discovery_batch(early_items)) if early_items else False

    out = {
        "urls_total": len(URLS),
        "ok": sum(1 for row in report if row["status"] == "OK"),
        "empty": empty,
        "missing": missing,
        "multi": multi,
        "slack_run2_items": 33,
        "slack_early3": slack_early,
        "slack_early_count": len(early_items),
        "rows": report,
    }
    (DATA / "doj_reprocess_final_report.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))
    for row in report:
        print(f"{row['status']:7} {row['pending_ids']} {(row['title'] or '')[:70]!r}")
        print(f"        {row['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
