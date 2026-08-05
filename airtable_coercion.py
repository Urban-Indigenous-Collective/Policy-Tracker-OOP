"""Normalize bill field values before Airtable writes (Pending and Main v3 share schema)."""

import ast
import json
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

from airtable_schema import (
    BILL_FIELD_NAMES,
    PROGRESSION_CHOICES,
    STATUS_CHOICES,
    EVAL_TBD_FIELDS,
    EVAL_YES_NO_SOMEWHAT_FIELDS,
    LEGACY_FIELD_RENAMES,
)
from constants import ALLOWED_CATEGORIES

_ALLOWED_CATEGORY_LOOKUP = {c.lower(): c for c in ALLOWED_CATEGORIES}
_PROGRESSION_LOOKUP = {p.lower(): p for p in PROGRESSION_CHOICES}
_STATUS_LOOKUP = {s.lower(): s for s in STATUS_CHOICES}
_CHAMBER_LOOKUP = {c.lower(): c for c in ["Executive", "Senate", "House"]}

_URL_FIELDS = {"Bill Overview (Link)", "Bill Text", "Optional Link"}
_DATE_FIELDS = {"Last Update"}
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize_legacy_keys(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for old, new in LEGACY_FIELD_RENAMES.items():
        if old in out and new not in out:
            out[new] = out.pop(old)
        elif old in out:
            out.pop(old, None)
    return out


def coerce_eval_value(field_name: str, value: Any) -> str:
    text = str(value or "").strip().rstrip(".")
    if not text:
        return "No"
    lowered = text.lower()
    if field_name in EVAL_TBD_FIELDS:
        if lowered == "yes":
            return "Yes"
        if lowered == "no":
            return "No"
        return "TBD or TCRP Specific"
    if field_name in EVAL_YES_NO_SOMEWHAT_FIELDS:
        if lowered == "yes":
            return "Yes"
        if lowered == "somewhat":
            return "Somewhat"
        return "No"
    return text


def coerce_status(value: Any) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered in _STATUS_LOOKUP:
        return _STATUS_LOOKUP[lowered]
    if lowered in ("active", "in progress", "open"):
        return "Pending"
    return "Pending"


def coerce_progression(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.upper() == "N/A":
        return "Progression"
    lowered = text.lower()
    if lowered in _PROGRESSION_LOOKUP:
        return _PROGRESSION_LOOKUP[lowered]
    for choice in PROGRESSION_CHOICES:
        if choice.lower() == lowered:
            return choice
    return "Progression"


def coerce_chamber(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "Executive"
    lowered = text.lower()
    if lowered in _CHAMBER_LOOKUP:
        return _CHAMBER_LOOKUP[lowered]
    if "senate" in lowered:
        return "Senate"
    if "house" in lowered or "assembly" in lowered:
        return "House"
    if "executive" in lowered:
        return "Executive"
    return "Executive"


_TOKEN_STRIP_RE = re.compile(r"^[\[\]'\"]+|[\[\]'\"]+$")


def _strip_category_token(token: str) -> str:
    return _TOKEN_STRIP_RE.sub("", token.strip())


def parse_category_tokens(value: Any) -> list[str]:
    """Extract raw category strings from LLM/Airtable shapes (JSON, Python repr, comma-split)."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(parse_category_tokens(item))
        return result

    text = str(value).strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple)):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except (ValueError, SyntaxError, TypeError):
            pass
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            pass

    return [
        _strip_category_token(part)
        for part in text.split(",")
        if _strip_category_token(part)
    ]


def coerce_categories(value: Any) -> list[str]:
    result: list[str] = []
    for part in parse_category_tokens(value):
        canonical = _ALLOWED_CATEGORY_LOOKUP.get(part.lower())
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def coerce_iso_date(value: Any) -> str | None:
    """Return YYYY-MM-DD or None if empty/unparseable (Airtable rejects '')."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    if _ISO_DATE_RE.match(text):
        return text
    # Common LLM leftovers: "May 5, 2026" / "05/05/2026"
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def coerce_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return text
    return None


def coerce_bill_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Return bill_data with Main v3–compatible field names and values."""
    merged = _normalize_legacy_keys(data)
    out: dict[str, Any] = {}

    for key in BILL_FIELD_NAMES:
        value = merged.get(key, "")
        if key == "Status":
            out[key] = coerce_status(value)
        elif key == "Progression":
            out[key] = coerce_progression(value)
        elif key == "Chamber":
            out[key] = coerce_chamber(value)
        elif key == "Categories":
            out[key] = coerce_categories(value)
        elif key.endswith("?"):
            out[key] = coerce_eval_value(key, value)
        elif key in _DATE_FIELDS:
            coerced = coerce_iso_date(value)
            if coerced:
                out[key] = coerced
            # Omit empty/invalid dates — Airtable 422s on ""
        elif key in _URL_FIELDS:
            coerced = coerce_url(value)
            if coerced:
                out[key] = coerced
        else:
            out[key] = value if value is not None else ""

    # Last Update is required-ish for review UX; default when metadata had none
    if "Last Update" not in out:
        out["Last Update"] = date.today().isoformat()

    return out
