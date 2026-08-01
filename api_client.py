import logging
import time

import requests

logger = logging.getLogger(__name__)


class APIClient:
    def __init__(self, api_key):
        self.api_key = api_key

    def _make_request(self, endpoint, params=None, retries=3):
        url = f"https://api.legiscan.com/?key={self.api_key}&op={endpoint}"
        params = params or {}
        for attempt in range(retries):
            logger.debug("LegiScan request: op=%s params=%s", endpoint, params)
            response = requests.get(url, params=params, timeout=60)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                delay = 2 ** attempt
                logger.warning("LegiScan rate limit, retry in %ss", delay)
                time.sleep(delay)
                continue
            logger.error("LegiScan error status=%s body=%s", response.status_code, response.text[:200])
            return None
        return None

    def get_api_key(self):
        return self.api_key

    def get_bill_text(self, bill_id):
        data = self._make_request('getBillText', {'id': bill_id})
        return data['text'] if data and 'text' in data else None

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

    def iter_search_raw_pages(self, query, state="ALL", year=2, max_pages=None):
        page = 1
        while True:
            data = self.get_search_raw(query, state=state, year=year, page=page)
            if not data or data.get("status") != "OK":
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