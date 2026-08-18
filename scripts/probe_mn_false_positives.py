#!/usr/bin/env python3
"""Trace how MN HF32/SF25 false positives entered Pending."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from api_client import APIClient
from content_guard import (
    check_legiscan_document_text,
    legiscan_junk_title_flags,
    screen_legiscan_document,
)
from discovery.queries import MMIP_QUERIES, keyword_prescreen, strip_mmip_query_contamination
from discovery.seen_store import SeenStore
from legiscan_processor import LegiScanProcessor

TARGETS = [
    ("recGHwmaGfyVkk9mg", "HF32", "2020", "https://legiscan.com/MN/bill/HF32/2020/X7"),
    ("recQuPGGvq3c4QDl2", "SF25", "2020", "https://legiscan.com/MN/bill/SF25/2020/X7"),
]


def _matching_queries(title: str, text: str) -> list[str]:
    blob = f"{title}\n{text}".lower()
    matched = []
    for query in MMIP_QUERIES:
        # Simulate LegiScan boolean loosely: check key terms from each query
        q = query.lower().strip('"')
        if " or " in q:
            parts = [p.strip('" ') for p in q.split(" or ")]
            if any(p in blob for p in parts):
                matched.append(query)
        elif " and " in q:
            parts = [p.strip('"() ') for p in q.split(" and ")]
            if all(any(term in blob for term in p.split()) for p in parts if p):
                matched.append(query)
        elif q.strip('"') in blob:
            matched.append(query)
    return matched


def main() -> int:
    api = APIClient(os.environ["LEGISCAN_KEY"])
    proc = LegiScanProcessor(None, api_client=api)
    store = SeenStore(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))

    for rid, bill_num, year, url in TARGETS:
        print(f"\n{'='*60}\n{rid} {bill_num}/{year}\n{'='*60}")
        bill_id = proc.resolve_bill_id(url)
        details = api.get_bill_details(bill_id) if bill_id else {}
        bill = details.get("bill") or {}
        title = str(bill.get("title") or "")
        excerpt = proc.get_bill_excerpt_for_relevance(url, bill_id=bill_id) if bill_id else ""

        cleaned = strip_mmip_query_contamination(f"{title}\n{excerpt}")
        print(f"title: {title}")
        print(f"excerpt_len: {len(excerpt)}")
        print(f"keyword_prescreen: {keyword_prescreen(cleaned)}")
        print(f"junk_title_flags: {legiscan_junk_title_flags(title)}")
        print(f"matching_queries: {_matching_queries(title, excerpt)}")
        print(f"screen_legiscan: {screen_legiscan_document(url, excerpt, title=title)}")
        print(f"check_legiscan_doc: {check_legiscan_document_text(excerpt, url, title=title)}")

        seen = store.get(url)
        print(f"seen_store: {json.dumps(dict(seen) if seen else None, default=str, indent=2)}")

        # LegiScan search relevance score from getSearchRaw
        for query in MMIP_QUERIES[:3]:
            pass  # skip full search — too many API calls

        if bill_id:
            for query in MMIP_QUERIES:
                for page in api.iter_search_raw_pages(query, state="MN", year=int(year)):
                    results = (page.get("searchresult") or {}).get("results") or []
                    if isinstance(results, dict):
                        results = list(results.values())
                    for item in results:
                        if str(item.get("bill_id")) == str(bill_id):
                            print(f"FOUND via query: {query!r} relevance={item.get('relevance')}")
                            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
