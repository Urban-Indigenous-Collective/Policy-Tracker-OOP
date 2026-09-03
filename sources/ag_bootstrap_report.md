# Attorney General Source Bootstrap

Generated: 2026-09-03

State AG press rooms were a systematic blind spot: bootstrap and gap-fill only
probed governor / legislature / SOS paths. The South Dakota MMIP specialist
appointment (atg.sd.gov press release 3147) never appeared on those indexes.

## Summary

- Jurisdictions mapped: 51 (50 states + DC) in `sources/ag_hosts.json`
- Enabled AG sources after probe: 48
- Already covered by an existing DOJ/agency source: MT (`dojmt.gov/news/`), WI (`doj.state.wi.us/news`)
- Recorded `review_needed=true` (HTTP 403 from bootstrap host): KS, MA, NH

## SD one-off (incident)

- Source: `SD — Attorney General press releases`
- URL: https://atg.sd.gov/OurOffice/Media/pressreleases.aspx
- Crawl check 2026-09-03: emitted `pressreleasesdetail.aspx?id=3147`
  (Attorney General Jackley Names Marlys Big Eagle As State’s Missing and Murdered Indigenous Person Specialist)

## Re-run

```bash
python scripts/bootstrap_ag_sources.py --all --dry-run
python scripts/bootstrap_ag_sources.py --all --apply
python scripts/merge_state_manifests.py
```

KS / MA / NH listing URLs are in `sources/ag_hosts.json`. Probe them from prod
(honest crawler UA) and set `review_needed=false` if they return 200.
