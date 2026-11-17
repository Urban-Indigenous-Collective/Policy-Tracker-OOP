#!/usr/bin/env python3
"""One-off: re-analyze justice.gov empty-shell URLs after bot-wall fetch fix.

Airtable token cannot DELETE Pending rows, so junk Executive Order stubs are
updated in place. Rejected doc_empty URLs get new Pending records created.
Clears seen rows, purges short document_text cache, runs
DiscoveryPipeline._process_candidate with live LLM. Slack only for newly good
Pending items with real titles.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from airtable_client import AirtableClient
from airtable_coercion import coerce_bill_fields
from airtable_fields import BILL_OVERVIEW_LINK_FIELD, REVIEW_STATUS_PENDING
from discovery.models import Candidate
from discovery.pipeline import DiscoveryPipeline, DiscoveryRunStats
from discovery.seen_store import SeenStore
from discovery.url_utils import normalize_url
from document_text_store import DocumentTextStore, is_usable_cached_text
from main_application import MainApplication
from slack_client import SlackNotifier

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("reprocess_doj")

STUB_TITLES = frozenset({"executive order", "untitled", ""})

DEFAULT_URLS_PATH = Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")).parent / "doj_reprocess_urls.json"
RESULT_PATH = Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")).parent / "doj_reprocess_result.json"


def _title_of(fields: dict) -> str:
    return (fields.get("Name") or fields.get("Title") or "").strip()


def _is_stub_title(title: str) -> bool:
    return title.strip().lower() in STUB_TITLES


def _load_urls(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("urls") or []
    urls = []
    seen: set[str] = set()
    for item in raw:
        u = (item if isinstance(item, str) else (item or {}).get("url") or "").strip()
        if not u or u.lower() in seen:
            continue
        seen.add(u.lower())
        urls.append(u)
    return urls


def _purge_short_cache(store: DocumentTextStore, url: str) -> str:
    row = store.get(url)
    if not row:
        return "none"
    text = row.get("decoded_text") or ""
    if is_usable_cached_text(text):
        return f"kept:{row.get('char_len')}"
    store.delete(url)
    return f"purged:{row.get('char_len')}"


def _delete_seen(db_path: str, url: str) -> str:
    key = url.strip().lower()
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, verdict FROM seen_candidates WHERE url = ?", (key,)
        ).fetchone()
        if not row:
            return "none"
        conn.execute("DELETE FROM seen_candidates WHERE url = ?", (key,))
        conn.commit()
        return f"deleted:{row[0]}/{row[1]}"


def _find_pending(airtable: AirtableClient, url: str) -> list[dict]:
    rec = airtable.find_by_url(airtable.pending_table, url, field=BILL_OVERVIEW_LINK_FIELD)
    return [rec] if rec else []


def _pending_update_fields(bill_data: dict, *, confidence: float, rationale: str, discovered_on: str) -> dict:
    fields = coerce_bill_fields(bill_data)
    if not fields.get("Categories"):
        fields.pop("Categories", None)
    fields.update(
        {
            "Review Status": REVIEW_STATUS_PENDING,
            "Source": "Federal Site",
            "Relevance Confidence": confidence,
            "Relevance Rationale": rationale,
            "Discovered On": discovered_on,
        }
    )
    if "Validation Warnings" in bill_data and "Validation Warnings" not in fields:
        fields["Validation Warnings"] = bill_data.get("Validation Warnings") or ""
    return fields


def main() -> int:
    load_dotenv(ROOT / ".env")
    urls_path = Path(os.getenv("DOJ_REPROCESS_URLS", str(DEFAULT_URLS_PATH)))
    urls = _load_urls(urls_path)
    if not urls:
        logger.error("No URLs in %s", urls_path)
        return 1

    os.environ.setdefault("DISCOVERY_MAX_ANALYSES_PER_RUN", "50")
    os.environ["SLACK_DEFER_DISCOVERY"] = "false"

    legiscan_key = os.getenv("LEGISCAN_KEY")
    if not legiscan_key:
        logger.error("LEGISCAN_KEY must be set")
        return 1

    db_path = os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")
    doc_db = os.getenv("DOCUMENT_TEXT_DB_PATH", "data/document_text.db")
    doc_store = DocumentTextStore(doc_db)
    airtable = AirtableClient()
    app = MainApplication(legiscan_key)
    pipeline = DiscoveryPipeline(
        main_app=app,
        seen_store=SeenStore(db_path),
        airtable=airtable,
        slack=SlackNotifier(),
        dry_run=False,
    )
    pipeline.max_analyses = max(pipeline.max_analyses, 50)

    results: list[dict] = []
    to_process: list[str] = []
    stub_pending_by_url: dict[str, str] = {}  # url -> record id to update in place

    logger.info("Preparing %d URLs (purge cache, Pending stubs, seen rows)", len(urls))
    for url in urls:
        entry: dict = {"url": url, "action": ""}
        cache_action = _purge_short_cache(doc_store, url)
        pending_recs = _find_pending(airtable, url)
        stub_id = None
        kept_ids: list[str] = []
        for rec in pending_recs:
            fields = rec.get("fields") or {}
            title = _title_of(fields)
            entry["pending_before"] = {
                "id": rec.get("id"),
                "title": title,
                "summary_len": len((fields.get("Summary") or "")),
            }
            if _is_stub_title(title):
                stub_id = rec["id"]
                logger.info("Will update stub Pending %s in place for %s", stub_id, url)
            else:
                kept_ids.append(rec["id"])
                logger.info("Keeping good Pending %s (%r) for %s", rec["id"], title[:80], url)

        if kept_ids and not stub_id:
            entry["action"] = "skip_already_good"
            entry["pending_ids"] = kept_ids
            entry["cache"] = cache_action
            results.append(entry)
            continue

        seen_action = _delete_seen(db_path, url)
        entry["cache"] = cache_action
        entry["seen"] = seen_action
        if stub_id:
            stub_pending_by_url[url.strip().lower()] = stub_id
            entry["update_pending_id"] = stub_id
        entry["action"] = "reprocess"
        results.append(entry)
        to_process.append(url)

    # Load duplicate index, then unregister URLs we are about to rewrite so
    # stubs don't block re-analysis.
    pipeline.duplicate_index.refresh()
    for url in to_process:
        norm = normalize_url(url)
        if norm:
            pipeline.duplicate_index._urls.discard(norm)

    # Patch create_pending_record to UPDATE stub rows in place.
    original_create = airtable.create_pending_record
    current_url: dict[str, str] = {"url": ""}

    def create_or_update_pending(
        bill_data,
        source,
        relevance_confidence,
        relevance_rationale,
        discovered_on,
    ):
        overview = (
            (bill_data or {}).get("Bill Overview (Link)")
            or (bill_data or {}).get("Bill Overview")
            or current_url["url"]
            or ""
        )
        keys = {
            overview.strip().lower(),
            normalize_url(overview) or "",
            current_url["url"].strip().lower(),
            normalize_url(current_url["url"]) or "",
        }
        stub_id = None
        for key in keys:
            if key and key in stub_pending_by_url:
                stub_id = stub_pending_by_url[key]
                break
        if stub_id:
            fields = _pending_update_fields(
                bill_data,
                confidence=relevance_confidence,
                rationale=relevance_rationale,
                discovered_on=discovered_on,
            )
            if source:
                fields["Source"] = source
            updated = airtable.update_record(airtable.pending_table, stub_id, fields)
            logger.info("Updated stub Pending in place id=%s url=%s", stub_id, overview[:80])
            return updated
        return original_create(
            bill_data=bill_data,
            source=source,
            relevance_confidence=relevance_confidence,
            relevance_rationale=relevance_rationale,
            discovered_on=discovered_on,
        )

    airtable.create_pending_record = create_or_update_pending  # type: ignore[method-assign]

    stats = DiscoveryRunStats()
    logger.info(
        "Processing %d URLs through DiscoveryPipeline (max_analyses=%d, stubs_in_place=%d)",
        len(to_process),
        pipeline.max_analyses,
        len(stub_pending_by_url),
    )
    for i, url in enumerate(to_process, 1):
        logger.info("[%d/%d] %s", i, len(to_process), url)
        current_url["url"] = url
        slug = url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
        candidate = Candidate(
            source="federal_site",
            state="US",
            url=url,
            title=slug.title(),
            snippet="Missing and Murdered Indigenous Persons MMIP",
        )
        before_analyzed = stats.analyzed
        before_rejected = stats.rejected
        before_errors = stats.errors
        before_skipped = stats.skipped
        before_slack = len(stats.slack_items)
        try:
            pipeline._process_candidate(candidate, stats)
        except Exception as exc:
            logger.exception("Unhandled error for %s: %s", url, exc)
            for r in results:
                if r["url"] == url:
                    r["result"] = "exception"
                    r["error"] = str(exc)
            continue

        for r in results:
            if r["url"] != url:
                continue
            if stats.analyzed > before_analyzed:
                item = stats.slack_items[before_slack] if len(stats.slack_items) > before_slack else {}
                title = (item.get("title") or "").strip()
                pend = _find_pending(airtable, url)
                r["result"] = "pending_ok"
                r["title"] = title
                r["pending_ids"] = [p["id"] for p in pend] or (
                    [r["update_pending_id"]] if r.get("update_pending_id") else []
                )
                r["empty_title"] = _is_stub_title(title)
            elif stats.rejected > before_rejected:
                seen = pipeline.seen_store.get(url) or {}
                r["result"] = "rejected"
                r["verdict"] = seen.get("verdict")
            elif stats.errors > before_errors:
                seen = pipeline.seen_store.get(url) or {}
                r["result"] = "error"
                r["verdict"] = seen.get("verdict")
            elif stats.skipped > before_skipped:
                r["result"] = "skipped"
                seen = pipeline.seen_store.get(url) or {}
                r["verdict"] = seen.get("verdict") or seen.get("status")
            else:
                r["result"] = "llm_retry_or_noop"
                r["llm_errors"] = stats.llm_errors
            break

    good_items = [
        item
        for item in stats.slack_items
        if not _is_stub_title((item.get("title") or "").strip())
    ]
    slack_sent = False
    if good_items:
        slack_sent = bool(pipeline.slack.notify_discovery_batch(good_items))
        logger.info("Slack digest sent=%s for %d items", slack_sent, len(good_items))
    else:
        logger.info("No newly good Pending items — Slack not sent")

    summary = {
        "urls_total": len(urls),
        "reprocessed": len(to_process),
        "skipped_already_good": sum(1 for r in results if r.get("action") == "skip_already_good"),
        "pending_ok": sum(1 for r in results if r.get("result") == "pending_ok"),
        "pending_empty_title": sum(
            1 for r in results if r.get("result") == "pending_ok" and r.get("empty_title")
        ),
        "rejected": sum(1 for r in results if r.get("result") == "rejected"),
        "errors": sum(1 for r in results if r.get("result") == "error"),
        "still_emptyish": sum(
            1
            for r in results
            if r.get("empty_title")
            or (
                r.get("result") == "rejected"
                and str(r.get("verdict") or "").startswith("doc_")
            )
        ),
        "slack_sent": slack_sent,
        "slack_item_count": len(good_items),
        "stats": {
            "analyzed": stats.analyzed,
            "rejected": stats.rejected,
            "skipped": stats.skipped,
            "errors": stats.errors,
            "llm_errors": stats.llm_errors,
        },
        "results": results,
    }
    RESULT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("Wrote %s", RESULT_PATH)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
    for r in results:
        print(
            f"{r.get('result') or r.get('action'):20} "
            f"pending={r.get('pending_ids') or r.get('update_pending_id')} "
            f"title={r.get('title')!r} verdict={r.get('verdict')} {r['url']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
