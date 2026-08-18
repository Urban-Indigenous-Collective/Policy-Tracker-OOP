# State Source Bootstrap Report

Generated: 2026-08-01

## Summary

- States processed: 4
- Total proposed sources: 17
- States with zero sources: 0

## Per-state counts

| State | Sources |
|-------|---------|
| NC | 8 |
| ND | 2 |
| NM | 3 |
| WA | 4 |

## Low-confidence / search-only sources

- **NC** NC — nc.gov site search (q) (search) — https://www.nc.gov/search?q={query}
- **NC** NC — ncadmin.nc.gov (Main v3 seed) (index) — https://ncadmin.nc.gov/
- **ND** ND — governor.nd.gov (Main v3 seed) (index) — https://governor.nd.gov/
- **ND** ND — nd.gov site search (q) (search) — https://www.nd.gov/search?q={query}
- **NM** NM — governor.state.nm.us (Main v3 seed) (index) — https://governor.state.nm.us/
- **NM** NM — nmlegis.gov (Main v3 seed) (index) — https://nmlegis.gov/
- **WA** WA — app.leg.wa.gov (Main v3 seed) (index) — https://app.leg.wa.gov/
- **WA** WA — lawfilesext.leg.wa.gov (Main v3 seed) (index) — https://lawfilesext.leg.wa.gov/
- **WA** WA — wa.gov site search (q) (search) — https://www.wa.gov/search?q={query}

## Likely LegiScan overlap (deprioritize)

- **WA** WA — app.leg.wa.gov (Main v3 seed) — https://app.leg.wa.gov/
- **WA** WA — lawfilesext.leg.wa.gov (Main v3 seed) — https://lawfilesext.leg.wa.gov/

## Next steps

1. Review each source URL in `sources/manifests/*.json`
2. Replace seed/index URLs with real listing pages where needed
3. Set `review_needed: false` on approved rows
4. Run `python scripts/merge_state_manifests.py`
5. Run `python scripts/validate_state_sources.py --enabled-only`
