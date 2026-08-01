import logging
import os
import time
from typing import Iterator

from api_client import APIClient
from discovery.models import Candidate, utc_now_iso
from discovery.queries import MMIP_QUERIES

logger = logging.getLogger(__name__)


class LegiScanSearchSource:
    """Discover MMIP-related bills via LegiScan getSearchRaw + getBill hydration."""

    def __init__(self, api_client: APIClient, year: int | None = None):
        self.api = api_client
        self.year = year or int(os.getenv("DISCOVERY_LEGISCAN_YEAR", "2"))
        self._bill_cache: dict[str, dict] = {}

    def _hydrate_bill(self, bill_id: str) -> dict | None:
        if bill_id in self._bill_cache:
            return self._bill_cache[bill_id]

        data = self.api.get_bill_details(bill_id)
        if not isinstance(data, dict) or data.get("status") != "OK":
            logger.warning("getBill failed for bill_id=%s", bill_id)
            return None

        bill = data.get("bill") or {}
        self._bill_cache[bill_id] = bill
        time.sleep(0.2)
        return bill

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

                    bill = self._hydrate_bill(bill_id)
                    if not bill:
                        continue

                    history = bill.get("history") or []
                    last_action = history[-1].get("action", "") if history else ""

                    yield Candidate(
                        source="legiscan",
                        state=str(bill.get("state") or item.get("state") or ""),
                        url=str(bill.get("url") or item.get("url") or ""),
                        title=str(bill.get("title") or item.get("title") or ""),
                        snippet=str(
                            last_action or item.get("last_action") or item.get("description") or ""
                        ),
                        external_id=bill_id,
                        change_hash=str(item.get("change_hash") or ""),
                        discovered_at=utc_now_iso(),
                        relevance=int(item.get("relevance") or 0),
                    )

        logger.info("LegiScan discovery complete, unique bills=%d", len(seen_bill_ids))
