"""Guardrails for non-LegiScan (.gov crawl) candidates.

LegiScan candidates carry authoritative bill metadata from the LegiScan API.
Crawled .gov pages do not: the state, title, bill number and date all come from
an LLM reading whatever text the scraper managed to pull off the page. When the
page is a search shell, a nav index or a JS stub, the model still returns a
complete-looking record. These checks fail such candidates closed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import parse_qsl, urlparse

# Observed extracted-text lengths for the 2026-08-02 Pending batch:
#   junk: 0 (WA JS stub), 346 (NY PDF wrapper), 1344/1424/1569/1630/2632/2734
#   real: 4736 (MT DOJ), 5316 (Federal Register), 7514 (NC DOA)
# 600 clears the empty/stub cases without risking a genuinely short proclamation.
DEFAULT_MIN_DOC_CHARS = 600

# LegiScan bill metadata alone is often short; still long enough to catch
# query-only contamination while admitting real one-line session titles.
LEGISCAN_MIN_DOC_CHARS = 200

SEARCH_QUERY_KEYS = {
    "q",
    "query",
    "s",
    "search",
    "searchtext",
    "searchterm",
    "keyword",
    "keywords",
    "term",
    "criteria",
    "kw",
}

SEARCH_SEGMENT_PATTERN = re.compile(
    r"(billsearch|searchclient|searchresults|advancedsearch|quicksearch)"
)

NAV_SEGMENTS = {
    "",
    "index",
    "home",
    "default",
    "sitemap",
    "search",
    "results",
}

# Matched against the head of the document only — real documents sometimes
# mention "search results" in passing, search shells lead with it.
SEARCH_BODY_MARKERS = [
    re.compile(r"search results?\s+for\b", re.IGNORECASE),
    re.compile(r"\b(no|0)\s+results?\s+(found|match)", re.IGNORECASE),
    re.compile(r"your search .{0,40}returned", re.IGNORECASE),
    re.compile(r"rezultati pretrage", re.IGNORECASE),  # bs
    re.compile(r"r[ée]sultats de (la )?recherche", re.IGNORECASE),  # fr
    re.compile(r"resultados de (la )?b[úu]squeda", re.IGNORECASE),  # es
]
SEARCH_MARKER_WINDOW = 600

_WORD = re.compile(r"[a-z0-9']+")

TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "the",
    "of",
    "for",
    "to",
    "in",
    "on",
    "by",
    "as",
    "at",
    "or",
    "act",
    "bill",
    "state",
    "department",
}


@dataclass(frozen=True)
class GuardVerdict:
    """Outcome of a single guard. `code` is empty when the guard passes."""

    ok: bool
    code: str = ""
    detail: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class ConsistencyResult:
    """Post-analysis reconciliation of LLM metadata against the document."""

    ok: bool = True
    blocking_code: str = ""
    blocking_detail: str = ""
    warnings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


PASS = GuardVerdict(True)


def min_doc_chars() -> int:
    try:
        return int(os.getenv("DISCOVERY_MIN_DOC_CHARS", str(DEFAULT_MIN_DOC_CHARS)))
    except ValueError:
        return DEFAULT_MIN_DOC_CHARS


def _visible_length(text: str) -> int:
    return len(re.sub(r"\s+", " ", text or "").strip())


def _last_segment(path: str) -> str:
    segments = [seg for seg in (path or "").split("/") if seg]
    if not segments:
        return ""
    return segments[-1].lower()


def check_url_shape(url: str) -> GuardVerdict:
    """Reject URLs that cannot be a specific policy document."""
    text = (url or "").strip()
    if not text:
        return GuardVerdict(False, "url_empty", "empty URL")

    parsed = urlparse(text)
    if parsed.scheme.lower() not in ("http", "https"):
        return GuardVerdict(False, "url_not_http", f"scheme {parsed.scheme!r} is not http(s)")
    if not parsed.netloc:
        return GuardVerdict(False, "url_no_host", "URL has no host")

    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.strip().lower() in SEARCH_QUERY_KEYS and value.strip():
            return GuardVerdict(
                False, "url_search_page", f"search query parameter {key}={value!r}"
            )

    segment = _last_segment(parsed.path)
    stem = segment.rsplit(".", 1)[0] if "." in segment else segment
    if SEARCH_SEGMENT_PATTERN.search(stem):
        return GuardVerdict(False, "url_search_page", f"search endpoint {segment!r}")
    if "search" in re.split(r"[-_.]", stem):
        return GuardVerdict(False, "url_search_page", f"search endpoint {segment!r}")

    if stem in NAV_SEGMENTS:
        return GuardVerdict(False, "url_nav_index", f"index/nav endpoint {segment or '/'!r}")

    return PASS


def check_document_text(
    text: str,
    url: str = "",
    *,
    title: str = "",
    context: str = "",
) -> GuardVerdict:
    """Reject thin, empty, or search-result page text before LLM analysis."""
    length = _visible_length(text)
    if length == 0:
        return GuardVerdict(False, "doc_empty", f"no extractable text at {url or 'document'}")

    head = re.sub(r"\s+", " ", text)[:SEARCH_MARKER_WINDOW]
    for marker in SEARCH_BODY_MARKERS:
        found = marker.search(head)
        if found:
            return GuardVerdict(
                False, "doc_search_results", f"search-results marker {found.group(0)!r}"
            )

    # Imported lazily: discovery/__init__ pulls in the pipeline, which imports
    # this module.
    from discovery.federal_schema import is_federal_register_document_url
    from discovery.queries import keyword_prescreen

    is_fr_doc = is_federal_register_document_url(url)
    use_metadata = is_fr_doc or "justice.gov" in (url or "").lower()
    prescreen_parts = [part for part in (title, context, text) if part and part.strip()]
    prescreen_text = "\n".join(prescreen_parts).strip() if use_metadata else text

    minimum = min_doc_chars()
    if length < minimum:
        if use_metadata and keyword_prescreen(prescreen_text):
            pass
        else:
            return GuardVerdict(
                False, "doc_too_short", f"{length} chars of text (minimum {minimum})"
            )

    if not keyword_prescreen(prescreen_text):
        return GuardVerdict(
            False,
            "doc_no_mmip_evidence",
            "document text contains no MMIP terms; relevance came from link text only",
        )

    return PASS


def screen_candidate_document(
    url: str,
    text: str,
    *,
    title: str = "",
    context: str = "",
) -> GuardVerdict:
    """Run URL shape then document text checks for a crawled candidate."""
    verdict = check_url_shape(url)
    if not verdict:
        return verdict
    return check_document_text(text, url, title=title, context=context)


# --- LegiScan operative vs findings MMIP gate --------------------------------

LEGISCAN_JUNK_TITLE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"budget act", re.I), "budget_act"),
    (re.compile(r"omnibus", re.I), "omnibus"),
    (re.compile(r"appropriation", re.I), "appropriations"),
    (re.compile(r"public resources", re.I), "public_resources"),
    (re.compile(r"public safety omnibus", re.I), "public_safety_omnibus"),
    (re.compile(r"human trafficking", re.I), "human_trafficking"),
    (re.compile(r"serious felonies", re.I), "serious_felonies"),
    (re.compile(r"^public health:", re.I), "public_health_omnibus"),
]

OPERATIVE_MMIP_PHRASES = (
    "missing and murdered indigenous",
    "missing or murdered indigenous",
    "murdered or missing indigenous",
    "missing and murdered native american",
    "missing and murdered indigenous persons",
    "missing and murdered indigenous persons cases",
    "indigenous persons justice",
    "feather alert",
    "mmip task force",
    "mmiw task force",
)

TRIBAL_LE_OPERATIVE_PATTERNS = (
    re.compile(r"\bclets\b", re.I),
    re.compile(r"law enforcement telecommunications", re.I),
    re.compile(r"tribal police", re.I),
    re.compile(r"tribal law enforcement", re.I),
    re.compile(r"tribal peace officer", re.I),
)


def legiscan_junk_title_flags(title: str) -> list[str]:
    flags: list[str] = []
    for pattern, label in LEGISCAN_JUNK_TITLE_PATTERNS:
        if pattern.search(title or ""):
            flags.append(label)
    return flags


def title_has_mmip_nexus(title: str) -> bool:
    lowered = (title or "").lower()
    explicit = (
        "mmip",
        "mmiw",
        "missing and murdered indigenous",
        "murdered or missing indigenous",
        "missing or murdered indigenous",
        "missing and murdered native",
        "murdered and missing native",
        "feather alert",
        "indigenous people awareness",
        "indigenous women awareness",
        "indigenous persons justice",
    )
    if any(phrase in lowered for phrase in explicit):
        return True
    if "indigenous" in lowered and any(term in lowered for term in ("missing", "murdered", "mmip")):
        return True
    if "native american" in lowered and any(term in lowered for term in ("missing", "murdered", "women", "girls")):
        return True
    return False


def title_has_tribal_le_nexus(title: str) -> bool:
    lowered = (title or "").lower()
    return any(
        phrase in lowered
        for phrase in (
            "clets",
            "tribal police",
            "tribal law enforcement",
            "tribal peace officer",
            "feather alert",
        )
    )


def extract_operative_text(text: str) -> str:
    """Return the first operative segment (from Section 2 onward, before any recycle)."""
    from discovery.queries import strip_mmip_query_contamination

    clean = strip_mmip_query_contamination(text or "")
    lowered = clean.lower()
    start = 0
    for pattern in (r"\bsec(?:tion)?\.?\s*2\b", r"\bchapter\s+\d+", r"\barticle\s+\d+"):
        match = re.search(pattern, lowered)
        if match:
            start = match.start()
            break
    else:
        for marker in (
            "the people of the state of california do enact",
            "chapter ",
            "article ",
        ):
            pos = lowered.find(marker)
            if pos > 0:
                start = pos
                break
    operative = clean[start:]
    # LegiScan excerpts sometimes repeat the bill; drop recycled findings headers.
    recycle = re.search(r"(?im)\bsection\s+1\.?\b", operative[12:])
    if recycle:
        operative = operative[: 12 + recycle.start()]
    return operative


def extract_findings_text(text: str) -> str:
    """Return preamble/findings before the first operative section marker."""
    from discovery.queries import strip_mmip_query_contamination

    clean = strip_mmip_query_contamination(text or "")
    lowered = clean.lower()
    for pattern in (r"\bsec(?:tion)?\.?\s*2\b", r"\bchapter\s+\d+", r"\barticle\s+\d+"):
        match = re.search(pattern, lowered)
        if match:
            return clean[: match.start()]
    for marker in (
        "the people of the state of california do enact",
        "chapter ",
        "article ",
    ):
        pos = lowered.find(marker)
        if pos > 0:
            return clean[:pos]
    return clean


def _text_has_mmip_phrases(text: str) -> bool:
    from discovery.queries import MMIP_ACRONYM_RE

    lowered = (text or "").lower()
    if MMIP_ACRONYM_RE.search(lowered):
        return True
    return any(phrase in lowered for phrase in OPERATIVE_MMIP_PHRASES)


def has_operative_mmip_signal(text: str) -> bool:
    operative = extract_operative_text(text).lower()
    return _text_has_mmip_phrases(operative)


def is_findings_only_mmip(text: str) -> bool:
    findings = extract_findings_text(text)
    return _text_has_mmip_phrases(findings) and not has_operative_mmip_signal(text)


def has_operative_tribal_le_access(text: str) -> bool:
    operative = extract_operative_text(text)
    return any(pattern.search(operative) for pattern in TRIBAL_LE_OPERATIVE_PATTERNS)


def legiscan_relevance_supported(text: str, *, title: str = "") -> bool:
    """True when bill text/title contains evidence backing an MMIP relevance claim."""
    from discovery.queries import keyword_prescreen, strip_mmip_query_contamination

    cleaned = strip_mmip_query_contamination(text or "")
    if title_has_mmip_nexus(title):
        return True
    if keyword_prescreen(cleaned):
        return True
    return has_operative_mmip_signal(cleaned)


def check_legiscan_operative_mmip(text: str, *, title: str = "") -> GuardVerdict:
    """Require MMIP nexus in operative law, title, or tribal-LE + findings."""
    from discovery.queries import keyword_prescreen, strip_mmip_query_contamination

    cleaned = strip_mmip_query_contamination(text or "")
    title_mmip = title_has_mmip_nexus(title)
    title_tribal_le = title_has_tribal_le_nexus(title)
    operative_mmip = has_operative_mmip_signal(cleaned)
    findings_only = is_findings_only_mmip(cleaned)
    tribal_le_operative = has_operative_tribal_le_access(cleaned)
    junk_flags = legiscan_junk_title_flags(title)
    operative = extract_operative_text(cleaned)
    operative_prescreen = keyword_prescreen(operative)

    if title_mmip or operative_mmip:
        return PASS
    if tribal_le_operative and (_text_has_mmip_phrases(cleaned) or title_tribal_le):
        return PASS

    if junk_flags and not operative_mmip:
        return GuardVerdict(
            False,
            "legiscan_junk_title",
            f"title indicates non-MMIP subject ({', '.join(junk_flags)}); no operative MMIP provisions",
        )
    if findings_only and not tribal_le_operative:
        return GuardVerdict(
            False,
            "legiscan_findings_only_mmip",
            "MMIP mentioned only in legislative findings or intent, not operative enacting law",
        )
    if keyword_prescreen(cleaned) and not operative_prescreen and not tribal_le_operative:
        return GuardVerdict(
            False,
            "legiscan_no_operative_mmip",
            "MMIP keywords appear only in findings or incidental context, not operative law",
        )

    return PASS


def check_legiscan_document_text(text: str, url: str = "", *, title: str = "") -> GuardVerdict:
    """Reject LegiScan candidates whose bill text lacks MMIP grounding."""
    from discovery.queries import keyword_prescreen, strip_mmip_query_contamination

    cleaned = strip_mmip_query_contamination(text)
    length = _visible_length(cleaned)
    if length == 0:
        return GuardVerdict(
            False, "doc_empty", f"no extractable bill text at {url or 'LegiScan bill'}"
        )

    minimum = LEGISCAN_MIN_DOC_CHARS
    if length < minimum:
        return GuardVerdict(
            False,
            "doc_too_short",
            f"{length} chars of bill text (minimum {minimum})",
        )

    if not keyword_prescreen(cleaned):
        return GuardVerdict(
            False,
            "doc_no_mmip_evidence",
            "bill text contains no MMIP terms; relevance came from search query only",
        )

    return check_legiscan_operative_mmip(cleaned, title=title)


def screen_legiscan_document(url: str, text: str, *, title: str = "") -> GuardVerdict:
    """Screen a LegiScan bill excerpt or decoded text before relevance or write."""
    return check_legiscan_document_text(text, url, title=title)


def _normalize_bill_number(value: str) -> str:
    from legiscan_processor import normalize_bill_number

    return normalize_bill_number(value)


_FEDERAL_CHAMBER_ALIASES = {
    "HB": "HR",
    "HR": "HB",
    "SB": "S",
    "S": "SB",
}


def _bill_number_variants(bill_number: str) -> set[str]:
    norm = _normalize_bill_number(bill_number)
    if not norm:
        return set()
    variants = {norm}
    match = re.match(r"^([A-Z]+)(\d+)$", norm)
    if match:
        prefix, num = match.groups()
        alias = _FEDERAL_CHAMBER_ALIASES.get(prefix)
        if alias:
            variants.add(f"{alias}{num}")
    return variants


def _bill_number_in_raw_text(bill_number: str, source_text: str) -> bool:
    """Match dotted/spaced bill numbers like H.B. 25 or H. R. 958."""
    norm = _normalize_bill_number(bill_number)
    match = re.match(r"^([A-Z]+)(\d+)$", norm)
    if not match:
        return False
    prefix, num = match.groups()
    num_int = str(int(num))
    prefixes = [prefix]
    alias = _FEDERAL_CHAMBER_ALIASES.get(prefix)
    if alias:
        prefixes.append(alias)
    for pref in prefixes:
        prefix_pattern = r"\.?\s*".join(pref)
        pattern = rf"\b{prefix_pattern}\.?\s*0*{num_int}\b"
        if re.search(pattern, source_text, re.IGNORECASE):
            return True
    return False


def _ny_assembly_in_text(bill_number: str, source_text: str) -> bool:
    """A08545 matches phrasing like '8545 IN ASSEMBLY'."""
    norm = _normalize_bill_number(bill_number)
    match = re.match(r"^A(\d+)$", norm)
    if not match:
        return False
    num_int = str(int(match.group(1)))
    text_upper = source_text.upper()
    patterns = (
        rf"\b{num_int}\b[^\n]{{0,40}}\bIN ASSEMBLY\b",
        rf"\bASSEMBLY\b[^\n]{{0,40}}\b{num_int}\b",
        rf"\bA\.?\s*{num_int}\b",
    )
    return any(re.search(pattern, text_upper) for pattern in patterns)


def _admin_order_in_text(bill_number: str, source_text: str) -> bool:
    """AO329 matches 'Administrative Order No. 329'."""
    norm = _normalize_bill_number(bill_number)
    match = re.match(r"^AO(\d+)$", norm)
    if not match:
        return False
    num_int = str(int(match.group(1)))
    return bool(
        re.search(
            rf"\bADMINISTRATIVE\s+ORDER\s+(?:NO\.?\s*)?{num_int}\b",
            source_text,
            re.IGNORECASE,
        )
    )


def _bill_number_from_url(bill_data: dict | None) -> str:
    from legiscan_processor import parse_legiscan_bill_url

    if not bill_data:
        return ""
    for key in ("Bill Text", "Bill Overview (Link)", "Bill Overview"):
        parsed = parse_legiscan_bill_url(str(bill_data.get(key) or ""))
        if parsed:
            return parsed[1]
    return ""


def bill_number_in_text(
    bill_number: str,
    source_text: str,
    *,
    bill_data: dict | None = None,
) -> bool:
    """True when the bill number appears in the document, ignoring separators."""
    if not str(bill_number or "").strip():
        return True

    haystack = _normalize_bill_number(source_text)
    for variant in _bill_number_variants(bill_number):
        if variant in haystack:
            return True

    if _bill_number_in_raw_text(bill_number, source_text):
        return True
    if _ny_assembly_in_text(bill_number, source_text):
        return True
    if _admin_order_in_text(bill_number, source_text):
        return True

    url_bill = _bill_number_from_url(bill_data)
    if url_bill:
        if _bill_number_variants(url_bill) & _bill_number_variants(bill_number):
            return True
        for variant in _bill_number_variants(url_bill):
            if variant in haystack:
                return True
        if _bill_number_in_raw_text(url_bill, source_text):
            return True

    return False


def _significant_words(text: str) -> set[str]:
    return {
        word
        for word in _WORD.findall((text or "").lower())
        if len(word) > 3 and word not in TITLE_STOPWORDS
    }


def title_overlap(title: str, source_text: str) -> float:
    """Fraction of the title's significant words present in the document."""
    words = _significant_words(title)
    if not words:
        return 0.0
    source_words = _significant_words(source_text)
    return len(words & source_words) / len(words)


_MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


def _date_is_grounded(date_value: str, source_text: str) -> bool:
    """True when the date's year and calendar day appear in the document text."""
    match = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", str(date_value or ""))
    if not match:
        return False
    year, month, day = match.groups()
    text = source_text or ""
    if year not in text:
        return False
    if (month, day) == ("01", "01"):
        # Jan 1 is the model's default when it cannot find a date.
        return bool(re.search(rf"january\s+1\b|01-01|1/1/{year}", text, re.IGNORECASE))

    iso = f"{year}-{month}-{day}"
    if iso in text:
        return True

    month_idx = int(month)
    day_int = int(day)
    if month_idx < 1 or month_idx > 12:
        return False
    month_name = _MONTH_NAMES[month_idx - 1]
    day_patterns = [
        rf"{month_name}\s+{day_int}\b,?\s*{year}",
        rf"{month_name}\s+{day_int:02d}\b,?\s*{year}",
        rf"{month_idx}/{day_int}/{year}",
        rf"{month_idx:02d}/{day_int:02d}/{year}",
        rf"{month_idx}-{day_int}-{year}",
        rf"{month_idx:02d}-{day_int:02d}-{year}",
    ]
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in day_patterns)


def _proper_name_words(text: str) -> list[str]:
    words: list[str] = []
    for token in re.split(r"[\s,;/]+", str(text or "")):
        cleaned = re.sub(r"[^A-Za-z'-]", "", token)
        if not cleaned:
            continue
        lower = cleaned.lower()
        if len(lower) <= 3 or lower in TITLE_STOPWORDS:
            continue
        if cleaned[0].isupper() or lower in {"dunleavy", "tucker"}:
            words.append(lower)
    return words


_GENERIC_NAME_TOKENS = {
    "governor",
    "senator",
    "representative",
    "president",
    "secretary",
    "attorney",
    "general",
    "office",
    "district",
}


def _name_is_grounded(name: str, source_text: str) -> bool:
    words = _proper_name_words(name)
    if not words:
        return True
    text_lower = (source_text or "").lower()
    specific = [word for word in words if word not in _GENERIC_NAME_TOKENS]
    if not specific:
        return all(word in text_lower for word in words)
    return all(word in text_lower for word in specific)


def _ground_sponsors(sponsors: str, source_text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    parts = [part.strip() for part in re.split(r",|;", sponsors) if part.strip()]
    kept: list[str] = []
    for part in parts:
        if _name_is_grounded(part, source_text):
            kept.append(part)
        else:
            warnings.append(f"sponsor {part!r} does not appear in the document text; cleared")
    return ", ".join(kept), warnings


_CHAMBER_CLAIM_TERMS = (
    "proclamation",
    "governor",
    "signed into law",
    "enacted",
    "vetoed",
)


def _chamber_details_is_grounded(details: str, source_text: str) -> bool:
    details_text = str(details or "").strip()
    if not details_text:
        return True
    text_lower = (source_text or "").lower()
    details_lower = details_text.lower()
    for term in _CHAMBER_CLAIM_TERMS:
        if term in details_lower and term not in text_lower:
            return False
    for name in _proper_name_words(details_text):
        if name not in text_lower:
            return False
    return True


def _session_is_grounded(session: str, source_text: str) -> bool:
    session_text = str(session or "").strip()
    if not session_text:
        return True
    text_lower = (source_text or "").lower()
    for name in _proper_name_words(session_text):
        if name not in text_lower:
            return False
    return True


def check_record_consistency(
    bill_data: dict,
    source_text: str,
    min_title_overlap: float = 0.34,
    *,
    source: str | None = None,
) -> ConsistencyResult:
    """Reconcile an LLM-derived record against the document it came from.

    Blocks the write when the document has no MMIP grounding or the title is
    unrelated to the page. Unverifiable bill numbers and ungrounded dates are
    stripped from `bill_data` and reported as warnings rather than blocking.
    """
    result = ConsistencyResult()
    record_source = str(source or bill_data.get("Source") or "").strip()
    skip_sponsor_chamber = record_source == "LegiScan"
    skip_session = skip_sponsor_chamber or record_source == "Federal Site"

    verdict = check_document_text(source_text, bill_data.get("Bill Text", ""))
    if not verdict:
        result.ok = False
        result.blocking_code = verdict.code
        result.blocking_detail = verdict.detail
        return result

    title = str(bill_data.get("Name") or "")
    overlap = title_overlap(title, source_text)
    if overlap < min_title_overlap:
        result.ok = False
        result.blocking_code = "title_not_in_document"
        result.blocking_detail = (
            f"only {overlap:.0%} of title words appear in the document: {title!r}"
        )
        return result

    bill_number = str(bill_data.get("Bill Number") or "").strip()
    if bill_number and not bill_number_in_text(bill_number, source_text, bill_data=bill_data):
        result.warnings.append(
            f"bill number {bill_number!r} does not appear in the document text; cleared"
        )
        bill_data["Bill Number"] = ""

    last_update = str(bill_data.get("Last Update") or "").strip()
    if last_update and not _date_is_grounded(last_update, source_text):
        result.warnings.append(
            f"Last Update {last_update!r} is not grounded in the document text; cleared"
        )
        bill_data["Last Update"] = ""

    if not skip_sponsor_chamber:
        sponsors = str(bill_data.get("Sponsors of the Legislation") or "").strip()
        if sponsors:
            grounded_sponsors, sponsor_warnings = _ground_sponsors(sponsors, source_text)
            result.warnings.extend(sponsor_warnings)
            if grounded_sponsors != sponsors:
                bill_data["Sponsors of the Legislation"] = grounded_sponsors

        chamber_details = str(bill_data.get("Chamber Details") or "").strip()
        if chamber_details and not _chamber_details_is_grounded(chamber_details, source_text):
            result.warnings.append(
                f"Chamber Details {chamber_details!r} is not grounded in the document text; cleared"
            )
            bill_data["Chamber Details"] = ""

    if not skip_session:
        session = str(bill_data.get("Session") or "").strip()
        if session and not _session_is_grounded(session, source_text):
            result.warnings.append(
                f"Session {session!r} is not grounded in the document text; cleared"
            )
            bill_data["Session"] = ""

    return result


def merge_warnings(existing: str, added: Iterable[str]) -> str:
    parts = [part.strip() for part in str(existing or "").split(";") if part.strip()]
    for item in added:
        if item and item not in parts:
            parts.append(item)
    return "; ".join(parts)
