#!/usr/bin/env python3
"""Compare Indigenous Sponsorship fields between Airtable snapshot backups."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from airtable_fields import BILL_OVERVIEW_LINK_FIELD
from discovery.url_utils import bill_identity_key, normalize_url
from sponsor_utils import split_sponsors

INDIGENOUS_FIELD = "Indigenous Sponsorship"
SPONSORS_FIELD = "Sponsors of the Legislation"

CAREER_NOISE_MARKERS = (
    "speaker of the state house",
    "1995–present",
    "1995-present",
    "state representative 20",
    "state senator 19",
)

SPOT_CHECK_NAMES = (
    "Sharice Davids",
    "James Ramos",
    "Mary Kunesh",
    "Tyson Running Wolf",
    "Bryce Edgmon",
)


def _identity(record: dict) -> str:
    fields = record.get("fields") or {}
    url = fields.get(BILL_OVERVIEW_LINK_FIELD) or fields.get("Bill Overview") or ""
    normalized = normalize_url(url) if url else ""
    if normalized:
        return f"url:{normalized}"
    key = bill_identity_key(fields.get("State", ""), fields.get("Bill Number", ""))
    if key:
        return f"bill:{key[0]}:{key[1]}"
    return f"id:{record.get('id', 'unknown')}"


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _count_entries(value: str) -> int:
    text = _normalize(value)
    if not text:
        return 0
    return len(split_sponsors(text))


def _has_career_noise(value: str) -> bool:
    lowered = _normalize(value).lower()
    return any(marker in lowered for marker in CAREER_NOISE_MARKERS)


def _load_records(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") or []
    return {_identity(record): record for record in records}


def _classify_change(old_val: str, new_val: str) -> str:
    old_norm = _normalize(old_val)
    new_norm = _normalize(new_val)
    if old_norm == new_norm:
        return "unchanged"
    if old_norm and not new_norm:
        return "cleared"
    if not old_norm and new_norm:
        return "restored"
    if old_norm and new_norm and _has_career_noise(old_norm) and not _has_career_noise(new_norm):
        return "improved"
    if old_norm and new_norm and not _has_career_noise(old_norm) and _has_career_noise(new_norm):
        return "regression_noise"
    if old_norm and new_norm:
        return "changed"
    return "unchanged"


def _spot_checks(records: dict[str, dict]) -> list[dict]:
    hits: list[dict] = []
    for record in records.values():
        fields = record.get("fields") or {}
        indigenous = _normalize(fields.get(INDIGENOUS_FIELD))
        sponsors = _normalize(fields.get(SPONSORS_FIELD))
        blob = f"{indigenous} {sponsors}".lower()
        for name in SPOT_CHECK_NAMES:
            if name.lower() in blob:
                hits.append(
                    {
                        "name": name,
                        "bill": _normalize(fields.get("Bill Number")),
                        "state": _normalize(fields.get("State")),
                        "title": _normalize(fields.get("Name"))[:80],
                        "indigenous": indigenous,
                    }
                )
    return hits


def compare_snapshots(baseline_path: Path, current_path: Path) -> dict:
    baseline = _load_records(baseline_path)
    current = _load_records(current_path)

    shared = sorted(set(baseline) & set(current))
    only_baseline = sorted(set(baseline) - set(current))
    only_current = sorted(set(current) - set(baseline))

    baseline_rows_with_indigenous = sum(
        1 for key in baseline if _normalize((baseline[key].get("fields") or {}).get(INDIGENOUS_FIELD))
    )
    current_rows_with_indigenous = sum(
        1 for key in current if _normalize((current[key].get("fields") or {}).get(INDIGENOUS_FIELD))
    )
    baseline_entry_count = sum(
        _count_entries((baseline[key].get("fields") or {}).get(INDIGENOUS_FIELD, ""))
        for key in baseline
    )
    current_entry_count = sum(
        _count_entries((current[key].get("fields") or {}).get(INDIGENOUS_FIELD, ""))
        for key in current
    )

    by_class: dict[str, list[dict]] = {
        "unchanged": [],
        "restored": [],
        "cleared": [],
        "improved": [],
        "changed": [],
        "regression_noise": [],
        "still_missing": [],
    }

    for key in shared:
        old_fields = baseline[key].get("fields") or {}
        new_fields = current[key].get("fields") or {}
        old_ind = _normalize(old_fields.get(INDIGENOUS_FIELD))
        new_ind = _normalize(new_fields.get(INDIGENOUS_FIELD))
        classification = _classify_change(old_ind, new_ind)

        if old_ind and not new_ind:
            by_class["still_missing"].append(
                {
                    "identity": key,
                    "bill": _normalize(old_fields.get("Bill Number")),
                    "state": _normalize(old_fields.get("State")),
                    "title": _normalize(old_fields.get("Name"))[:80],
                    "old": old_ind,
                }
            )
            continue

        if classification != "unchanged":
            by_class[classification].append(
                {
                    "identity": key,
                    "bill": _normalize(new_fields.get("Bill Number") or old_fields.get("Bill Number")),
                    "state": _normalize(new_fields.get("State") or old_fields.get("State")),
                    "title": _normalize(new_fields.get("Name") or old_fields.get("Name"))[:80],
                    "old": old_ind,
                    "new": new_ind,
                }
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_file": str(baseline_path),
        "current_file": str(current_path),
        "baseline_records": len(baseline),
        "current_records": len(current),
        "only_in_baseline": len(only_baseline),
        "only_in_current": len(only_current),
        "shared_records": len(shared),
        "metrics": {
            "baseline_rows_with_indigenous": baseline_rows_with_indigenous,
            "current_rows_with_indigenous": current_rows_with_indigenous,
            "baseline_indigenous_entry_count": baseline_entry_count,
            "current_indigenous_entry_count": current_entry_count,
        },
        "counts_by_class": {key: len(items) for key, items in by_class.items()},
        "details": by_class,
        "spot_checks_baseline": _spot_checks(baseline),
        "spot_checks_current": _spot_checks(current),
    }


def _write_markdown(report: dict, path: Path) -> None:
    metrics = report["metrics"]
    lines = [
        "# Indigenous Sponsorship Comparison",
        "",
        f"- Baseline: `{report['baseline_file']}`",
        f"- Current: `{report['current_file']}`",
        "",
        "## Metrics",
        "",
        f"| Metric | Baseline | Current |",
        f"|--------|----------|---------|",
        f"| Rows with indigenous field | {metrics['baseline_rows_with_indigenous']} | {metrics['current_rows_with_indigenous']} |",
        f"| Indigenous sponsor entries | {metrics['baseline_indigenous_entry_count']} | {metrics['current_indigenous_entry_count']} |",
        "",
        "## Classifications",
        "",
    ]
    for key, count in report["counts_by_class"].items():
        lines.append(f"- **{key}**: {count}")

    lines.extend(["", "## Spot checks (current)", ""])
    for hit in report.get("spot_checks_current") or []:
        lines.append(
            f"- {hit['name']} — {hit['state']} {hit['bill']}: `{hit['indigenous'][:120]}`"
        )

    still_missing = report["details"].get("still_missing") or []
    if still_missing:
        lines.extend(["", "## Still missing (regressions)", ""])
        for item in still_missing[:20]:
            lines.append(f"- {item['state']} {item['bill']}: had `{item['old'][:100]}`")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="Pre-trim or last-known-good snapshot JSON")
    parser.add_argument("--current", required=True, help="Post-fix snapshot JSON")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "scripts" / "reports"),
        help="Directory for JSON/Markdown reports",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)
    report = compare_snapshots(baseline_path, current_path)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"indigenous_sponsorship_compare_{stamp}.json"
    md_path = out_dir / f"indigenous_sponsorship_compare_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(report, md_path)

    metrics = report["metrics"]
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(
        f"Rows with indigenous: baseline={metrics['baseline_rows_with_indigenous']} "
        f"current={metrics['current_rows_with_indigenous']}"
    )
    print(
        f"Entry count: baseline={metrics['baseline_indigenous_entry_count']} "
        f"current={metrics['current_indigenous_entry_count']}"
    )
    print(f"still_missing={report['counts_by_class'].get('still_missing', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
