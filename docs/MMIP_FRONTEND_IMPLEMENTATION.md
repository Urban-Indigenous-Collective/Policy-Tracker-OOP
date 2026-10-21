# MMIP Policy Tracker — Next.js frontend implementation

Living plan for the greenfield public frontend. Agents should read this before starting work and update checkboxes when a phase completes.

## Product goal

- Rebuild the public MMIP Policy Tracker from Figma **Finalized pages**.
- Optimize for **SEO/discoverability** (MMIP, state, and bill-level pages).
- Keep **Flask** as backend (API, webhooks, scheduler, discovery, analyzer).

**Figma:** [MMIP Policy Tracker](https://www.figma.com/design/9wjMrCGEzPefYbCQcBCQim/MMIP-Policy-Tracker?node-id=160-2141)  
**USA map SVG:** [mapsvg.com/maps/usa](https://mapsvg.com/maps/usa) — respect license/attribution.

## Locked stack

| Layer | Choice |
|--------|--------|
| Frontend | Next.js (App Router), React, TypeScript |
| Styling | Tailwind CSS |
| Client data | TanStack Query |
| SEO routes | SSG/ISR + per-route metadata |
| Backend | Flask JSON API (read-only v1 first) |
| Hosting | Docker monolith: nginx → Next + Flask (GitHub CD) |

## Locked product rules

### Public data gate

- **Published policies** = rows on Airtable **Main v3** (`AIRTABLE_TABLE`, default `"Main v3"`).
- Pending / Rejected never appear on the public site or sitemap.
- Optional strict filter: `Review Status = "Live"` (exclude transient `"Send Back to Pending"`).
- Default bulk reads match existing tooling: `AirtableClient.all_live_records()`.

### URLs

```text
/                              Map-first home (Figma P0)
/states/{code}                 State view — bills for state (Figma P1)
/states/{code}/bills/{slug}    Bill analysis detail (Figma P2)
/policies                      List view — **last** (Figma P3)
```

- Slugs must be **stable** (bill number + session and/or Airtable record id suffix).
- Every bill shown in the state slide-out gets a **canonical indexable URL**.

### v1 screen priority

1. **P0** — Map page (`/`)
2. **P1** — State + bills panel (`/states/[code]`)
3. **P2** — Bill analysis (`/states/[code]/bills/[slug]`)
4. **P3** — Full list view (`/policies`) — defer

## Architecture

```text
Browser → nginx (public port / tunnel)
            ├─ /          → Next.js (frontend service)
            ├─ /states/*  → Next.js
            └─ /api/*     → Flask (web service)

Flask ← Airtable Main v3, existing jobs unchanged
```

## Implementation phases

### Phase 0 — Repo & infra scaffold

- [x] `frontend/` Next app (TS, Tailwind, ESLint)
- [x] Dev: Next proxies `/api` → local Flask
- [x] `docker-compose`: `frontend` + `web` + `nginx` sketch (prod-shaped)
- [x] Env documented (`.env.example` entries for `NEXT_PUBLIC_*`, API URL)
- [x] CI: build Next artifact (wire deploy in later phase)

**Exit criteria:** `npm run dev` serves a placeholder page; Flask `/health-check` reachable via proxy; compose files validate.

**Completed 2026-10-21:** Next 16 app in `frontend/`; rewrites via `FLASK_DEV_URL`; Docker profile `frontend` (`nginx` on `${PUBLIC_HOST_PORT:-8080}`, `frontend`, `web`); `.github/workflows/frontend-ci.yml`; root `.dockerignore`. Production tunnel still targets Flask-only until Phase 5.

### Phase 1 — Design system & app shell

- [x] Figma Finalized pages → tokens, typography, layout shell
- [x] Header/footer/nav, responsive breakpoints
- [x] USA map SVG integrated (accessible interaction layer stub)
- [x] **Full Tailwind token layer** — `@theme` colors/spacing/type + `uic-*` patterns; JS mirror for SVG ([frontend/docs/design-tokens.md](../frontend/docs/design-tokens.md))

**Exit criteria:** Static shell matches primary Figma frame structure (no real data yet); **components use design tokens only** (no ad hoc hex / Figma px in TSX).

**Completed 2026-10-21:** Map home (`160:2142`) — `lib/design/tokens.css` + `tokens.ts`, `SiteNavigation`, `MapIntro`, `UsaMap`, `MapLegend`, filter row; dev-only Flask health banner. Figma node map: [frontend/docs/figma-nodes.md](../frontend/docs/figma-nodes.md).

**Before Phase 2:** Token foundation is required — new API-driven UI must not introduce parallel color/spacing constants.

### Phase 2 — Flask public read API

- [ ] `GET /api/v1/states` (aggregates for map)
- [ ] `GET /api/v1/states/{code}/bills`
- [ ] `GET /api/v1/bills/{id}` or slug resolver
- [ ] Same Main v3 gate as above; JSON shapes documented

**Exit criteria:** Next can fetch real policy data in dev; tests or smoke script for endpoints.

### Phase 3 — Core routes (Figma P0–P2)

- [ ] `/` map + TanStack Query
- [ ] `/states/[code]` slide-out / bill list
- [ ] `/states/[code]/bills/[slug]` analysis page
- [ ] SSR/ISR + metadata on state and bill routes

**Exit criteria:** End-to-end click map → state → bill with live Airtable data.

### Phase 4 — SEO hardening

- [ ] `sitemap.xml`, `robots.txt`
- [ ] JSON-LD where appropriate
- [ ] Canonical URLs; hub copy on `/` and MMIP-oriented titles
- [ ] Performance pass on LCP for public pages

**Exit criteria:** All indexable Main v3 Live rows appear in sitemap; bill pages have unique titles/descriptions.

### Phase 5 — Production cutover

- [ ] GitHub CD builds/deploys nginx + Next + Flask
- [ ] Cloudflare tunnel → nginx
- [ ] Redirect legacy Flask template routes when ready
- [ ] `/policies` list view (P3) if not done earlier

**Exit criteria:** https://policy.urbanindigenouscollective.org serves new frontend; old UI retired or redirected.

---

## Agent workflow (phase chaining)

When asked to implement frontend work:

1. Read this file and find the **first phase with unchecked exit criteria**.
2. If the user did not specify a phase, work on that phase only.
3. **Before coding a phase:** produce a short **phase plan** (tasks, files, risks, test plan) in chat or Plan mode.
4. **After completing a phase:** mark checkboxes in this file, commit if user requested commits, then **stop and prompt the user** (or next agent turn): *"Phase N complete. Create plan for Phase N+1?"*
5. Do not skip phases without explicit user approval.
6. Production deploys: GitHub CD only (see `.cursor/rules/github-cd-deploy.mdc`).

## Phase 0 detailed plan

Implemented: placeholder at `/`, `ApiHealthSmoke` client check for proxied `/health-check`, [frontend/README.md](../frontend/README.md), [deploy/nginx/default.conf](../deploy/nginx/default.conf). Local dev: `cd frontend && npm run dev` with Flask on `:8000`. Optional stack: `docker compose --profile frontend up --build`.

**Handoff:** Phase 0 complete. Plan Phase 1 (Figma shell + design tokens + map frame).

**Phase 1 handoff:** Plan Phase 2 (Flask `/api/v1` read API for map stats and state lists).
