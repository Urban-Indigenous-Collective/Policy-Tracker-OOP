#!/usr/bin/env python3
"""Per-state HTTP validation + MMIP prescreen crawl audit."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dotenv import load_dotenv

from discovery.site_crawler import StateSiteSource
from discovery.source_schema import StateManifest, StateSource
from validate_state_sources import check_source

MANIFESTS_DIR = ROOT / "sources" / "manifests"
REPORT_PATH = ROOT / "sources" / "audit_report.md"


@dataclass
class SourceAudit:
    name: str
    method: str
    validate_ok: bool
    validate_detail: str
    mmip_candidates: int = 0
    crawl_error: str = ""


@dataclass
class StateAudit:
    state: str
    sources: list[SourceAudit] = field(default_factory=list)

    @property
    def validate_pass(self) -> int:
        return sum(1 for s in self.sources if s.validate_ok)

    @property
    def mmip_total(self) -> int:
        return sum(s.mmip_candidates for s in self.sources)


def load_state_sources(state: str) -> list[StateSource]:
    path = MANIFESTS_DIR / f"{state}.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return StateManifest.model_validate(json.load(f)).sources


def audit_source(
    source: StateSource,
    max_queries: int,
    include_review: bool,
    delay: float,
) -> SourceAudit:
    ok, detail = check_source(source)
    crawl = source.model_copy(deep=True)
    if crawl.method in ("search", "api") and max_queries > 0:
        crawl.search_queries = (crawl.search_queries or ["MMIP"])[:max_queries]

    temp = ROOT / "sources" / f".audit_{source.state}_{source.source_id}.json"
    temp.write_text(json.dumps({"sources": [crawl.model_dump()]}), encoding="utf-8")
    mmip = 0
    crawl_err = ""
    try:
        crawler = StateSiteSource(
            sources_path=temp,
            include_review_needed=include_review,
            per_domain_delay=delay,
        )
        mmip = sum(1 for _ in crawler.discover())
    except Exception as exc:
        crawl_err = str(exc)[:120]
    finally:
        temp.unlink(missing_ok=True)

    return SourceAudit(
        name=source.name,
        method=source.method,
        validate_ok=ok,
        validate_detail=detail,
        mmip_candidates=mmip,
        crawl_error=crawl_err,
    )


def audit_state(
    state: str,
    max_queries: int,
    include_review: bool,
    only_enabled: bool,
    delay: float,
) -> StateAudit:
    sources = load_state_sources(state)
    if only_enabled:
        sources = [s for s in sources if not s.review_needed]
    audit = StateAudit(state=state)
    for source in sources:
        if source.review_needed and not include_review:
            continue
        audit.sources.append(
            audit_source(source, max_queries, include_review=True, delay=delay)
        )
    return audit


def write_report(results: list[StateAudit], path: Path) -> None:
    lines = [
        "# State Source Audit Report",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "HTTP smoke test + MMIP keyword prescreen per source (2 search queries max by default).",
        "",
        "## Summary",
        "",
        "| State | Sources | Validate OK | MMIP candidates |",
        "|-------|---------|-------------|-----------------|",
    ]
    for audit in sorted(results, key=lambda a: a.state):
        if not audit.sources:
            lines.append(f"| {audit.state} | 0 | — | — |")
            continue
        lines.append(
            f"| {audit.state} | {len(audit.sources)} | "
            f"{audit.validate_pass}/{len(audit.sources)} | {audit.mmip_total} |"
        )

    lines.extend(["", "## Per-state detail", ""])
    for audit in sorted(results, key=lambda a: a.state):
        lines.append(f"### {audit.state}")
        if not audit.sources:
            lines.append("")
            lines.append("_No sources configured._")
            lines.append("")
            continue
        for src in audit.sources:
            mark = "OK" if src.validate_ok else "FAIL"
            lines.append(
                f"- **[{mark}]** `{src.method}` {src.name} — "
                f"validate: {src.validate_detail}; MMIP links: {src.mmip_candidates}"
            )
            if src.crawl_error:
                lines.append(f"  - crawl error: {src.crawl_error}")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Audit state sources per state")
    parser.add_argument("--state", help="Limit to one state code")
    parser.add_argument(
        "--max-queries",
        type=int,
        default=2,
        help="Max search/API queries per source (default: 2)",
    )
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip sources still marked review_needed=true",
    )
    parser.add_argument(
        "--enabled-only",
        action="store_true",
        help="Only audit approved sources (review_needed=false)",
    )
    parser.add_argument("--report", default=str(REPORT_PATH))
    args = parser.parse_args()

    states = [args.state.upper()] if args.state else sorted(
        p.stem for p in MANIFESTS_DIR.glob("*.json")
    )
    delay = float(os.getenv("CRAWLER_AUDIT_DELAY", "1.0"))
    include_review = not args.skip_review and not args.enabled_only

    results: list[StateAudit] = []
    for state in states:
        print(f"Auditing {state}...", flush=True)
        audit = audit_state(
            state,
            max_queries=args.max_queries,
            include_review=include_review,
            only_enabled=args.enabled_only,
            delay=delay,
        )
        results.append(audit)
        if audit.sources:
            print(
                f"  {audit.validate_pass}/{len(audit.sources)} validate OK, "
                f"{audit.mmip_total} MMIP candidate(s)",
                flush=True,
            )
        else:
            print("  no sources", flush=True)

    write_report(results, Path(args.report))
    print(f"\nReport written to {args.report}")


if __name__ == "__main__":
    main()
