"""Infer state jurisdiction for DOJ / USAO federal discovery items."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from discovery.federal_schema import FEDERAL_STATE

USAO_DISTRICTS_PATH = (
    Path(__file__).resolve().parent.parent / "sources" / "usao_districts.json"
)

USAO_SLUG_RE = re.compile(r"justice\.gov/(usao-[a-z0-9-]+)", re.I)

# Inverted from slack_client.STATE_NAMES plus territories used by USAO districts.
_NAME_TO_CODE: dict[str, str] = {
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "DISTRICT OF COLUMBIA": "DC",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "GUAM": "GU",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "PUERTO RICO": "PR",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGIN ISLANDS": "VI",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
}

_VALID_STATE_CODES = set(_NAME_TO_CODE.values())

_DISTRICT_OF_RE = re.compile(
    r"\bdistrict of ([A-Za-z][A-Za-z .'-]+?)(?:\s*,|\s+and\b|\s+U\.S\.|\s*$|\.)",
    re.I,
)
_USAO_DISTRICT_RE = re.compile(
    r"\b(?:"
    r"western|eastern|northern|southern|central|middle"
    r")\s+district of ([A-Za-z][A-Za-z .'-]+?)(?:\s*,|\s+and\b|\s+U\.S\.|\s*$|\.)",
    re.I,
)
_STATE_NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(name.title()) for name in sorted(_NAME_TO_CODE, key=len, reverse=True)) + r")\b",
    re.I,
)

# Shared multi-jurisdiction USAO offices — keep National rather than guessing one state.
_MULTI_JURISDICTION_SLUGS = frozenset({"usao-gu"})


def _normalize_state_code(value: str | None) -> str:
    text = (value or "").strip().upper()
    if not text or text in {"NATIONAL", "FEDERAL", "UNKNOWN", "NOT APPLICABLE", "N/A"}:
        return FEDERAL_STATE
    if text in _VALID_STATE_CODES:
        return text
    return FEDERAL_STATE


def _district_name_to_state(name: str) -> str | None:
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    lower = cleaned.lower()
    if "&" in cleaned or " and " in lower:
        return None
    primary = cleaned.split(",")[0].strip()
    return _NAME_TO_CODE.get(primary.upper())


@lru_cache(maxsize=1)
def _usao_slug_to_state() -> dict[str, str]:
    if not USAO_DISTRICTS_PATH.exists():
        return {}
    data = json.loads(USAO_DISTRICTS_PATH.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for district in data.get("districts") or []:
        slug = str(district.get("slug") or "").strip().lower()
        if not slug or slug in _MULTI_JURISDICTION_SLUGS:
            continue
        state = _district_name_to_state(str(district.get("name") or ""))
        if state:
            mapping[slug] = state
    return mapping


def extract_usao_slug(url: str = "", source_id: str | None = None) -> str | None:
    sid = (source_id or "").strip().lower()
    if sid.startswith("usao-"):
        return sid
    match = USAO_SLUG_RE.search(url or "")
    return match.group(1).lower() if match else None


def _state_from_text(*parts: str) -> str | None:
    combined = "\n".join(p for p in parts if p).strip()
    if not combined:
        return None

    for pattern in (_USAO_DISTRICT_RE, _DISTRICT_OF_RE):
        match = pattern.search(combined)
        if match:
            code = _district_name_to_state(match.group(1).strip())
            if code:
                return code

    for match in _STATE_NAME_RE.finditer(combined):
        code = _NAME_TO_CODE.get(match.group(1).upper())
        if code:
            return code
    return None


def is_national_federal_document(url: str, *, content_type: str = "") -> bool:
    """True when the URL/content type should remain National (EO/FR/HQ DOJ)."""
    lower_url = (url or "").lower()
    ctype = (content_type or "").lower()
    if ctype in {"executive_order", "regulation", "proclamation"}:
        return True
    if "federalregister.gov" in lower_url:
        return True
    if "whitehouse.gov" in lower_url:
        return True
    parsed = urlparse(lower_url)
    path = parsed.path or ""
    if "justice.gov" in (parsed.netloc or ""):
        if extract_usao_slug(lower_url):
            return False
        if "/opa/" in path or path.startswith("/opa"):
            return True
        if "/archives/opa/" in path:
            return True
    return False


def infer_federal_jurisdiction(
    url: str,
    *,
    source_id: str | None = None,
    title: str = "",
    body: str = "",
    content_type: str = "",
) -> str:
    """Return a state code (e.g. AK) or ``National`` for federal discovery items."""
    if is_national_federal_document(url, content_type=content_type):
        return FEDERAL_STATE

    slug = extract_usao_slug(url, source_id=source_id)
    if slug:
        mapped = _usao_slug_to_state().get(slug)
        if mapped:
            return mapped
        if slug in _MULTI_JURISDICTION_SLUGS:
            return FEDERAL_STATE

    from_text = _state_from_text(title, body)
    if from_text:
        return from_text

    return FEDERAL_STATE


def resolve_federal_pending_state(
    *,
    url: str,
    candidate_state: str = "",
    llm_state: str = "",
    title: str = "",
    body: str = "",
    content_type: str = "",
    source_id: str | None = None,
) -> str:
    """Pick the Pending ``State`` field for a federal_site item."""
    inferred = infer_federal_jurisdiction(
        url,
        source_id=source_id,
        title=title,
        body=body,
        content_type=content_type,
    )
    if inferred != FEDERAL_STATE:
        return inferred

    llm_code = _normalize_state_code(llm_state)
    if llm_code != FEDERAL_STATE:
        return llm_code

    candidate_code = _normalize_state_code(candidate_state)
    if candidate_code != FEDERAL_STATE:
        return candidate_code

    return FEDERAL_STATE
