"""In-memory index of records already in Main v3 or Pending."""

import logging
from typing import Iterable

from airtable_fields import BILL_OVERVIEW_LINK_FIELD
from discovery.url_utils import bill_identity_key, normalize_url

logger = logging.getLogger(__name__)

URL_FIELDS = [BILL_OVERVIEW_LINK_FIELD, "Bill Text", "Optional Link", "Bill Overview"]


class AirtableDuplicateIndex:
    """Caches known URLs and state/bill-number pairs from Main v3 and Pending."""

    def __init__(self, airtable_client):
        self.airtable = airtable_client
        self._urls: set[str] = set()
        self._bill_keys: set[tuple[str, str]] = set()
        self._loaded = False

    def refresh(self) -> None:
        self._urls.clear()
        self._bill_keys.clear()
        for table in (self.airtable.live_table, self.airtable.pending_table):
            self._index_table(table)
        self._loaded = True
        logger.info(
            "Duplicate index loaded: %d URLs, %d state/bill pairs",
            len(self._urls),
            len(self._bill_keys),
        )

    def _index_table(self, table) -> None:
        try:
            records = table.all()
        except Exception as exc:
            logger.warning("Failed to load duplicate index from table: %s", exc)
            return
        for record in records:
            fields = record.get("fields") or {}
            for field in URL_FIELDS:
                url = fields.get(field)
                if url and isinstance(url, str):
                    normalized = normalize_url(url)
                    if normalized:
                        self._urls.add(normalized)
            key = bill_identity_key(
                fields.get("State", ""),
                fields.get("Bill Number", ""),
            )
            if key:
                self._bill_keys.add(key)

    def is_duplicate(
        self,
        url: str,
        state: str = "",
        bill_number: str = "",
    ) -> bool:
        if not self._loaded:
            self.refresh()

        normalized = normalize_url(url)
        if normalized and normalized in self._urls:
            return True

        key = bill_identity_key(state, bill_number)
        if key and key in self._bill_keys:
            return True
        return False

    def register(
        self,
        url: str = "",
        state: str = "",
        bill_number: str = "",
        extra_urls: Iterable[str] | None = None,
    ) -> None:
        """Track a newly written Pending record so later candidates in the same run dedupe."""
        if url:
            normalized = normalize_url(url)
            if normalized:
                self._urls.add(normalized)
        for extra in extra_urls or []:
            normalized = normalize_url(extra)
            if normalized:
                self._urls.add(normalized)
        key = bill_identity_key(state, bill_number)
        if key:
            self._bill_keys.add(key)
