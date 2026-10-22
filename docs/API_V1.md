# Public read API (v1)

Flask serves JSON under `/api/v1/*`. Next.js dev rewrites `/api/*` to Flask (`FLASK_DEV_URL`); nginx proxies `/api/` to the `web` service in Docker.

## Data gate

- Source: Airtable **Main v3** (`AIRTABLE_TABLE`, default `Main v3`).
- Public rows: `Review Status = "Live"` when `PUBLIC_API_REQUIRE_LIVE=1` (default).
- Main v3 rows with **empty** `Review Status` are public by default (pre-backfill data). Set `PUBLIC_API_STRICT_REVIEW_STATUS=1` to require explicit `Live` only.
- `GET /api/v1/health` includes `mainV3Count` (all Main v3 rows) and `liveCount` (after gate).
- Pending table and non-Live rows are never exposed.

## Caching (Airtable throttle)

All v1 handlers read an **in-memory snapshot** refreshed at most once per `PUBLIC_API_CACHE_TTL_SECONDS` (default **300**). Bill detail and state lists are served from the snapshot, not per-request Airtable calls.

| Variable | Default | Purpose |
|----------|---------|---------|
| `PUBLIC_API_CACHE_TTL_SECONDS` | `300` | Snapshot TTL |
| `PUBLIC_API_STALE_ON_ERROR` | `1` | Serve last good snapshot if refresh fails |
| `PUBLIC_API_REQUIRE_LIVE` | `1` | Require Live review status |

## Map legend category (per state)

Applied to Live bills grouped by normalized state code (2-letter US/territory). **National** bills count in summary and `/states/National/bills` but do **not** appear in `states` (no SVG region).

Map-key uses **every Live Main v3 row** grouped by `State` (legislation, executive orders, DOJ/USAO initiatives, empty `Bill Number`, etc.). Same gate as hero `summary`.

Per-bill input is Main v3 **`Status`** only (`Passed` / `Pending` / `Failed`). `Progression` is metadata for display, not map-key.

| API `category` | Rule |
|----------------|------|
| `passed` | ≥1 `Status=Passed`, no `Pending` |
| `passedAdditional` | ≥1 Passed and ≥1 Pending |
| `pending` | No Passed ever, ≥1 Pending, not `failedAdditional` |
| `failed` | No Passed, no Pending, ≥1 Failed |
| `failedAdditional` | No Passed, ≥1 Pending, every non-Pending bill is Failed |

Unlisted states (no row in `states` after the legislation filter): frontend **neutral gray** (`#8a8a8a`). Listed `failed` uses Figma dark fill (`#212121`).

## Endpoints

### `GET /api/v1/states`

Map home payload.

```json
{
  "summary": { "passed": 153, "pending": 63, "rejected": 23 },
  "states": {
    "WA": {
      "code": "WA",
      "name": "Washington",
      "category": "passed",
      "billCount": 4
    }
  },
  "policyDataAsOf": "2026-10-21T06:00:00+00:00",
  "generatedAt": "2026-10-21T19:00:00+00:00",
  "cacheAgeSeconds": 12.4
}
```

### `GET /api/v1/states/{code}/bills`

`code`: `WA`, `National`, etc. Valid US map codes (e.g. `OH`) return `200` with `"bills": []` when there are no Live bills. `404` for unknown jurisdictions (e.g. `ZZ`) or non-map codes with no data.

```json
{
  "state": "WA",
  "bills": [ { "id": "rec…", "slug": "…", "name": "…", "status": "Passed", … } ],
  "generatedAt": "…",
  "cacheAgeSeconds": 12.4
}
```

### `GET /api/v1/bills/{airtable_record_id}`

Full public bill DTO (includes `uicPros`, `uicCons`). 404 if id not in Live snapshot.

### `GET /api/v1/health`

```json
{ "ok": true, "liveCount": 240, "cacheAgeSeconds": 1.2, "generatedAt": "…" }
```

## Errors

```json
{ "error": "not_found", "message": "…" }
```

| HTTP | `error` |
|------|---------|
| 404 | `not_found` |
| 503 | `upstream_unavailable` |

## Smoke

```bash
# Flask on :8000 with Airtable env set
python scripts/smoke_public_api.py
```
