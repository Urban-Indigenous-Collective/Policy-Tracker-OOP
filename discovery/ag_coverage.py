"""State Attorney General crawl coverage.

Governor / legislature / SOS sources do not see AG press rooms. This module is the
canonical map of AG hosts so bootstrap, coverage audit, and tests agree on whether
a source actually watches the AG office.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
AG_HOSTS_PATH = ROOT / "sources" / "ag_hosts.json"


def load_ag_hosts(path: Path | None = None) -> dict[str, dict]:
    target = path or AG_HOSTS_PATH
    with open(target, encoding="utf-8") as f:
        data = json.load(f)
    return {str(state).upper(): dict(entry) for state, entry in data.items()}


def _host(url_or_host: str) -> str:
    raw = (url_or_host or "").strip().lower()
    if "://" in raw:
        raw = urlparse(raw).netloc
    return raw.removeprefix("www.")


def _path_matches(path: str, prefix: str) -> bool:
    path = (path or "/").lower().rstrip("/") or "/"
    prefix = prefix.lower().rstrip("/")
    if not prefix:
        return True
    if path == prefix:
        return True
    # "/ag" must not match "/agriculture"; "/orgs/office-of-attorney-general"
    # must match mass.gov slugs like "...-andrea-joy-campbell/news".
    return path.startswith(prefix + "/") or path.startswith(prefix + "-")


def url_matches_ag(state: str, url: str, hosts: dict[str, dict] | None = None) -> bool:
    """True when url is on this state's Attorney General host (and path, if scoped)."""
    hosts = hosts if hosts is not None else load_ag_hosts()
    entry = hosts.get((state or "").upper())
    if not entry or not url:
        return False
    parsed = urlparse(url)
    if _host(parsed.netloc) != _host(str(entry.get("host") or "")):
        return False
    prefix = str(entry.get("path_prefix") or "")
    return _path_matches(parsed.path, prefix)


def source_matches_ag(source: dict, hosts: dict[str, dict] | None = None) -> bool:
    state = str(source.get("state") or "")
    url = (
        source.get("url")
        or source.get("search_url")
        or source.get("rss_url")
        or source.get("api_url_template")
        or ""
    )
    return url_matches_ag(state, str(url), hosts)


def states_missing_ag(
    sources_by_state: dict[str, list[dict]],
    *,
    include_review: bool = False,
    hosts: dict[str, dict] | None = None,
) -> list[str]:
    hosts = hosts if hosts is not None else load_ag_hosts()
    missing: list[str] = []
    for state in sorted(hosts):
        rows = sources_by_state.get(state, [])
        if not include_review:
            rows = [s for s in rows if not s.get("review_needed", True)]
        if not any(source_matches_ag(s, hosts) for s in rows):
            missing.append(state)
    return missing
