import logging
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

from legiscan_cache import LegiScanCache

logger = logging.getLogger(__name__)

_OVERLIMIT_MARKERS = (
    "overlimit",
    "over limit",
    "query limit",
    "monthly limit",
    "quota",
    "exceeded",
    "30,000",
    "30000",
)


class LegiScanAPIError(Exception):
    """LegiScan API returned status=ERROR."""


class LegiScanOverlimitError(LegiScanAPIError):
    """Monthly query quota exhausted — do not retry."""


class LegiScanBudgetExceededError(Exception):
    """Per-job network query budget exceeded."""


class LegiScanDisabledError(Exception):
    """LegiScan API disabled via LEGISCAN_API_ENABLED=false."""


@dataclass
class LegiScanOpStats:
    network: int = 0
    memory_cache_hit: int = 0
    sqlite_cache_hit: int = 0
    by_op: Counter = field(default_factory=Counter)

    def record(self, op: str, source: str) -> None:
        self.by_op[op] += 1
        if source == "network":
            self.network += 1
        elif source == "memory":
            self.memory_cache_hit += 1
        elif source == "sqlite":
            self.sqlite_cache_hit += 1

    def log_summary(self) -> None:
        logger.info(
            "legiscan_ops network=%d memory_cache_hit=%d sqlite_cache_hit=%d by_op=%s",
            self.network,
            self.memory_cache_hit,
            self.sqlite_cache_hit,
            dict(self.by_op),
        )


class APIClient:
    LIST_CACHE_OPS = frozenset({"getSessionList", "getMasterList", "getMasterListRaw"})

    def __init__(self, api_key, cache: LegiScanCache | None = None):
        self.api_key = api_key
        self._memory_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._sqlite_cache = cache if cache is not None else LegiScanCache()
        self.stats = LegiScanOpStats()
        self._network_budget = int(os.getenv("LEGISCAN_MAX_NETWORK_QUERIES_PER_JOB", "800"))
        self._api_enabled = os.getenv("LEGISCAN_API_ENABLED", "true").lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        self.quota_exhausted = False
        self.last_error_alert = ""

    def mark_quota_exhausted(self, reason: str) -> None:
        self.quota_exhausted = True
        if reason:
            self.last_error_alert = reason

    def response_indicates_overlimit(self, data: dict[str, Any] | None) -> bool:
        if not data:
            return self.quota_exhausted
        text = json_dumps_safe(data).lower()
        return any(marker in text for marker in _OVERLIMIT_MARKERS)

    def get_api_key(self):
        return self.api_key

    def log_stats(self) -> None:
        self.stats.log_summary()

    def _param_key(self, params: dict[str, Any]) -> str:
        return "|".join(f"{k}={params[k]}" for k in sorted(params))

    def _check_enabled(self) -> None:
        if not self._api_enabled:
            raise LegiScanDisabledError("LegiScan API disabled (LEGISCAN_API_ENABLED=false)")
        if self.quota_exhausted:
            raise LegiScanOverlimitError(
                self.last_error_alert or "LegiScan API monthly limit reached"
            )

    def _check_budget(self) -> None:
        if self._network_budget and self.stats.network >= self._network_budget:
            raise LegiScanBudgetExceededError(
                f"LegiScan network query budget exceeded ({self._network_budget})"
            )

    def _is_overlimit(self, data: dict[str, Any]) -> bool:
        alert = str(data.get("alert") or "").lower()
        if any(marker in alert for marker in _OVERLIMIT_MARKERS):
            return True
        message = str(data.get("status") or "").upper()
        if message == "ERROR":
            text = json_dumps_safe(data).lower()
            return any(marker in text for marker in _OVERLIMIT_MARKERS)
        return False

    def _validate_response(self, data: dict[str, Any] | None, endpoint: str) -> dict[str, Any] | None:
        if not data:
            return None
        status = str(data.get("status") or "").upper()
        if status == "OK":
            return data
        if self._is_overlimit(data):
            reason = str(data.get("alert") or data)
            self.mark_quota_exhausted(reason)
            raise LegiScanOverlimitError(
                f"LegiScan quota exceeded on {endpoint}: {data.get('alert', data)}"
            )
        if status == "ERROR":
            reason = str(data.get("alert") or data)
            if self.response_indicates_overlimit(data):
                self.mark_quota_exhausted(reason)
                raise LegiScanOverlimitError(
                    f"LegiScan quota exceeded on {endpoint}: {data.get('alert', data)}"
                )
            raise LegiScanAPIError(f"LegiScan error on {endpoint}: {data.get('alert', data)}")
        return data

    def _get_cached(self, endpoint: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        key = self._param_key(params)
        mem_key = (endpoint, key)
        if mem_key in self._memory_cache:
            self.stats.record(endpoint, "memory")
            return self._memory_cache[mem_key]
        if endpoint in self.LIST_CACHE_OPS:
            cached = self._sqlite_cache.get(endpoint, key)
            if cached is not None:
                self._memory_cache[mem_key] = cached
                self.stats.record(endpoint, "sqlite")
                return cached
        return None

    def _store_cached(self, endpoint: str, params: dict[str, Any], data: dict[str, Any]) -> None:
        key = self._param_key(params)
        mem_key = (endpoint, key)
        self._memory_cache[mem_key] = data
        if endpoint in self.LIST_CACHE_OPS:
            self._sqlite_cache.set(endpoint, key, data)

    def _make_request(self, endpoint, params=None, retries=3):
        self._check_enabled()
        params = params or {}
        cached = self._get_cached(endpoint, params)
        if cached is not None:
            return cached

        url = f"https://api.legiscan.com/?key={self.api_key}&op={endpoint}"
        for attempt in range(retries):
            self._check_budget()
            logger.debug("LegiScan request: op=%s params=%s", endpoint, params)
            response = requests.get(url, params=params, timeout=60)
            if response.status_code == 200:
                data = response.json()
                try:
                    data = self._validate_response(data, endpoint)
                except LegiScanOverlimitError:
                    self.mark_quota_exhausted(str(data.get("alert") if isinstance(data, dict) else data))
                    raise
                except LegiScanAPIError:
                    logger.error("LegiScan API error op=%s body=%s", endpoint, str(data)[:200])
                    return None
                if data is not None:
                    self.stats.record(endpoint, "network")
                    if endpoint in self.LIST_CACHE_OPS:
                        self._store_cached(endpoint, params, data)
                    else:
                        self._memory_cache[(endpoint, self._param_key(params))] = data
                return data
            if response.status_code == 429:
                delay = 2**attempt
                logger.warning("LegiScan rate limit, retry in %ss", delay)
                time.sleep(delay)
                continue
            logger.error(
                "LegiScan error status=%s body=%s",
                response.status_code,
                response.text[:200],
            )
            return None
        return None

    def get_session_list(self, state: str) -> dict[str, Any] | None:
        data = self._make_request("getSessionList", {"state": state})
        return data if isinstance(data, dict) else None

    def get_master_list(self, session_id: int | str) -> dict[str, Any] | None:
        data = self._make_request("getMasterList", {"id": session_id})
        return data if isinstance(data, dict) else None

    def get_master_list_raw(self, session_id: int | str) -> dict[str, Any] | None:
        data = self._make_request("getMasterListRaw", {"id": session_id})
        return data if isinstance(data, dict) else None

    def get_bill_text(self, bill_id):
        data = self._make_request("getBillText", {"id": bill_id})
        if not data:
            return None
        if "text" in data:
            return data["text"]
        return data

    def get_bill_text_doc(self, doc_id):
        return self.get_bill_text(doc_id)

    def get_bill_details(self, bill_id):
        if not bill_id:
            return "Invalid Bill ID"
        return self._make_request("getBill", {"id": bill_id})

    def get_search_raw(self, query, state="ALL", year=2, page=1, session_id=None):
        params = {"query": query, "page": page}
        if session_id:
            params["id"] = session_id
        else:
            params["state"] = state
            params["year"] = year
        return self._make_request("getSearchRaw", params)

    def get_search(self, query, state="ALL", year=2, page=1, session_id=None):
        params = {"query": query, "page": page}
        if session_id:
            params["id"] = session_id
        else:
            params["state"] = state
            params["year"] = year
        return self._make_request("getSearch", params)

    def get_dataset_list(self, state: str = "ALL") -> dict[str, Any] | None:
        data = self._make_request("getDatasetList", {"state": state})
        return data if isinstance(data, dict) else None

    def get_dataset(self, session_id: int | str, access_key: str = "") -> dict[str, Any] | None:
        params: dict[str, Any] = {"id": session_id}
        if access_key:
            params["access_key"] = access_key
        data = self._make_request("getDataset", params)
        return data if isinstance(data, dict) else None

    def iter_search_raw_pages(self, query, state="ALL", year=2, max_pages=None):
        page = 1
        while True:
            data = self.get_search_raw(query, state=state, year=year, page=page)
            if self.quota_exhausted:
                break
            if not data or data.get("status") != "OK":
                if self.response_indicates_overlimit(data if isinstance(data, dict) else None):
                    self.mark_quota_exhausted(str((data or {}).get("alert") or "search blocked"))
                break
            yield data
            summary = (data.get("searchresult") or {}).get("summary") or {}
            page_total = int(summary.get("page_total") or 1)
            if page >= page_total:
                break
            if max_pages and page >= max_pages:
                break
            page += 1
            time.sleep(0.5)


def json_dumps_safe(data: Any) -> str:
    import json

    try:
        return json.dumps(data)
    except (TypeError, ValueError):
        return str(data)
