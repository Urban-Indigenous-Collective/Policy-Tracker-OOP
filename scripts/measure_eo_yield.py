#!/usr/bin/env python3
"""Measure crawl yield across enabled executive_order + proclamation sources.

Crawl-only: no LLM, no Airtable, no Pending writes. Emits a JSON report with
per-source link counts, page-fetch counts, and every prescreen hit.
"""

import argparse
import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.site_crawler import StateSiteSource  # noqa: E402
from discovery.source_schema import load_sources_data  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

DEFAULT_TYPES = ("executive_order", "proclamation")


def crawl_one(
    sources_path: str,
    source_id: str,
    include_review: bool,
    delay: float,
    max_pages: int = 0,
) -> dict:
    crawler = StateSiteSource(
        sources_path=sources_path,
        source_id_filter=source_id,
        include_review_needed=include_review,
        per_domain_delay=delay,
    )
    if max_pages:
        real_load = crawler.load_sources

        def capped_load():
            loaded = real_load()
            for src in loaded:
                src.max_pages = max_pages
            return loaded

        crawler.load_sources = capped_load  # type: ignore[method-assign]
    stats = {"links": 0, "pages": 0, "fetch_bytes": 0}
    lock = threading.Lock()

    real_extract = crawler.http.extract_links
    real_fetch = crawler.http.fetch

    def counting_extract(*args, **kwargs):
        out = real_extract(*args, **kwargs)
        with lock:
            stats["links"] += len(out)
        return out

    def counting_fetch(*args, **kwargs):
        body, digest = real_fetch(*args, **kwargs)
        with lock:
            stats["pages"] += 1
            stats["fetch_bytes"] += len(body or "")
        return body, digest

    crawler.http.extract_links = counting_extract  # type: ignore[method-assign]
    crawler.http.fetch = counting_fetch  # type: ignore[method-assign]

    started = time.time()
    candidates = []
    error = ""
    try:
        for cand in crawler.discover():
            candidates.append(
                {
                    "state": cand.state,
                    "url": cand.url,
                    "title": (cand.title or "")[:200],
                    "snippet": (cand.snippet or "")[:300],
                }
            )
    except Exception as exc:  # noqa: BLE001 - report, don't abort the sweep
        error = f"{type(exc).__name__}: {exc}"
    return {
        "source_id": source_id,
        "links": stats["links"],
        "pages": stats["pages"],
        "bytes": stats["fetch_bytes"],
        "elapsed_s": round(time.time() - started, 1),
        "candidates": candidates,
        "error": error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", default=str(ROOT / "sources" / "state_sources.json"))
    parser.add_argument("--out", required=True, help="Path for the JSON report")
    parser.add_argument("--types", default=",".join(DEFAULT_TYPES))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--delay", type=float, default=1.5, help="Per-domain delay seconds")
    parser.add_argument("--include-review", action="store_true")
    parser.add_argument("--state", default="", help="Optional two-letter filter")
    parser.add_argument("--source-id", default="", help="Optional single source_id")
    parser.add_argument("--label", default="run")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Override every source's max_pages (0 = use each source's own value)",
    )
    args = parser.parse_args()

    wanted_types = {t.strip() for t in args.types.split(",") if t.strip()}
    with open(args.sources, encoding="utf-8") as fh:
        all_sources = load_sources_data(json.load(fh))

    selected = [
        s
        for s in all_sources
        if s.content_type in wanted_types
        and (args.include_review or not s.review_needed)
        and (not args.state or s.state == args.state.upper())
        and (not args.source_id or s.source_id == args.source_id)
    ]
    meta = {s.source_id: s for s in selected}
    print(f"[{args.label}] crawling {len(selected)} sources with {args.workers} workers")

    results = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                crawl_one,
                args.sources,
                s.source_id,
                args.include_review,
                args.delay,
                args.max_pages,
            ): s
            for s in selected
        }
        for done, fut in enumerate(as_completed(futures), start=1):
            src = futures[fut]
            row = fut.result()
            row["state"] = src.state
            row["name"] = src.name
            row["content_type"] = src.content_type
            row["url"] = src.primary_url()
            results.append(row)
            print(
                f"  [{done}/{len(selected)}] {src.source_id:50} "
                f"links={row['links']:5} pages={row['pages']:3} hits={len(row['candidates'])}"
                + (f" ERR={row['error'][:80]}" if row["error"] else "")
            )

    results.sort(key=lambda r: (r["state"], r["source_id"]))
    total_links = sum(r["links"] for r in results)
    total_pages = sum(r["pages"] for r in results)
    hits = [c | {"source_id": r["source_id"]} for r in results for c in r["candidates"]]
    distinct = {}
    for h in hits:
        distinct.setdefault(h["url"], h)

    report = {
        "label": args.label,
        "sources_path": args.sources,
        "max_pages_override": args.max_pages,
        "sources_crawled": len(results),
        "dead_sources": [r["source_id"] for r in results if r["pages"] and r["links"] == 0],
        "total_links": total_links,
        "total_pages": total_pages,
        "total_hits": len(hits),
        "distinct_hits": len(distinct),
        "elapsed_s": round(time.time() - started, 1),
        "results": results,
        "distinct_hit_list": sorted(distinct.values(), key=lambda h: (h["state"], h["url"])),
    }
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"\n[{args.label}] sources={len(results)} links={total_links} pages={total_pages} "
        f"hits={len(hits)} distinct={len(distinct)} in {report['elapsed_s']}s -> {args.out}"
    )
    for h in report["distinct_hit_list"]:
        print(f"  {h['state']:3} {h['title'][:70]:72} {h['url']}")


if __name__ == "__main__":
    main()
