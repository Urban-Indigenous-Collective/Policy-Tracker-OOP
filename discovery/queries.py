"""MMIP search queries and keyword lexicon for discovery prescreening."""

from __future__ import annotations

import re

# LegiScan full-text query variants (boolean search)
MMIP_QUERIES = [
    '"missing and murdered indigenous"',
    '"missing and murdered Native American"',
    '"murdered indigenous women"',
    'MMIW OR MMIP OR MMIWG',
    '"missing" AND "indigenous" AND ("task force" OR "taskforce")',
    '"tribal" AND "missing persons"',
    '"Savanna\'s Act" OR "Not Invisible Act"',
    '"missing and murdered" AND ("tribal" OR "Native American" OR "Alaska Native")',
    '"indigenous" AND ("homicide" OR "murdered") AND "women"',
    '"Native Hawaiian" AND ("missing" OR "murdered")',
]

INDIGENOUS_TERMS = [
    "indigenous",
    "native american",
    "american indian",
    "alaska native",
    "native hawaiian",
    "tribal",
    "tribe",
    "first nations",
    "mmiw",
    "mmip",
    "mmiwg",
    "indian country",
    "on-reservation",
    "on reservation",
]

HARM_TERMS = [
    "missing",
    "murdered",
    "homicide",
    "trafficking",
    "violence",
    "unsolved",
    "disappeared",
    "disappearance",
    "cold case",
    "murder",
    "kidnapping",
    "abducted",
]

MMIP_ACRONYMS = ["mmiw", "mmip", "mmiwg"]

# Word-boundary acronyms for operative-text checks (avoids matching inside longer words).
MMIP_ACRONYM_RE = re.compile(r"\bmmi[wpr][a-z0-9]*\b", re.IGNORECASE)


def strip_mmip_query_contamination(text: str) -> str:
    """Remove LegiScan discovery query literals that can false-trigger prescreen.

    Only strips boolean/search-syntax queries (AND/OR/parentheses). Natural-language
    phrase queries like ``"missing and murdered indigenous"`` also appear verbatim in
    real bill text and must not be erased.
    """
    cleaned = text or ""
    for query in MMIP_QUERIES:
        # LegiScan boolean operators are uppercase AND/OR. Do not use IGNORECASE —
        # that would treat the English word "and" inside phrase queries as syntax.
        if not re.search(r"\b(?:AND|OR)\b|\(|\)", query):
            continue
        for variant in {query, query.strip('"'), query.replace('"', "")}:
            variant = variant.strip()
            if len(variant) < 4:
                continue
            cleaned = re.sub(re.escape(variant), " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def keyword_prescreen(text: str) -> bool:
    """Return True if text likely relates to MMIP (cheap pre-filter)."""
    lowered = text.lower()
    if any(acronym in lowered for acronym in MMIP_ACRONYMS):
        return True
    has_indigenous = any(term in lowered for term in INDIGENOUS_TERMS)
    has_harm = any(term in lowered for term in HARM_TERMS)
    return has_indigenous and has_harm
