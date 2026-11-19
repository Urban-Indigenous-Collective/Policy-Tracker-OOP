#!/usr/bin/env python3
"""Compare automated (creation-time) Pending values with the corrected/approved rows.

Baseline sources (creation-time entries always win over snapshot seeds):
  * ``<data>/automated_baseline/pending-created-*.jsonl`` written by the pipeline
  * ``--baseline-snapshot`` Pending snapshot files (pre-existing records; may already
    contain reviewer edits, flagged ``baseline_kind=snapshot`` in the output)

Current rows come from ``--current`` snapshot files or ``--fetch`` (live Airtable).

Examples:
  # Offline, using local backups
  python scripts/compare_automated_vs_corrected.py \\
      --baseline-snapshot data/backups/pending-pre-independent-analysis-apply.json \\
      --current data/backups/airtable-pre-numeral-cleanup-20261119T161547Z.json \\
      --approved-only --output /tmp/automated_vs_corrected.json

  # On prod, inside the existing container (read-only against Airtable)
  docker compose exec scheduler python scripts/compare_automated_vs_corrected.py \\
      --fetch --approved-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

import automated_baseline as ab


def _fetch_current() -> list[tuple[str, dict]]:
    from airtable_client import AirtableClient

    client = AirtableClient()
    pairs = [("Pending", record) for record in client.pending_table.all()]
    pairs.extend(("Live", record) for record in client.all_live_records())
    return pairs


def _short(value, limit: int = 160) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_markdown(report: dict) -> str:
    lines = [
        "# Automated vs corrected",
        "",
        f"- Baseline entries: {report['baseline_count']}",
        f"- Current rows considered: {report['current_count']}",
        f"- Matched: {report['matched']} "
        f"({report['matched_with_changes']} changed, {report['matched_unchanged']} unchanged)",
        "",
        "## Fields changed",
        "",
    ]
    if report["field_change_counts"]:
        lines += [f"- {name}: {count}" for name, count in report["field_change_counts"].items()]
    else:
        lines.append("- (none)")
    for item in report["records"]:
        if not item["changed"]:
            continue
        lines += [
            "",
            f"## {item['bill'] or item['identity']} — {item['current_table']} "
            f"({item['current_review_status']}), baseline={item['baseline_kind']}",
        ]
        for name, diff in item["changed"].items():
            lines += [
                f"- **{name}**",
                f"  - automated: {_short(diff['automated'])}",
                f"  - current:   {_short(diff['current'])}",
            ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline-dir", default="", help="Override automated_baseline directory")
    parser.add_argument(
        "--baseline-snapshot",
        action="append",
        default=[],
        help="Pending snapshot JSON used for records with no creation-time entry (repeatable)",
    )
    parser.add_argument("--current", action="append", default=[], help="Airtable snapshot JSON (repeatable)")
    parser.add_argument("--fetch", action="store_true", help="Fetch current Pending + Live from Airtable")
    parser.add_argument("--approved-only", action="store_true", help="Only compare against Live (approved) rows")
    parser.add_argument(
        "--include-volatile",
        action="store_true",
        help="Also compare status/progression/workflow fields that change without human edits",
    )
    parser.add_argument("--output", default="", help="Write full JSON report here")
    parser.add_argument("--markdown", default="", help="Write a readable markdown report here")
    args = parser.parse_args()

    if not args.current and not args.fetch:
        parser.error("provide --current snapshot file(s) or --fetch")

    load_dotenv(ROOT / ".env")

    directory = Path(args.baseline_dir) if args.baseline_dir else None
    baseline = ab.baseline_from_snapshots(Path(p) for p in args.baseline_snapshot)
    baseline.update(ab.load_baseline(directory))  # creation-time entries override snapshot seeds

    current: list[tuple[str, dict]] = []
    for path in args.current:
        current.extend(ab.snapshot_tables(Path(path)))
    if args.fetch:
        current.extend(_fetch_current())

    report = ab.compare_to_current(
        baseline,
        current,
        include_volatile=args.include_volatile,
        approved_only=args.approved_only,
    )

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote JSON report to {args.output}")
    if args.markdown:
        Path(args.markdown).write_text(render_markdown(report), encoding="utf-8")
        print(f"Wrote markdown report to {args.markdown}")
    if not args.output and not args.markdown:
        print(render_markdown(report))

    print(
        f"Summary: baseline={report['baseline_count']} matched={report['matched']} "
        f"changed={report['matched_with_changes']} unchanged={report['matched_unchanged']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
