"""Immutable record of what the automation wrote to Pending at creation time.

Airtable's API keeps no field edit history, so once a reviewer corrects a record the
original LLM output is gone. ``record_pending_creation`` appends one JSON line per newly
created Pending record, *before* any reviewer can touch it. ``compare_to_current`` later
diffs those automated values against the corrected rows (Pending or Live) for gold-set work.

Storage: ``<data dir>/automated_baseline/pending-created-YYYYMM.jsonl`` (append-only).
On prod this lives in the ``discovery_data`` Docker volume next to ``discovery.db``.

Join key is the bill URL (or state + bill number), **not** the Airtable record id: approval
sync creates a brand-new Live record and deletes the Pending one.

Capture never raises; a baseline failure must not block discovery.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
FILE_PREFIX = "pending-created-"
KIND_CREATION = "creation"  # captured by the pipeline at creation time (authoritative)
KIND_SNAPSHOT = "snapshot"  # seeded from an Airtable snapshot (may include human edits)

_URL_FIELDS = ("Bill Overview (Link)", "Bill Overview")

# Fields that legitimately change without a human correction (status refresh, workflow,
# discovery metadata). Excluded from comparisons unless include_volatile is set.
VOLATILE_FIELDS = frozenset(
    {
        "Review Status",
        "Source",
        "Relevance Confidence",
        "Relevance Rationale",
        "Discovered On",
        "Status",
        "Progression",
        "Chamber",
        "Chamber Details",
        "Last Update",
        "Validation Warnings",
    }
)

# Airtable system/computed columns: never a human correction, always skipped.
SYSTEM_FIELDS = frozenset({"Created By", "Created", "Created Time", "Last Modified", "Last Modified By"})

_LEADING_NUMERAL = re.compile(r"^\s*(?:\d+[.)]\s+)+", re.MULTILINE)
_WHITESPACE = re.compile(r"\s+")


# --- configuration -----------------------------------------------------------


def baseline_enabled() -> bool:
    return os.getenv("AUTOMATED_BASELINE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def baseline_dir() -> Path:
    """``AUTOMATED_BASELINE_DIR`` or ``automated_baseline/`` beside the discovery DB."""
    override = os.getenv("AUTOMATED_BASELINE_DIR", "").strip()
    if override:
        return Path(override)
    return Path(os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")).parent / "automated_baseline"


# --- identity ----------------------------------------------------------------


def record_identity(fields: dict[str, Any]) -> str | None:
    """Stable join key: normalized bill URL, else ``bill:STATE:NUMBER``."""
    from discovery.url_utils import bill_identity_key, normalize_url

    for name in _URL_FIELDS:
        raw = fields.get(name)
        if isinstance(raw, str) and raw.strip():
            normalized = normalize_url(raw)
            if normalized:
                return f"url:{normalized}"
    key = bill_identity_key(str(fields.get("State") or ""), str(fields.get("Bill Number") or ""))
    if key:
        return f"bill:{key[0]}:{key[1]}"
    return None


def _bill_url(fields: dict[str, Any]) -> str:
    for name in _URL_FIELDS:
        raw = fields.get(name)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


# --- capture -----------------------------------------------------------------


def _build_entry(
    *,
    kind: str,
    record_id: str | None,
    airtable_created_time: str | None,
    captured_at: str,
    fields: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "identity": record_identity(fields),
        "record_id": record_id,
        "airtable_created_time": airtable_created_time,
        "captured_at": captured_at,
        "bill_url": _bill_url(fields),
        "state": fields.get("State"),
        "bill_number": fields.get("Bill Number"),
        "fields": fields,
    }
    if extra:
        entry.update(extra)
    return entry


def _append_line(directory: Path, line: str, when: datetime) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{FILE_PREFIX}{when.strftime('%Y%m')}.jsonl"
    with open(path, "a", encoding="utf-8") as handle:
        try:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX)
        except (ImportError, OSError):  # non-POSIX: single append is still best effort
            pass
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return path


def record_pending_creation(
    created: dict[str, Any] | None,
    sent_fields: dict[str, Any] | None = None,
    *,
    source: str = "",
    relevance_confidence: float | None = None,
    discovered_on: str = "",
) -> Path | None:
    """Append the automated field values of a just-created Pending record.

    ``created`` is the Airtable create response; ``sent_fields`` is the fallback when the
    response carries no fields. Returns the file written, or ``None`` when disabled/failed.
    """
    if not baseline_enabled():
        return None
    try:
        created = created or {}
        fields = dict(created.get("fields") or sent_fields or {})
        if not fields:
            return None
        from constants import PROMPT_VERSION

        now = datetime.now(timezone.utc)
        entry = _build_entry(
            kind=KIND_CREATION,
            record_id=created.get("id"),
            airtable_created_time=created.get("createdTime"),
            captured_at=now.isoformat(),
            fields=fields,
            extra={
                "prompt_version": PROMPT_VERSION,
                "llm_model": os.getenv("LLM_MODEL", ""),
                "pipeline_source": source,
                "relevance_confidence": relevance_confidence,
                "discovered_on": discovered_on,
            },
        )
        return _append_line(baseline_dir(), json.dumps(entry, ensure_ascii=False, default=str), now)
    except Exception as exc:  # never block discovery on baseline capture
        logger.warning("Automated baseline capture failed: %s", exc)
        return None


# --- loading -----------------------------------------------------------------


def iter_entries(directory: Path | None = None) -> Iterable[dict[str, Any]]:
    """Yield stored creation entries oldest-first (files sorted by month, lines in order)."""
    root = directory or baseline_dir()
    if not root.is_dir():
        return
    for path in sorted(root.glob(f"{FILE_PREFIX}*.jsonl")):
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping unreadable baseline line %s:%d", path.name, number)


def _entry_key(entry: dict[str, Any]) -> str:
    return entry.get("identity") or f"id:{entry.get('record_id') or 'unknown'}"


def load_baseline(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """identity -> first (original) creation entry. Later duplicates never overwrite."""
    baseline: dict[str, dict[str, Any]] = {}
    for entry in iter_entries(directory):
        baseline.setdefault(_entry_key(entry), entry)
    return baseline


def snapshot_tables(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Read an Airtable snapshot file as ``(table_label, record)`` pairs.

    Handles ``pending_snapshot.py`` / ``live_snapshot.py`` output (``records`` + ``table``)
    and combined dumps with ``live`` / ``pending`` lists.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pairs: list[tuple[str, dict[str, Any]]] = []
    if isinstance(data.get("records"), list):
        label = "Live" if str(data.get("table", "")).lower().startswith("main") else "Pending"
        pairs.extend((label, record) for record in data["records"])
    for key, label in (("live", "Live"), ("pending", "Pending")):
        if isinstance(data.get(key), list):
            pairs.extend((label, record) for record in data[key])
    return pairs


def baseline_from_snapshots(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    """Fallback baseline from Airtable Pending snapshots (kind=snapshot).

    Earlier snapshots win. These can already contain reviewer edits, so they rank below
    creation-time entries; callers should merge with ``{**snapshot_based, **creation_based}``.
    """
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(Path(p) for p in paths):
        data = json.loads(path.read_text(encoding="utf-8"))
        captured_at = data.get("exported_at") or data.get("taken_at") or ""
        for label, record in snapshot_tables(path):
            if label != "Pending":
                continue
            fields = dict(record.get("fields") or {})
            if not fields:
                continue
            entry = _build_entry(
                kind=KIND_SNAPSHOT,
                record_id=record.get("id"),
                airtable_created_time=record.get("createdTime"),
                captured_at=captured_at,
                fields=fields,
                extra={"snapshot_file": path.name},
            )
            result.setdefault(_entry_key(entry), entry)
    return result


# --- comparison --------------------------------------------------------------


def _normalize(value: Any) -> Any:
    """Collapse noise that is not a real correction: numeral prefixes, whitespace, empties."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if text.lower().startswith(("http://", "https://")) and " " not in text:
            from discovery.url_utils import normalize_url

            return normalize_url(text)  # trailing slash / http->https is not a correction
        return _WHITESPACE.sub(" ", _LEADING_NUMERAL.sub("", value)).strip()
    if isinstance(value, (list, tuple)):
        items = [_normalize(item) for item in value]
        return sorted((item for item in items if item != ""), key=str)
    if isinstance(value, bool):
        return value
    return value


def _is_empty(value: Any) -> bool:
    return value in ("", [], None)


def compare_to_current(
    baseline: dict[str, dict[str, Any]],
    current: Iterable[tuple[str, dict[str, Any]]],
    *,
    include_volatile: bool = False,
    approved_only: bool = False,
) -> dict[str, Any]:
    """Diff automated baseline fields against current Airtable rows.

    ``current`` is ``(table_label, record)`` pairs (``"Pending"`` or ``"Live"``). A bill in
    both tables is reported from Live (the approved version). Fields a current table never
    carries are skipped so Live's smaller schema does not read as a correction.
    """
    pairs = list(current)
    carried: dict[str, set[str]] = {}
    for label, record in pairs:
        carried.setdefault(label, set()).update((record.get("fields") or {}).keys())

    chosen: dict[str, tuple[str, dict[str, Any]]] = {}
    for label, record in pairs:
        if approved_only and label != "Live":
            continue
        fields = record.get("fields") or {}
        key = record_identity(fields) or f"id:{record.get('id')}"
        if key not in chosen or label == "Live":
            chosen[key] = (label, record)

    matches: list[dict[str, Any]] = []
    field_counts: dict[str, int] = {}
    for key, (label, record) in sorted(chosen.items()):
        entry = baseline.get(key)
        if entry is None:
            continue
        old_fields = entry.get("fields") or {}
        new_fields = record.get("fields") or {}
        changed: dict[str, dict[str, Any]] = {}
        compared = 0
        for name in sorted(set(old_fields) | set(new_fields)):
            if name in SYSTEM_FIELDS:
                continue
            if not include_volatile and name in VOLATILE_FIELDS:
                continue
            if name not in carried[label]:
                continue
            compared += 1
            old, new = old_fields.get(name), new_fields.get(name)
            if _is_empty(old) and _is_empty(new):
                continue
            if _normalize(old) != _normalize(new):
                changed[name] = {"automated": old, "current": new}
                field_counts[name] = field_counts.get(name, 0) + 1
        matches.append(
            {
                "identity": key,
                "bill": f"{entry.get('state') or ''} {entry.get('bill_number') or ''}".strip(),
                "current_table": label,
                "current_review_status": new_fields.get("Review Status"),
                "current_record_id": record.get("id"),
                "baseline_kind": entry.get("kind"),
                "baseline_captured_at": entry.get("captured_at"),
                "prompt_version": entry.get("prompt_version"),
                "llm_model": entry.get("llm_model"),
                "fields_compared": compared,
                "changed": changed,
            }
        )

    matched_keys = {item["identity"] for item in matches}
    return {
        "baseline_count": len(baseline),
        "current_count": len(chosen),
        "matched": len(matches),
        "matched_with_changes": sum(1 for item in matches if item["changed"]),
        "matched_unchanged": sum(1 for item in matches if not item["changed"]),
        "baseline_without_current": sorted(set(baseline) - matched_keys),
        "field_change_counts": dict(sorted(field_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "records": matches,
    }
