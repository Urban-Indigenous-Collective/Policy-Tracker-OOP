import logging
import os
from typing import Iterator

from api_client import APIClient
from discovery.models import Candidate, utc_now_iso
from discovery.queries import MMIP_QUERIES

logger = logging.getLogger(__name__)


class LegiScanSearchSource:
    """Discover MMIP-related bills via LegiScan getSearchRaw (no getBill hydration)."""

    def __init__(self, api_client: APIClient, year: int | None = None):
        self.api = api_client
        self.year = year or int(os.getenv("DISCOVERY_LEGISCAN_YEAR", "2"))

    def discover(self, queries: list[str] | None = None) -> Iterator[Candidate]:
        queries = queries or MMIP_QUERIES
        seen_bill_ids: set[str] = set()

        for query in queries:
            logger.info("LegiScan search query: %s", query)
            for page_data in self.api.iter_search_raw_pages(query, state="ALL", year=self.year):
                searchresult = page_data.get("searchresult") or {}
                results = searchresult.get("results") or []
                if isinstance(results, dict):
                    results = list(results.values())

                for item in results:
                    if not isinstance(item, dict):
                        continue
                    bill_id = str(item.get("bill_id") or "")
                    if not bill_id or bill_id in seen_bill_ids:
                        continue
                    seen_bill_ids.add(bill_id)

                    yield Candidate(
                        source="legiscan",
                        state=str(item.get("state") or ""),
                        url=str(item.get("url") or ""),
                        title=str(item.get("title") or ""),
                        snippet=str(
                            item.get("last_action")
                            or item.get("description")
                            or item.get("summary")
                            or ""
                        ),
                        external_id=bill_id,
                        change_hash=str(item.get("change_hash") or ""),
                        discovered_at=utc_now_iso(),
                        relevance=int(item.get("relevance") or 0),
                    )

        logger.info("LegiScan discovery complete, unique bills=%d", len(seen_bill_ids))
