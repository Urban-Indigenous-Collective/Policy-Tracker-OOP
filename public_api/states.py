"""Normalize Airtable State values for API keys and map aggregation."""

from __future__ import annotations

from discovery.federal_jurisdiction import _NAME_TO_CODE, _VALID_STATE_CODES
from discovery.federal_schema import FEDERAL_STATE

_FEDERAL_ALIASES = frozenset(
    {"US", "U.S.", "USA", "FEDERAL", "NATIONAL", "UNKNOWN", "NOT APPLICABLE", "N/A", ""}
)


def normalize_public_state(raw: str | None) -> str:
    """Return 2-letter code for US states/territories, or ``National`` for federal."""
    text = str(raw or "").strip()
    if not text:
        return FEDERAL_STATE
    upper = text.upper()
    if upper in _FEDERAL_ALIASES or text.lower() in {"us", "u.s.", "federal", "national"}:
        return FEDERAL_STATE
    if upper in _VALID_STATE_CODES:
        return upper
    if len(upper) == 2 and upper.isalpha():
        return upper
    mapped = _NAME_TO_CODE.get(upper)
    if mapped:
        return mapped
    title = text.title()
    mapped = _NAME_TO_CODE.get(title.upper())
    if mapped:
        return mapped
    return FEDERAL_STATE


def is_map_state_code(code: str) -> bool:
    """True when code can be painted on the US SVG (excludes National)."""
    return bool(code) and code != FEDERAL_STATE and code in _VALID_STATE_CODES
