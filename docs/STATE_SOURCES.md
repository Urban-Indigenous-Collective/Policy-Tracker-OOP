# State MMIP Crawl Sources

State discovery monitors **official state government** listing pages, site search endpoints, and RSS feeds — not individual documents. LegiScan searches bill metadata/text via API (2020+), but **official legislature and agency sites** can still surface committee reports, session documents, press releases, and other material LegiScan may not index — keep those as separate crawl targets when the URL is a real listing page.

## Workflow

```bash
# 1. Bootstrap manifests (51 states + DC)
python scripts/bootstrap_state_sources_agents.py

# 2. Review sources/manifests/*.json — set review_needed=false on approved rows

# 3. Merge into production config
python scripts/merge_state_manifests.py

# 4. Validate enabled sources
python scripts/validate_state_sources.py --enabled-only

# 5. Dry-run crawl for one state
python scripts/run_state_crawl.py --state NC --include-review --verbose

# 6. Per-state audit (HTTP smoke test + MMIP prescreen counts)
python scripts/audit_state_sources.py
# → sources/audit_report.md
```

## Source config vs Pending review

| | Source config (`review_needed`) | Policy review (Airtable Pending) |
|---|--------------------------------|----------------------------------|
| Question | Should we crawl this URL nightly? | Should this analyzed policy go live? |
| Where | `sources/state_sources.json` | Pending tab |

All bootstrap output starts with `review_needed: true`. The nightly crawler **ignores** those until you approve them.

## Manifest schema

Each source row:

| Field | Description |
|-------|-------------|
| `state` | Two-letter code |
| `name` | Human label |
| `content_type` | `press_release`, `proclamation`, `executive_order`, `letter`, `legislation`, `report`, `other` |
| `method` | `index`, `search`, `rss`, or `api` |
| `url` | Listing page (index method) |
| `search_url` | Template with `{query}` (search method) |
| `search_queries` | Plain-language queries for search / api methods |
| `rss_url` | Feed URL (rss method) |
| `api_url_template` | JSON API URL with `{query}` and `{api_key}` (api method) |
| `api_key_env` | Env var name for API key (api method) |
| `ssl_verify` | Set `false` when a site has an incomplete TLS chain |
| `render_js` | `true` to fetch with headless Chromium (JS-rendered pages) |
| `browser_wait_selector` | CSS selector to wait for after page load (e.g. `table.dataTable tbody tr`) |
| `browser_click_selector` | Optional click before search input (e.g. keyword radio on VT) |
| `browser_input_selector` | Search input for browser form submit |
| `browser_submit_selector` | Submit control for browser search |
| `link_selector` | Restrict link extraction (e.g. `a[href*='bill/status/']`) |
| `review_needed` | `true` until human approves |
| `confidence` | `high`, `medium`, `low` |

Defined in [`discovery/source_schema.py`](../discovery/source_schema.py).

## North Carolina example

Multiple approved sources per state:

| Source | method | content_type |
|--------|--------|--------------|
| NC Admin public affairs | index | report |
| Governor news | index | press_release |
| nc.gov search | search | other |

See [`sources/manifests/NC.json`](../sources/manifests/NC.json) after bootstrap.

## New York (nysenate.gov blocked)

`www.nysenate.gov` returns **HTTP 403** to automated clients (even with a browser user-agent). Use instead:

| Source | method | Notes |
|--------|--------|-------|
| NY Assembly press | index | `https://www.nyassembly.gov/Press/` |
| NY Assembly search | search | Server-rendered; works with MMIP queries |
| NY Governor news | index | `https://www.governor.ny.gov/news` |
| Open Legislation API | api | Free key at [legislation.nysenate.gov](https://legislation.nysenate.gov/); set `NY_OPEN_LEGISLATION_KEY` in `.env` |

Bill detail pages load at `https://legislation.nysenate.gov/bills/{year}/{printNo}` (200 OK) even when `nysenate.gov` is blocked.

### NY executive orders / proclamations (Cloudflare UA trap)

`governor.ny.gov` EO and proclamation indexes **work from prod** with the default crawler UA (`UIC-PolicyTracker/1.0`). Do **not** set a Chrome-spoof `user_agent` on those sources — Cloudflare returns HTTP 403 for full Chrome UAs from the datacenter IP while allowing the honest bot UA.

| Source | method | Notes |
|--------|--------|-------|
| Governor executive orders | index | `https://www.governor.ny.gov/executiveorders` — leave `user_agent` empty |
| Governor proclamations | index | `https://www.governor.ny.gov/proclamations` — leave `user_agent` empty |
| NYSED OP COVID EOs | index | Supplemental healthcare/professions EO list on `op.nysed.gov` |

`dos.ny.gov` State Register also publishes EOs but is Cloudflare-blocked from prod (403). Open Legislation API covers bills only, not EOs. Direct PDF URLs under `governor.ny.gov/sites/default/files/` are fetchable when you already know the path.

## Search queries

Gov site search uses plain phrases (not LegiScan boolean):

- `missing and murdered indigenous`
- `MMIP` / `MMIW`
- `missing persons indigenous`
- `murdered indigenous`
- `tribal missing persons`

## JS-rendered legislature pages (Playwright)

Some state legislature sites (e.g. Vermont) load bill tables via JavaScript. For those sources set `render_js: true` in the manifest and install Playwright on the crawler host:

```bash
pip install playwright
playwright install chromium
```

Optional manifest fields for interactive search forms:

- `browser_click_selector` — e.g. `#Form_BillSearchForm_SearchBy_keyword`
- `browser_input_selector` — keyword field
- `browser_submit_selector` — submit button

**Docker / production:** Add Playwright + Chromium to the scheduler image, or run discovery on a host with browsers installed. If `PLAYWRIGHT_BROWSERS_PATH` points at a sandbox cache with the wrong CPU arch, unset it and re-run `playwright install chromium`.

Test Vermont:

```bash
unset PLAYWRIGHT_BROWSERS_PATH
python scripts/test_vt_sources.py
```

## Files

| Path | Purpose |
|------|---------|
| `sources/manifests/{ST}.json` | Per-state bootstrap output |
| `sources/state_sources.json` | Merged config used by nightly crawler |
| `sources/bootstrap_report.md` | Bootstrap summary |
| `discovery/fetchers.py` | Index, search, RSS fetchers |
| `discovery/browser_fetcher.py` | Playwright headless renderer |
| `discovery/site_crawler.py` | Orchestrator |
