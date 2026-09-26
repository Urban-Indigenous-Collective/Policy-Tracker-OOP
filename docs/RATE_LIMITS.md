# Rate limits and quotas

The tracker depends on two metered APIs. They fail in different ways, and the fixes for one do not help the other.

| Limit | Symptom | What helps |
|-------|---------|------------|
| Airtable ~5 requests/second per base | `too many 429 error responses`, `Max retries exceeded` | Shared pacing, stopping on the first limit error instead of retrying |
| Airtable monthly billing cap | `PUBLIC_API_BILLING_LIMIT_EXCEEDED` | Making fewer calls; stopping early. Pacing does not help. |
| LegiScan monthly quota (~30k queries, resets on the 1st) | `LegiScanOverlimitError`, `getBill` failures | Change-hash skips, the `getBill` cache, `LEGISCAN_MAX_NETWORK_QUERIES_PER_JOB` |

## Where the calls come from

The nightly pipeline in `scheduler.py` runs discovery, then status refresh, then (optionally) validation refresh, then an approval-sync catch-up and webhook refresh. Separately, the `web` container runs approval sync whenever Airtable pings `/webhooks/airtable`. Both containers can hit Airtable at the same time.

- **Discovery** loads Main v3 and Pending once per run into `AirtableDuplicateIndex` and dedupes candidates in memory. It no longer queries Airtable per candidate.
- **Status refresh** reads all of Pending and Main v3, then updates changed rows. LegiScan `getBill` is only called when the masterlist change hash differs, and responses are cached in `data/legiscan_api_cache.db` keyed by `bill_id` and change hash.
- **Approval sync** does a duplicate check, a create, an optional verify (`APPROVAL_SYNC_VERIFY_WRITES`), and a delete per moved record. It holds `data/approval_sync.lock`, so webhook and nightly syncs never overlap.
- **Validation refresh** reads all of Pending and writes one update per changed row. It is off by default (`VALIDATION_REFRESH_ENABLED=false`).

## Shared pacing

Every Airtable HTTP call goes through `PacedApi` in `airtable_client.py`, which waits on `airtable_pace.wait_turn()`. That function keeps a timestamp in `data/airtable_pace.db` behind a file lock, so the web and scheduler containers (which share the `discovery_data` volume) together send at most one request every `AIRTABLE_MIN_INTERVAL_SEC` (default 0.21s, just under 5/s). Set `AIRTABLE_PACE_ENABLED=false` to turn it off.

## Behavior when a limit is hit

Discovery, status refresh, validation refresh, approval sync, and webhook refresh all stop at the first Airtable rate or billing limit error, log a warning, and leave remaining work for the next run. They do not post Slack error alerts for these. Discovery and status refresh record `airtable_rate_limited` in the deferred Slack report.

## Settings

| Variable | Default | Purpose |
|----------|---------|---------|
| `AIRTABLE_PACE_ENABLED` | `true` | Cross-process request spacing |
| `AIRTABLE_MIN_INTERVAL_SEC` | `0.21` | Minimum gap between Airtable calls |
| `AIRTABLE_RETRY_TOTAL` / `AIRTABLE_RETRY_BACKOFF` | `6` / `2` | urllib3 retry on 429/5xx |
| `APPROVAL_SYNC_VERIFY_WRITES` | `true` | Re-read records after approval sync creates them |
| `LEGISCAN_GETBILL_CACHE_TTL_HOURS` | `18` | Lifetime of cached `getBill` responses |
| `LEGISCAN_MAX_NETWORK_QUERIES_PER_JOB` | `800` | Per-job LegiScan budget |

Operationally: keep `APPROVAL_SYNC_INTERVAL_MIN=0` (webhooks plus nightly catch-up), keep validation refresh off unless needed, and avoid running backfill or audit scripts on the same night as the full pipeline.

## Checking before and after a deploy

Run the relevant tests:

```bash
.venv/bin/python -m pytest -q tests/test_dedup.py tests/test_pipeline_dedup.py tests/test_airtable_pace.py \
  tests/test_approval_sync.py tests/test_airtable_rate_limit.py tests/test_api_client.py \
  tests/test_status_refresh.py tests/test_scheduler_nightly_pipeline.py
```

After GitHub CD finishes, confirm the prod image imports the new modules:

```bash
docker compose exec scheduler python -c "import airtable_pace, discovery.dedup, discovery.pipeline, discovery.status_refresh"
docker compose exec web python -c "import airtable_pace, airtable_client"
```

After the next nightly run, check the scheduler logs for `Duplicate index loaded`, the `legiscan_ops ... sqlite_cache_hit=` line, and any `Airtable rate/billing limit` warnings.
