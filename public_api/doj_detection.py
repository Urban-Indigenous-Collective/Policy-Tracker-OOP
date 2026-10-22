"""Detect DOJ / USAO-linked policies (justice.gov URLs on Main v3 / Pending)."""

from __future__ import annotations

import re

_JUSTICE_GOV_RE = re.compile(
    r"(?:https?://)?(?:[\w.-]*\.)?justice\.gov(?:/|$|[?#])",
    re.I,
)

# Link-less USAO rows on Main v3 (no Bill Number, title names the office).
_USAO_NAME_RE = re.compile(
    r"\b(?:USAO|U\.S\.\s*Attorney(?:\'s)?\s+Office|United States Attorney)\b",
    re.I,
)

_BILL_URL_KEYS = (
    "billOverviewUrl",
    "optionalLink",
    "billTextUrl",
)


def _normalize_url(url: str) -> str:
    return str(url or "").strip()


def url_looks_doj_linked(url: str) -> bool:
    """True when URL points at justice.gov."""
    text = _normalize_url(url)
    if not text:
        return False
    if _JUSTICE_GOV_RE.search(text):
        return True
    return "justice.gov" in text.lower()


def bill_link_urls_from_fields(fields: dict) -> list[str]:
    out: list[str] = []
    for key in (
        "Bill Overview (Link)",
        "Bill Overview",
        "Bill Text",
        "Optional Link",
    ):
        val = fields.get(key)
        if val not in (None, ""):
            out.append(str(val).strip())
    return out


def iter_bill_link_urls(bill: dict) -> list[str]:
    out: list[str] = []
    for key in _BILL_URL_KEYS:
        val = bill.get(key)
        if val not in (None, ""):
            out.append(_normalize_url(str(val)))
    return out


def is_doj_initiative_bill(bill: dict) -> bool:
    for url in iter_bill_link_urls(bill):
        if url_looks_doj_linked(url):
            return True

    bill_number = str(bill.get("billNumber") or "").strip()
    name = str(bill.get("name") or bill.get("title") or "").strip()
    if not bill_number and name and _USAO_NAME_RE.search(name):
        return True

    return False


def is_doj_initiative_record(record: dict) -> bool:
    fields = dict(record.get("fields") or {})
    for url in bill_link_urls_from_fields(fields):
        if url_looks_doj_linked(url):
            return True
    bill_number = str(fields.get("Bill Number") or "").strip()
    name = str(fields.get("Name") or fields.get("Title") or "").strip()
    if not bill_number and name and _USAO_NAME_RE.search(name):
        return True
    return False
