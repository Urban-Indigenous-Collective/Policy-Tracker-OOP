# Phase 5 production cutover — deferred

**Status (2026-10-22):** The MMIP Next.js frontend is **not production-ready** for nginx/Cloudflare cutover. **Wait on the Phase 5 plan** until map filters, drawer polish, and remaining P0/P1 UX are signed off.

## Do not yet

- Point Cloudflare tunnel at nginx + Next as the canonical public entry
- Retire or redirect legacy Flask template routes
- Treat “deployed to prod host” as “new UI is live for users”

## Before cutover (Phase 5 checklist preview)

- [ ] Map policy-type toggles operational (national / state / DOJ layers)
- [ ] Drawer and map QA on long state names, pills, search, empty states
- [ ] SEO smoke (`scripts/smoke_sitemap.py`) green against prod API
- [ ] Lighthouse baseline documented; no regressions on `/` and bill pages
- [ ] GitHub CD path verified: nginx → Next + Flask on `100.71.124.8`
- [ ] Explicit user approval to execute cutover

## Reference

Full phase list: [MMIP_FRONTEND_IMPLEMENTATION.md](./MMIP_FRONTEND_IMPLEMENTATION.md) — Phase 5 section remains unchecked until cutover is approved.
