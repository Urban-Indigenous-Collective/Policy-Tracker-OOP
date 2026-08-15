# Federal MMIP Crawl Sources

Federal discovery monitors **official federal government** listing pages and APIs — presidential executive orders, DOJ press releases, and all 93 U.S. Attorney (USAO) district office sites. LegiScan covers state bills only; federal policy lives on `.gov` sites outside that index.

All federal rows use `state: "National"` in config.

## Workflow

```bash
# 1. Bootstrap / refresh federal sources (Main v3 seeds + 93-district USAO template)
python scripts/bootstrap_federal_sources.py
# Optional: --probe to confirm /pr|/news listing HTTP status (never picks homepage)

# 2. Review sources/federal_sources.json — set review_needed=false on approved rows

# 3. Test DOJ News API (no browser)
python scripts/run_discovery.py --skip-legiscan --skip-state \
  --federal-source-id fed-doj-news --max-analyses 2 --dry-run

# 4. Federal Register API smoke (no browser)
python scripts/run_discovery.py --skip-legiscan --skip-state \
  --federal-source-id fed-fr-eo-search --max-analyses 1 --dry-run

# 5. Optional: one USAO district (Playwright; page 1 only — ?page=N is bot-walled)
python scripts/run_discovery.py --skip-legiscan --skip-state \
  --federal-source-id usao-ak --max-analyses 2 --dry-run

# 6. Production Docker Playwright smoke (run on WSL host after deploy)
docker compose exec scheduler python scripts/run_discovery.py \
  --skip-legiscan --skip-state --federal-source-id usao-ak --dry-run --max-analyses 2
# Expect: Playwright starts, page-1 /pr HTML (no ?page=1 bot-wall warning), sample_urls + any MMIP PR links
```

## Source layers

| Layer | content_type | method | Status |
|-------|--------------|--------|--------|
| Federal Register — Executive Orders | `executive_order` | `api` | **enabled** (`fed-fr-eo-search`) |
| DOJ — Press releases | `press_release` | `api` (News API title search) | **enabled** (`fed-doj-news`) |
| White House — Briefing room | `press_release` | `index` | `review_needed` |
| USAO — 93 district offices | `press_release` | `index` + `render_js` on `/pr` or `/news` | **enabled** (fragile; see below) |

### Federal Register (API)

Searches presidential documents (`type=PRESDOCU`) via the Federal Register JSON API:

```
https://www.federalregister.gov/api/v1/documents.json?conditions[type]=PRESDOCU&conditions[term]={query}&per_page=20
```

Search queries: `missing indigenous`, `MMIP`, `murdered indigenous women`, `murdered indigenous`.

Covers **both executive orders and proclamations** (`conditions[type]=PRESDOCU`; no subtype
filter). Title/term search only (not full document body). `per_page=20` with API pagination
via `next_page_url` (capped by source `max_pages`, default 5). Search snippets prefer API
`excerpts` / `abstract`; page text for analysis is fetched via the FR developer API (HTML pages
are bot-gated). Known docs reachable: Proclamation 10752 → FR doc `2024-10533`, EO 14053 →
`2021-25287`, task-force EO → `2019-26178`.

**Readiness: GREEN** — core MMIP EOs/proclamations are discoverable with paginated API search,
API-backed excerpts, and relaxed content-guard for thin presidential proclamations when title +
API snippet carry MMIP terms.

### DOJ (national) — prefer API, not HTML

**Working (plain HTTP + browser UA, no Playwright):**

| Endpoint | Result |
|----------|--------|
| `https://www.justice.gov/api/v1/press_releases.json?parameters[title]={query}&…` | JSON API — includes OPA **and** USAO PRs; title substring filter |
| `https://www.justice.gov/news/rss` | National RSS (~25 newest items); **not** keyword-filtered |

`fed-doj-news` uses the News API with queries `indigenous`, `MMIP`, `Missing and Murdered`, `tribal`. The fetcher paginates with `page=N` until results are exhausted or `max_pages` (default 5) is reached.

**Does not work for live listing crawl:**

| Endpoint | Result |
|----------|--------|
| `https://www.justice.gov/news` | Akamai `bm-verify` interstitial (~2KB) |
| `https://www.justice.gov/usao-*/pr` (plain HTTP) | Same bot wall |
| `https://www.justice.gov/usao-*/rss` etc. | 404 |
| `https://www.justice.gov/feeds/justice-news.xml?component[…]=…` (USAO hub feeds) | Redirects to `news/rss`; **district filters ignored** (all districts identical) |
| data.gov package search for DOJ press | Not a usable press feed |

Docs at [justice.gov/developer](https://www.justice.gov/developer) and the USAO feed index at [justice.gov/usao/rss](https://www.justice.gov/usao/rss) are real; the per-office XML links are currently broken as filters.

### USAO districts (93 offices)

One row per U.S. Attorney office. Bootstrapped from:

- **Main v3 Airtable** — known MMIP deep links stored in `sample_urls` (e.g. Alaska, Oregon, Western Michigan)
- **Canonical template** — `sources/usao_districts.json` (`office_url`, `press_url`, `news_url`)

**Crawl target (`url`)** is still the press/news **listing** with `render_js`. That path is
**fragile**: plain HTTP is Akamai-walled; Playwright works on page 1 from some IPs but
`?page=N` pagination URLs are bot-walled (sources are capped at `max_pages=1`).

When listing HTML is empty, only **`sample_urls`** yield known MMIP candidates (3 districts
have seeds today). Prefer relying on **`fed-doj-news` API** for new USAO/OPA discovery;
treat district `/pr` crawls as best-effort until a working per-district feed returns.

#### USAO investigation (2026-08-02)

| Question | Verdict |
|----------|---------|
| DOJ News API filter by USAO component? | **No** — `parameters[component]`, `component_uuid`, `path`, etc. are ignored; title search returns national + all districts. Post-filter by `/usao-{slug}/` in URL if needed. API yields ~43 MMIP/tribal title matches, ~35 with USAO URLs. |
| District RSS? | **No** — `feeds/justice-news.xml?component[…]=usao-ak` redirects to national `news/rss`; identical items. Per-district `/rss` 404. |
| Playwright on `/pr` listing? | **Yes on page 1** (Mac dev: 176KB HTML, 12 PR links for AK). Pipeline must not paginate to `?page=1` (bot wall). Production Docker untested here (SSH unavailable). |
| Seed `sample_urls` from Main v3? | **Yes** — re-run `python scripts/bootstrap_federal_sources.py` with Airtable creds; only AK/OR/WDMI have seeds today. |
| Disable 93 index crawls short-term? | **Not yet** — keep enabled at `max_pages=1`; they add page-1 MMIP hits when Playwright succeeds. Primary path is `fed-doj-news` + `sample_urls`. |

**Known MMIP pages (`sample_urls`)** — Main v3 seeds + Alaska hub:

| Office | Sample / seed |
|--------|----------------|
| USAO Alaska | `…/usao-ak/pr/pilot-projects-…`, awareness-day PR, `/missing-or-murdered-indigenous-persons` hub |
| USAO Western Michigan | `…/usao-wdmi/pr/2020_1218_MMIP` |
| USAO Oregon | `…/usao-or/page/file/…/download` (PDF seed; crawl URL still `/pr`) |

**Not used as crawl targets:** district Drupal `search/node` (404) and sitewide
`justice.gov/search` (403).

## Source config vs Pending review

| | Source config (`review_needed`) | Policy review (Airtable Pending) |
|---|--------------------------------|----------------------------------|
| Question | Should we crawl this URL nightly? | Should this analyzed policy go live? |
| Where | `sources/federal_sources.json` | Pending tab |

`Source=Federal Site` is a **Pending-only** single-select (not on Main v3).

## Manifest schema

Federal rows share the same schema as state sources (see [`discovery/federal_schema.py`](../discovery/federal_schema.py)):

| Field | Description |
|-------|-------------|
| `url` | Listing page (`/pr` or `/news`) for `index` method |
| `sample_urls` | Known MMIP deep links / hubs (also emitted as candidates) |
| `render_js` | Playwright fetch (required for justice.gov listings) |
| `office_url` | District homepage (metadata only — not crawled) |
| `press_url_template` | Canonical `…/pr` path |
| `review_needed` | `true` until human approves |

## Files

| Path | Purpose |
|------|---------|
| `sources/federal_sources.json` | Production config used by nightly crawler |
| `sources/usao_districts.json` | Canonical 93-district USAO template |
| `sources/federal_bootstrap_report.md` | Bootstrap summary |
| `discovery/federal_crawler.py` | `FederalSiteSource` orchestrator |
| `scripts/bootstrap_federal_sources.py` | Bootstrap / refresh script |
| `scripts/run_discovery.py` | `--federal-source-id`, `--skip-legiscan`, `--skip-state` |
