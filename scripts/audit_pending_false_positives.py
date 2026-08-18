#!/usr/bin/env python3
"""Audit Pending rows for likely LegiScan false positives.

Dry-run by default. Scores each non-rejected Pending row using keyword
prescreen, content_guard LegiScan checks, and optional LLM MMIP relevance.

Usage:
  python scripts/audit_pending_false_positives.py
  python scripts/audit_pending_false_positives.py --llm --limit 30
  python scripts/audit_pending_false_positives.py --source LegiScan --llm
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from airtable_client import AirtableClient
from airtable_coercion import coerce_categories
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, BILL_TEXT_FIELD, REVIEW_STATUS_REJECTED
from api_client import APIClient
from content_guard import (
    check_legiscan_document_text,
    legiscan_junk_title_flags,
    legiscan_relevance_supported,
    screen_legiscan_document,
    title_has_mmip_nexus,
)
from discovery.models import Candidate
from discovery.queries import keyword_prescreen, strip_mmip_query_contamination
from discovery.relevance import MMIPRelevanceGate
from discovery.seen_store import SeenStore
from document_processor import DocumentProcessor
from legiscan_processor import LegiScanProcessor
from llm.factory import get_llm_provider

logging.basicConfig(level=os.getenv("LOG_LEVEL", "WARNING"))
logger = logging.getLogger(__name__)


def _record_url(fields: dict) -> str:
    return (
        fields.get(BILL_OVERVIEW_LINK_FIELD)
        or fields.get("Bill Overview")
        or fields.get(BILL_TEXT_FIELD)
        or ""
    )


def _categories_empty(fields: dict) -> bool:
    cats = coerce_categories(fields.get("Categories"))
    return not cats


def _seen_verdict(store: SeenStore, url: str) -> dict | None:
    if not url:
        return None
    row = store.get(url)
    if not row:
        return None
    return {
        "status": row.get("status"),
        "verdict": row.get("verdict"),
        "confidence": row.get("confidence"),
        "source": row.get("source"),
    }


def _fetch_excerpt(proc: LegiScanProcessor, doc: DocumentProcessor, url: str, bill_number: str, state: str) -> str:
    bill_id = proc.resolve_bill_id(url, state=state, bill_number=bill_number)
    if not bill_id:
        return ""
    return proc.get_bill_excerpt_for_relevance(url, bill_id=bill_id, document_processor=doc)


def audit_record(
    record: dict,
    proc: LegiScanProcessor,
    doc: DocumentProcessor,
    store: SeenStore,
    gate: MMIPRelevanceGate | None,
) -> dict:
    rid = record["id"]
    fields = record.get("fields") or {}
    name = str(fields.get("Name") or "")
    title = name
    url = _record_url(fields)
    source = str(fields.get("Source") or "")
    state = str(fields.get("State") or "")
    bill_number = str(fields.get("Bill Number") or "")

    excerpt = ""
    if source == "LegiScan" and url:
        excerpt = _fetch_excerpt(proc, doc, url, bill_number, state)

    combined = f"{title}\n{excerpt}"
    cleaned = strip_mmip_query_contamination(combined)
    kp = keyword_prescreen(cleaned)
    junk_flags = legiscan_junk_title_flags(title)
    title_mmip = title_has_mmip_nexus(title)

    guard_pre = screen_legiscan_document(url, excerpt, title=title) if excerpt else None
    guard_post = (
        check_legiscan_document_text(excerpt, url, title=title) if excerpt else None
    )
    text_supported = legiscan_relevance_supported(excerpt, title=title) if excerpt else None

    mmip = None
    is_relevant = None
    if gate and excerpt:
        candidate = Candidate(
            source="legiscan",
            state=state,
            url=url,
            title=title,
            snippet=excerpt[:500],
            bill_number=bill_number,
        )
        is_relevant, result, stage = gate.evaluate(candidate, excerpt=excerpt, prescreened=True)
        if result:
            mmip = {
                "is_mmip": result.is_mmip,
                "confidence": result.confidence,
                "rationale": result.rationale[:200],
                "stage": stage,
            }

    reasons: list[str] = []
    score = 0

    if _categories_empty(fields):
        reasons.append("empty_categories")
        score += 2
    if junk_flags and not title_mmip:
        reasons.append(f"junk_title:{','.join(junk_flags)}")
        score += 3
    if guard_pre and not guard_pre.ok:
        reasons.append(f"guard_pre:{guard_pre.code}")
        score += 4
    elif guard_post and not guard_post.ok:
        reasons.append(f"guard_post:{guard_post.code}")
        score += 4
    if not kp:
        reasons.append("no_keyword_prescreen")
        score += 2
    if is_relevant is False:
        reasons.append("llm_not_mmip")
        score += 5
    if not title_mmip and source == "LegiScan":
        reasons.append("title_no_mmip_nexus")
        score += 1

    seen = _seen_verdict(store, url)
    if seen and seen.get("verdict") == "analyzed":
        pass  # normal path

    return {
        "record_id": rid,
        "name": name[:80],
        "state": state,
        "bill_number": bill_number,
        "source": source,
        "url": url,
        "categories": coerce_categories(fields.get("Categories")),
        "relevance_confidence": fields.get("Relevance Confidence"),
        "relevance_rationale": str(fields.get("Relevance Rationale") or "")[:300],
        "discovered_on": fields.get("Discovered On"),
        "score": score,
        "reasons": reasons,
        "keyword_prescreen": kp,
        "junk_title_flags": junk_flags,
        "title_mmip_nexus": title_mmip,
        "guard_pre": guard_pre.code if guard_pre and not guard_pre.ok else None,
        "guard_post": guard_post.code if guard_post and not guard_post.ok else None,
        "text_supported": text_supported,
        "pipeline_would_block": bool(
            (guard_pre and not guard_pre.ok)
            or (guard_post and not guard_post.ok)
            or text_supported is False
        ),
        "mmip": mmip,
        "seen": seen,
        "recommendation": "reject" if score >= 5 else ("review" if score >= 3 else "keep"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="", help="Filter by Source field (e.g. LegiScan)")
    parser.add_argument("--llm", action="store_true", help="Run MMIP relevance LLM check")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-score", type=int, default=3, help="Only show rows at or above score")
    parser.add_argument("--record-id", action="append", default=[], dest="record_ids")
    args = parser.parse_args()

    client = AirtableClient()
    api = APIClient(os.environ["LEGISCAN_KEY"])
    proc = LegiScanProcessor(None, api_client=api)
    doc = DocumentProcessor(get_llm_provider())
    store = SeenStore(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db"))
    gate = MMIPRelevanceGate(get_llm_provider()) if args.llm else None

    rows: list[dict] = []
    if args.record_ids:
        records = []
        for rid in args.record_ids:
            records.append(client.pending_table.get(rid))
    else:
        records = client.pending_table.all()

    for record in records:
        fields = record.get("fields") or {}
        if fields.get("Review Status") == REVIEW_STATUS_REJECTED:
            continue
        if args.record_ids and record["id"] not in args.record_ids:
            continue
        if args.source and str(fields.get("Source") or "") != args.source:
            continue
        rows.append(audit_record(record, proc, doc, store, gate))

    rows.sort(key=lambda r: (-r["score"], r["state"], r["name"]))
    if args.min_score:
        rows = [r for r in rows if r["score"] >= args.min_score]
    if args.limit:
        rows = rows[: args.limit]

    reject = [r for r in rows if r["recommendation"] == "reject"]
    review = [r for r in rows if r["recommendation"] == "review"]

    print(f"scanned={len(rows)} reject_candidates={len(reject)} review={len(review)} llm={args.llm}")
    for row in rows:
        print(
            f"[{row['score']}] {row['record_id']} {row['state']} {row['bill_number']} "
            f"{row['name'][:50]!r} -> {row['recommendation']} ({', '.join(row['reasons'])})"
        )

    print("\n=== JSON ===")
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
