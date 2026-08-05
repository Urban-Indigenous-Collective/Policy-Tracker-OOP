# Indigenous Ethnicity Enrichment Plan

Wikipedia-based tribal affiliation enrichment for the indigenous politician roster.

**Status:** Plan only (not implemented)  
**Last updated:** 2026-08-05  
**Context:** 755 deduped roster entries; **220** have `ethnicity: "N/A"` (category-only stubs). Feasibility work confirms Wikipedia intro extract is best ROI; Wikidata is sparse; re-scraping the list page does not fix category stubs.

---

## Problem statement

Category ingestion in `indigenous_database.py` adds page titles from Wikipedia categories with hardcoded `ethnicity: "N/A"`. List-page rows already carry ethnicity. After dedupe, high-impact legislators (James Ramos, Mary Kunesh, Sharice Davids, etc.) remain matched as indigenous but produce **no tribe parenthetical** in `process_sponsors()`.

Parallel work may add `data/indigenous_ethnicity_overrides.json` for hand-curated high-impact names. This plan covers **automated Wikipedia enrichment** for the remaining stubs and defines how both layers compose.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│  data/indigenous_politicians.json  (canonical roster cache)     │
│  built by build_database() / refresh_indigenous_db.py           │
└────────────────────────────┬────────────────────────────────────┘
                             │ load_from_disk() / ensure_loaded()
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  indigenous_database.py                                         │
│  1. Load roster from disk                                       │
│  2. Merge ethnicity sidecars (priority order below)             │
│  3. Dedupe + _pick_richer for twins                             │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
  overrides.json      enrichment.json      (inline roster fields)
  (manual, parallel)  (script output)      (list-page known)
         │                   │
         └─────────┬─────────┘
                   ▼
         sponsor_utils.process_sponsors()
                   ▼
         backfill_indigenous_sponsorship.py → Airtable
```

**Merge priority (highest wins for ethnicity):**

1. `data/indigenous_ethnicity_overrides.json` — human-verified; never overwritten by enricher
2. Inline roster value when not `N/A` (list-page / manual_adjustments)
3. `data/indigenous_ethnicity_enrichment.json` — automated Wikipedia extractions
4. Default `N/A`

---

## 1. `scripts/enrich_indigenous_ethnicity.py` design

### Purpose

Batch-fetch Wikipedia metadata for roster entries with `ethnicity == "N/A"`, extract tribal affiliation from intro text (primary) and optional fallbacks, validate, and write results to the enrichment sidecar (not directly into the roster cache).

### CLI surface

```bash
# Dry-run: report only, no writes
python scripts/enrich_indigenous_ethnicity.py

# Target MVP cohort (Airtable high-impact names)
python scripts/enrich_indigenous_ethnicity.py --mvp

# Full N/A batch
python scripts/enrich_indigenous_ethnicity.py --all-na

# Explicit name list
python scripts/enrich_indigenous_ethnicity.py --names "James Ramos" "Mary Kunesh"

# Apply accepted results to sidecar
python scripts/enrich_indigenous_ethnicity.py --mvp --apply

# Force re-fetch (ignore enrichment cache TTL)
python scripts/enrich_indigenous_ethnicity.py --all-na --refresh

# Output report path
python scripts/enrich_indigenous_ethnicity.py --report scripts/reports/enrichment_YYYYMMDD.json
```

Follow existing script conventions: dry-run by default, `--apply` to write, structured JSON report + human-readable summary.

### Target selection

| Mode | Selection logic |
|------|-----------------|
| `--mvp` | Intersection of (a) roster N/A stubs and (b) names appearing in Airtable `Indigenous Sponsorship` or `Sponsors of the Legislation` on pending/live, plus hardcoded spot-check list from `compare_indigenous_sponsorship.py` |
| `--all-na` | All 220 deduped entries where merged ethnicity is still `N/A` and not in overrides |
| `--names` | Explicit list; normalize via `IndigenousDatabase._normalize_roster_name()` |

Build MVP cohort once via helper `discover_mvp_targets(roster, airtable_client) -> list[str]` and cache in report for reproducibility.

### Wikipedia API flow (per name)

Use **MediaWiki Action API** (`https://en.wikipedia.org/w/api.php`), not HTML scraping. Reuse `requests.Session()` pattern from `wikipedia_api_client.py`.

**Step A — Resolve page title**

Many roster titles are bare names (`"James Ramos"`) while Wikipedia uses disambiguation pages (`James Ramos (politician)`).

1. **Direct query** — `action=query&titles={title}&redirects=1`
2. If `missing` → **OpenSearch** — `action=opensearch&search={name}&limit=5&namespace=0`
3. Score candidates:
   - Title contains `politician`, `representative`, `senator`, or state name
   - Levenshtein / token match against roster name
   - Reject disambiguation index pages (`"(disambiguation)"`)
4. If top candidate confidence < threshold → mark `status: "disambiguation_unresolved"`, skip auto-apply

**Step B — Fetch intro extract (primary)**

```
action=query
prop=extracts
exintro=1
explaintext=1
redirects=1
titles={resolved_title}
```

**Step C — Optional infobox fallback**

If intro regex misses, fetch wikitext:

```
action=parse
page={resolved_title}
prop=wikitext
```

Parse first `{{Infobox ...}}` block; check keys containing `tribe`, `nationality`, `citizenship`, `ethnicity`, `ancestry`, `people` (case-insensitive). Strip wikilinks/templates.

**Step D — Optional Wikidata fallback**

Only when B and C fail:

1. `prop=pageprops&ppprop=wikibase_item` → QID
2. `wbgetentities` on `www.wikidata.org` — claims `P172` (ethnic group), `P27` (country of citizenship; sometimes tribal nation)

Resolve QID labels via `wbgetentities&props=labels`. Low confidence; require label to match tribe dictionary.

**Step E — Optional LLM extraction (Phase 2, not MVP)**

For intros containing "Native American" without a specific nation (e.g. Anne McKeig), optionally call UIC Qwen with intro text only. Guard with `--llm-fallback` flag; default off for MVP.

### Extraction logic

**Primary:** regex over intro plain text using an expanded tribe/nation dictionary derived from known roster values + feasibility probe patterns:

- Nation names: `Navajo`, `Cherokee`, `Ho-Chunk`, `Serrano`, `Cahuilla`, …
- Phrases: `Citizen of the Cherokee Nation`, `member of the ... Tribe`, `... descent`, `... heritage`
- Multi-tribe: join with ` / ` when multiple distinct nations appear (match Mary Kunesh style)

**Normalization:**

- Title-case known nations; preserve official forms (`Ho-Chunk`, `Yup'ik`, `Iñupiat`)
- Strip trailing punctuation, Wikipedia parentheticals
- Max length 120 chars; reject if >3 distinct nations unless intro explicitly lists them

**Do not extract:**

- Generic-only: `Native American`, `Indigenous`, `Alaska Native`, `First Nations` (without specific nation)
- Geographic states, parties, offices
- Non-tribal ethnicities unless explicitly tied to indigenous identity in intro

### Rate limits and politeness

Feasibility probing hit HTTP 429 with rapid sequential requests. Required controls:

| Control | Value |
|---------|-------|
| User-Agent | `CRAWLER_USER_AGENT` from env, or `UIC-PolicyTracker/1.0 (+https://policy.urbanindigenouscollective.org)` |
| Sequential delay | 1.0s between individual page fetches (configurable `--delay`) |
| Batch size | Up to 50 titles per `titles=` pipe query for title resolution only |
| Retry | Exponential backoff on 429/503: 2s, 4s, 8s; max 3 retries |
| Timeout | 20s per request |
| Full batch ETA | ~220 names × 1.2s ≈ 4–5 min (acceptable for manual/weekly job) |

Log `X-RateLimit-*` headers when present. Abort batch if sustained 429 after retries.

### Output record schema (`indigenous_ethnicity_enrichment.json`)

```json
{
  "generated_at": "2026-08-05T15:00:00Z",
  "source": "wikipedia",
  "version": 1,
  "entries": {
    "jamesramos": {
      "roster_name": "James Ramos",
      "wikipedia_title": "James Ramos (politician)",
      "ethnicity": "Serrano/Cahuilla",
      "status": "accepted",
      "method": "intro_regex",
      "confidence": "high",
      "evidence": "James Ramos (born ...) is an American politician and member of the Serrano and Cahuilla tribes.",
      "fetched_at": "2026-08-05T14:58:00Z",
      "reject_reason": null
    }
  }
}
```

Keys use `IndigenousDatabase._normalize_roster_name(name)` for stable lookup.

**Status values:** `accepted`, `rejected`, `disambiguation_unresolved`, `page_missing`, `skipped_override`, `skipped_known`.

### Dry-run report

Write `scripts/reports/indigenous_ethnicity_enrichment_{timestamp}.json` and `.md` with:

- Counts: targets, accepted, rejected, unresolved, skipped
- Per-entry: name, proposed ethnicity, method, evidence snippet, reject reason
- MVP impact estimate: how many Airtable rows would gain tribe labels after backfill

---

## 2. Sidecar vs inline merge strategy

### Recommendation: **dual sidecar, merge at load time**

| File | Owner | Mutability | Survives `refresh()`? |
|------|-------|------------|------------------------|
| `data/indigenous_politicians.json` | Wikipedia scrape | Rebuilt weekly if enabled | N/A |
| `data/indigenous_ethnicity_overrides.json` | Human / parallel agent | Manual edits | Yes |
| `data/indigenous_ethnicity_enrichment.json` | `enrich_indigenous_ethnicity.py` | Script `--apply` | Yes |

**Do not** write enricher output directly into `indigenous_politicians.json`. Weekly `db.refresh()` rebuilds from Wikipedia and would erase inline patches (except `manual_adjustments()`).

### Changes to `indigenous_database.py`

Add constants:

```python
DEFAULT_OVERRIDES_PATH = Path("data/indigenous_ethnicity_overrides.json")
DEFAULT_ENRICHMENT_PATH = Path("data/indigenous_ethnicity_enrichment.json")
```

Add method `_apply_ethnicity_sidecars(records: list[dict]) -> list[dict]`:

1. Load overrides JSON if present (tolerate missing file)
2. Load enrichment JSON if present
3. For each record, compute `key = _normalize_roster_name(name)`
4. Apply ethnicity only when current value is `N/A`:
   - If override exists → use override (even if enricher disagrees)
   - Elif enrichment entry with `status == "accepted"` → use enrichment
   - Else keep `N/A`
5. Never downgrade a known inline ethnicity

Call `_apply_ethnicity_sidecars()` from:

- `load_from_disk()` — after `_dedupe_roster()`
- `build_database()` — after `_dedupe_roster()` and before `save_to_disk()` (so saved cache reflects merged view for debugging, but sidecars remain source of truth for N/A fills)

**Alternative considered — inline merge on `--apply`:** rejected because refresh overwrites and creates merge conflicts with overrides.

### Enricher ↔ overrides interaction

- Enricher **skips** any name present in overrides (log `skipped_override`)
- Enricher **never modifies** overrides file
- If override removes a bad enrichment, add override entry; enricher will not re-propose on next run unless override deleted
- Re-enrichment of a name: delete or downgrade enrichment entry, or add override

---

## 3. MVP scope vs full batch

### MVP (~30 names, 1–2 days)

**Goal:** Restore tribe labels for legislators actively appearing in Airtable pending/live.

**Cohort construction:**

1. Hardcoded spot checks: Sharice Davids, James Ramos, Mary Kunesh, Tyson Running Wolf, Bryce Edgmon, Donald Olson, Deb Haaland, Tom Cole, Markwayne Mullin, Peggy Flanagan, Kevin Killer, Rena Newell, Shannon Pinto
2. Union with roster N/A stubs matched by `get_indigenous_sponsor_entry()` against all sponsor strings in Airtable pending + live
3. Cap at ~30 by frequency (names appearing on most bills first)
4. Exclude names already in overrides sidecar

**Expected yield:** 20–25 accepted extractions (feasibility: ~80% hit rate on resolvable pages; disambiguation failures on bare names like James Ramos).

**Success criteria:**

- James Ramos → `Serrano/Cahuilla`
- Sharice Davids → `Ho-Chunk`
- Mary Kunesh → `Standing Rock Dakota / Native Hawaiian`
- `backfill_indigenous_sponsorship.py` dry-run shows tribe parentheticals restored for MVP bills
- No regressions on known-ethnicity entries (Edgmon, Olson unchanged)

### Full batch (220 names, +2–3 days after MVP)

**Goal:** Close the category-stub gap for the entire roster.

**Approach:**

1. Run enricher with `--all-na` after MVP patterns validated
2. Human review of dry-run report: spot-check 20 random `accepted` + all `rejected` with non-null proposed values
3. `--apply` accepted entries only; leave `disambiguation_unresolved` for manual overrides or title-alias map
4. Maintain `data/indigenous_wikipedia_title_aliases.json` for stubborn disambiguation cases:

   ```json
   { "James Ramos": "James Ramos (politician)", "Mary Kunesh": "Mary Kunesh-Podein" }
   ```

**Expected yield:** ~140–170 accepted (65–75% of 220), ~20 unresolved disambiguation, ~30 thin/generic pages, remainder rejected.

**Not in scope for v1:** Municipal-only stubs with no Wikipedia page, historical figures with minimal bios.

---

## 4. Validation and reject rules

### Skip conditions (never fetch, never write)

| Rule | Rationale |
|------|-----------|
| Merged ethnicity not `N/A` | Don't overwrite list-page or override data |
| Name in `indigenous_ethnicity_overrides.json` | Human source of truth |
| Enrichment entry exists with `status: accepted` and `--refresh` not set | Idempotent cache |

### Auto-reject after fetch

| Rule | Example |
|------|---------|
| Page missing after search | No Wikipedia bio |
| Intro length < 80 chars | Stub page |
| Extracted value is generic-only | `Native American`, `Indigenous`, `Alaska Native` alone |
| Extracted value matches office/party/state | `Democratic`, `California` |
| Confidence `low` from Wikidata-only with no tribe dictionary match | Random citizenship country |
| Proposed ethnicity shorter than 3 chars | Parse artifact |
| Proposed ethnicity differs from override | Should not happen if skip logic correct |

### Accept conditions

| Method | Accept when |
|--------|-------------|
| `intro_regex` | Dictionary match or `member of the X Tribe/Nation` pattern in first 500 chars of intro |
| `infobox` | Tribe-like field matches dictionary |
| `wikidata` | P172 label matches dictionary AND intro mentions indigenous context |
| `llm` (Phase 2) | Model returns specific nation + evidence quote present in intro |

### Human review queue

Dry-run report flags for manual override:

- `disambiguation_unresolved`
- `rejected` with evidence containing partial tribe signal
- `accepted` with `confidence: low`

---

## 5. Integration with refresh job and backfill

### `refresh_indigenous_db.py` / weekly scheduler

**Implemented (post-refresh hook):** After a successful roster refresh (or `--dedupe-only`), Wikipedia enrichment runs automatically when `INDIGENOUS_ETHNICITY_ENRICH_ON_REFRESH=true` (default). LLM fallback is optional via `INDIGENOUS_ETHNICITY_LLM_FALLBACK_ON_REFRESH=false` (default off — slow, uses Qwen).

The hook is wired in:
- `scripts/refresh_indigenous_db.py` — calls `run_post_refresh_enrichment()` after `db.refresh()` / `dedupe_disk_cache()`
- `scheduler.run_indigenous_roster_refresh_job()` — same hook after scheduled refresh, then `reload_if_stale()` on the main app

Manual CLI remains available for ad-hoc runs:

```bash
python scripts/refresh_indigenous_db.py          # refresh + post-refresh enrich (if enabled)
python scripts/enrich_indigenous_ethnicity.py --all-na --apply
python scripts/backfill_indigenous_sponsorship.py --apply
```

Env vars (see `.env.example`):

```
INDIGENOUS_ETHNICITY_ENRICH_ON_REFRESH=true
INDIGENOUS_ETHNICITY_LLM_FALLBACK_ON_REFRESH=false
```

**Phase 2 (future):** Incremental mode — only re-fetch when `fetched_at` older than `INDIGENOUS_ETHNICITY_CACHE_DAYS` or status was `disambiguation_unresolved` and alias map updated.

### `backfill_indigenous_sponsorship.py`

No code changes required if `IndigenousDatabase.ensure_loaded()` applies sidecars before matching.

**Operational sequence after enrichment:**

```bash
# 1. Snapshot Airtable (optional but recommended)
python scripts/pending_snapshot.py backup --output-dir data/backups

# 2. Dry-run backfill
python scripts/backfill_indigenous_sponsorship.py --show 60

# 3. Apply
python scripts/backfill_indigenous_sponsorship.py --apply

# 4. Compare to baseline
python scripts/compare_indigenous_sponsorship.py \
  --baseline data/backups/live-pre-indigenous-sponsor-trim-20260805-093100.json \
  --current data/backups/live-post-enrichment.json
```

Use `--also-sponsors` only if tribe labels should appear in `Sponsors of the Legislation` field (currently optional; indigenous field is primary).

### `bill_processor.py` / runtime

`MainApplication` already calls `ensure_loaded()`. Sidecar merge in `load_from_disk()` automatically benefits new bills without deploy of enricher script to scheduler — only the JSON sidecar files need to ship via git/CD.

---

## 6. Test strategy

### Unit tests (`tests/test_enrich_indigenous_ethnicity.py`)

Mock `requests` responses; no live Wikipedia in CI.

| Test | Assert |
|------|--------|
| Intro regex extracts Serrano/Cahuilla | From fixture based on James Ramos intro |
| Rejects generic "Native American" only | `status: rejected` |
| Disambiguation picks `(politician)` page | OpenSearch fixture |
| Skips known ethnicity | Input roster with Deb Haaland Laguna Pueblo unchanged |
| Skips override entry | Override present → enricher skip |
| Sidecar merge priority | Override beats enrichment beats N/A |
| `_pick_richer` unchanged | List-page twin still wins over enrichment for duplicates |

### Unit tests (`tests/test_indigenous_database.py` additions)

| Test | Assert |
|------|--------|
| `load_from_disk` applies overrides | N/A stub → override ethnicity |
| `load_from_disk` applies enrichment | N/A stub → enrichment ethnicity |
| Known ethnicity not overwritten | List-page value preserved |
| Refresh + sidecar | After `build_database()`, sidecars still apply on reload |

### Integration test (optional, marked `@pytest.mark.network`)

Single live fetch against James Ramos (politician) — skip in CI, run manually pre-release.

### Manual QA checklist

- [ ] MVP dry-run report reviewed
- [ ] `pytest tests/test_indigenous_database.py tests/test_enrich_indigenous_ethnicity.py -q`
- [ ] `backfill_indigenous_sponsorship.py` dry-run on pending+live
- [ ] Spot-check bills for Ramos, Kunesh, Davids in Airtable
- [ ] `compare_indigenous_sponsorship.py` shows no `still_missing` regressions for MVP names
- [ ] Running Wolf still resolves via twin merge (enrichment must not break dedupe)

---

## 7. Rollout plan

### Step 0 — Prerequisites

- [ ] Commit and deploy prior indigenous sponsor fixes via GitHub CD (parallel gap work)
- [ ] Confirm `data/indigenous_ethnicity_overrides.json` exists from parallel work (or create with MVP names)
- [ ] Ship sidecar merge in `indigenous_database.py`

### Step 1 — Implement enricher + sidecar merge (dev)

- [ ] `scripts/enrich_indigenous_ethnicity.py`
- [ ] `indigenous_database.py` sidecar loading
- [ ] Unit tests
- [ ] `.env.example` entries

### Step 2 — MVP dry-run

```bash
python scripts/enrich_indigenous_ethnicity.py --mvp \
  --report scripts/reports/enrichment_mvp_dryrun.json
```

Review report; add manual overrides for unresolved MVP names; add Wikipedia title aliases as needed.

### Step 3 — MVP apply

```bash
python scripts/enrich_indigenous_ethnicity.py --mvp --apply
git add data/indigenous_ethnicity_enrichment.json data/indigenous_ethnicity_overrides.json
# commit when user requests
```

Push to `main` → GitHub Actions CD deploys sidecar files to prod.

### Step 4 — Re-backfill Airtable

```bash
# Snapshot first
python scripts/backfill_indigenous_sponsorship.py --show 60
python scripts/backfill_indigenous_sponsorship.py --apply
python scripts/compare_indigenous_sponsorship.py --baseline ... --current ...
```

Prod helper (read-only pattern):

```bash
docker compose exec scheduler python scripts/backfill_indigenous_sponsorship.py --apply
```

### Step 5 — Full batch (after MVP stable)

```bash
python scripts/enrich_indigenous_ethnicity.py --all-na          # dry-run
python scripts/enrich_indigenous_ethnicity.py --all-na --apply
# commit enrichment sidecar, deploy, re-backfill
```

### Step 6 — Enable incremental enrichment (optional)

Set `INDIGENOUS_ETHNICITY_ENRICH_ENABLED=true` on prod after 2 weeks of stable MVP.

---

## 8. Effort estimate and risks

### Effort

| Phase | Scope | Estimate |
|-------|-------|----------|
| Sidecar merge in `indigenous_database.py` | Load-time merge, tests | 0.5 day |
| `enrich_indigenous_ethnicity.py` MVP | API client, regex, disambiguation, dry-run report | 1–1.5 days |
| MVP rollout | Dry-run review, apply, Airtable backfill, compare | 0.5 day |
| Full 220 batch | Aliases, batch run, review rejected queue | 1.5–2 days |
| Scheduler integration (Phase 2) | Env-gated hook, cache TTL | 0.5 day |
| **Total** | MVP → full production | **3–5 days** |

### Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Wikipedia 429 rate limits | Batch fails mid-run | Throttle 1 req/s, batch title resolution, retry/backoff, resume from enrichment cache |
| Wrong page disambiguation | Incorrect tribe label | OpenSearch scoring + alias map; dry-run review; overrides trump enricher |
| Generic extraction ("Native American") | Misleading labels | Strict reject rules; no auto-apply without dictionary match |
| Weekly refresh erases enrichments | Tribe labels lost | Sidecar architecture; never rely on inline roster patches |
| Overrides vs enricher conflict | Duplicate maintenance | Enricher skips overridden names; document precedence |
| Parallel agent edits same files | Merge conflicts | Overrides = human; enrichment = machine; separate JSON files |
| Airtable backfill churn | Wide record updates | Dry-run first; `--limit` for staged apply; snapshot baselines |
| Twin-name dedupe regression | Running Wolf loses Blackfeet | Enrichment keys on normalized name; tests for twin merge |
| CI/live network dependency | Flaky tests | Mock all API calls in unit tests; one manual network smoke test |

---

## File checklist (implementation)

| File | Action |
|------|--------|
| `scripts/enrich_indigenous_ethnicity.py` | **Create** |
| `indigenous_database.py` | **Modify** — sidecar merge |
| `data/indigenous_ethnicity_enrichment.json` | **Create** — machine output (git-tracked) |
| `data/indigenous_ethnicity_overrides.json` | **May exist** — parallel work |
| `data/indigenous_wikipedia_title_aliases.json` | **Create** — optional disambiguation map |
| `tests/test_enrich_indigenous_ethnicity.py` | **Create** |
| `tests/test_indigenous_database.py` | **Modify** — sidecar tests |
| `.env.example` | **Modify** — enrichment env vars |
| `scheduler.py` | **Modify** — Phase 2 only, env-gated |
| `docs/INDIGENOUS_ETHNICITY_ENRICHMENT_PLAN.md` | This document |

---

## References

- Feasibility assessment: agent transcript `5df6500c-aec0-4d14-9cf6-06e92684fe24` (2026-08-05)
- Roster cache: `data/indigenous_politicians.json` (755 entries, 220 N/A, `built_at=2026-08-05T13:57:57Z`)
- Sponsorship compare baseline: `scripts/reports/indigenous_sponsorship_compare_20260805T140041Z.md`
- Existing refresh: `scripts/refresh_indigenous_db.py`, `INDIGENOUS_DB_REFRESH_ENABLED=false`
- Backfill: `scripts/backfill_indigenous_sponsorship.py`
