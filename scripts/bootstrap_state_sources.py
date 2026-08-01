#!/usr/bin/env python3
"""Bootstrap state_sources.json from non-federal entries in Main v3 Airtable."""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from airtable_client import AirtableClient  # noqa: E402

FEDERAL_STATES = {"national", "us", "u.s.", "federal", ""}
SKIP_DOMAINS = {"legiscan.com", "www.legiscan.com", "federalregister.gov", "www.federalregister.gov"}
URL_FIELDS = ["Bill Overview", "Bill Overview (Link)", "Bill Text", "Optional Link"]
OUTPUT_PATH = ROOT / "sources" / "state_sources.json"


def registrable_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def main():
    load_dotenv()
    client = AirtableClient()
    records = client.all_live_records()

    grouped: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"count": 0, "sample_urls": [], "state": ""}
    )

    for record in records:
        fields = record.get("fields") or {}
        state = str(fields.get("State") or "").strip()
        if state.lower() in FEDERAL_STATES:
            continue

        for field in URL_FIELDS:
            url = fields.get(field)
            if not url or not isinstance(url, str) or not url.startswith("http"):
                continue
            domain = registrable_domain(url)
            if any(skip in domain for skip in SKIP_DOMAINS):
                continue
            key = (state, domain)
            grouped[key]["count"] += 1
            grouped[key]["state"] = state
            if url not in grouped[key]["sample_urls"] and len(grouped[key]["sample_urls"]) < 5:
                grouped[key]["sample_urls"].append(url)

    sources = []
    for (state, domain), info in sorted(grouped.items(), key=lambda x: (-x[1]["count"], x[0][0])):
        sample = info["sample_urls"][0] if info["sample_urls"] else f"https://{domain}/"
        sources.append(
            {
                "state": state[:2].upper() if len(state) == 2 else state,
                "name": f"{state} — {domain}",
                "url": sample,
                "type": "index",
                "link_selector": None,
                "review_needed": True,
                "sample_urls": info["sample_urls"],
                "occurrence_count": info["count"],
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_from": "Main v3 Airtable (non-federal entries)",
        "note": "Edit urls to point at index/listing pages before setting review_needed=false",
        "sources": sources,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    print(f"Wrote {len(sources)} source entries to {OUTPUT_PATH}")
    print("Review and edit URLs to index pages, then set review_needed=false for each source.")


if __name__ == "__main__":
    main()
