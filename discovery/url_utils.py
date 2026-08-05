"""URL and bill identity normalization for deduplication."""

from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """Normalize a URL for duplicate comparison."""
    text = (url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    scheme = (parsed.scheme or "https").lower()
    if scheme == "http":
        scheme = "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    # DOJ archived OPA press releases mirror live /opa/ paths on justice.gov.
    if netloc.endswith("justice.gov") and path.startswith("/archives/"):
        path = path[len("/archives") :] or "/"
        path = path.rstrip("/") or "/"
    # Ignore fragments; keep query (some legislatures use it)
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def normalize_state(state: str) -> str:
    return str(state or "").strip().upper()


def normalize_bill_number(bill_number: str) -> str:
    return "".join(str(bill_number or "").upper().split())


def bill_identity_key(state: str, bill_number: str) -> tuple[str, str] | None:
    state_key = normalize_state(state)
    bill_key = normalize_bill_number(bill_number)
    if not state_key or not bill_key:
        return None
    return state_key, bill_key
