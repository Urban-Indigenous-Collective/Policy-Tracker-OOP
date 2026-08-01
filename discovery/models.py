from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Candidate:
    """A discovered policy item awaiting relevance review and analysis."""

    source: str  # "legiscan" | "state_site"
    state: str
    url: str
    title: str
    snippet: str = ""
    external_id: str = ""
    change_hash: str = ""
    content_hash: str = ""
    discovered_at: str = field(default_factory=utc_now_iso)
    relevance: Optional[int] = None

    def dedupe_key(self) -> str:
        return self.url.strip().lower()
