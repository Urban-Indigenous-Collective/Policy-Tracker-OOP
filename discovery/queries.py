"""MMIP search queries and keyword lexicon for discovery prescreening."""

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


def keyword_prescreen(text: str) -> bool:
    """Return True if text likely relates to MMIP (cheap pre-filter)."""
    lowered = text.lower()
    if any(acronym in lowered for acronym in MMIP_ACRONYMS):
        return True
    has_indigenous = any(term in lowered for term in INDIGENOUS_TERMS)
    has_harm = any(term in lowered for term in HARM_TERMS)
    return has_indigenous and has_harm
