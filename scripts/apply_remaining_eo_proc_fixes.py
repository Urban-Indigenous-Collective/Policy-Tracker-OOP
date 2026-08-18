#!/usr/bin/env python3
"""Apply validated EO/proc manifest fixes for the remaining 7 gap jurisdictions."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = ROOT / "sources" / "manifests"
TODAY = date.today().isoformat()
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

FIXES: dict[str, dict] = {
    # --- MA EO: prod Playwright validated ---
    "ma-ma-governor-healey-executive-orders": {
        "review_needed": False,
        "render_js": True,
        "ignore_robots": True,
        "user_agent": BROWSER_UA,
        "notes": "Playwright render_js; 54 EO links validated prod Docker 2026-08-03.",
        "confidence": "high",
    },
    # --- NH EO: SOS index (not governor SPA) ---
    "nh-nh-sos-executive-orders": {
        "review_needed": False,
        "ignore_robots": True,
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "notes": "SOS HTML table with direct PDF links (ayotte-YYYY-NN.pdf, sununu-YYYY-NN.pdf). Short Mozilla UA required. 373 EO PDF links validated prod Docker 2026-08-03.",
        "confidence": "high",
    },
    "wy-wy-governor-executive-order": {
        "url": "https://governor.wyo.gov/state-government/executive-orders",
        "review_needed": False,
        "render_js": True,
        "ignore_robots": True,
        "user_agent": BROWSER_UA,
        "allowed_extra_domains": ["drive.google.com"],
        "notes": "Playwright render_js; 60 Google Drive EO links at /state-government/executive-orders (not /news/ path). Validated prod Docker 2026-08-03.",
        "confidence": "high",
    },
}

WAF_QUARANTINE_NOTES = {
    "ks-ks-governor-executive-orders-waf": (
        "Real KS EO index URL but Akamai bot wall blocks Playwright from prod Docker (empty_response). 2026-08-03."
    ),
    "nh-nh-governor-news-and-media-waf": (
        "NH EO archive URL confirmed but Akamai bot wall blocks Playwright from prod Docker. 2026-08-03."
    ),
    "nh-nh-governor-site-proclamation-gap-waf": (
        "HONEST GAP: Drupal SPA shell returns 200 but 0 extractable proc links; render_js hits Akamai bot wall from prod. No SOS proclamation archive (404). 2026-08-03."
    ),
    "ny-ny-governor-executive-orders": (
        "Official NY EO index behind Cloudflare challenge; render_js cannot pass from prod datacenter IP. 2026-08-03."
    ),
    "ny-ny-governor-proclamations": (
        "Official NY proclamations index behind Cloudflare challenge; render_js cannot pass from prod datacenter IP. 2026-08-03."
    ),
    "pa-pa-governor-executive-order": (
        "ACCESS-BLOCKED: Coveo JS index returns 0 EO links in Playwright; pacode table lists EOs but has no href links; PDFs exist at /content/dam/.../eo/{YYYY-NN}.pdf but no crawlable HTML index. 2026-08-03."
    ),
}

HONEST_GAP_NOTES = {
    "ma-ma-governor-proclamations-mass-gov": (
        "HONEST GAP: proclamations page 404 (Not found | Mass.gov). No public archive found. 2026-08-03."
    ),
    "ky-ky-governor-home-eo-archive-gap": (
        "HONEST GAP: no central EO archive; SharePoint/newsroom paths soft-404. Re-confirmed 2026-08-03."
    ),
    "ky-ky-governor-proclamation-request-gap": (
        "HONEST GAP: proclamation request form only, not an archive. Re-confirmed 2026-08-03."
    ),
    "wy-wy-governor-proclamation": (
        "HONEST GAP: governor.wyo.gov proc paths are SPA shells with 0 extractable docs. /state-government/proclamations 404. Re-confirmed 2026-08-03."
    ),
    "ks-ks-governor-newsroom-proclamation-gap-waf": (
        "HONEST GAP: no verified public proclamation archive. 2026-08-03."
    ),
    "pa-pa-governor-proclamation": (
        "HONEST GAP: no dedicated proclamation archive post-redesign. 2026-08-03."
    ),
}


def _merge_note(existing: str, note: str) -> str:
    existing = (existing or "").strip()
    if note in existing:
        return existing
    return f"{existing} | {note}".strip(" |") if existing else note


def apply_fixes() -> list[str]:
    changes: list[str] = []
    for path in sorted(MANIFESTS.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        sources = raw.get("sources", raw)
        if not isinstance(sources, list):
            continue
        file_changed = False
        for src in sources:
            sid = src.get("source_id", "")
            if sid in FIXES:
                src.update(deepcopy(FIXES[sid]))
                src["discovered_on"] = TODAY
                changes.append(f"FIX {sid}")
                file_changed = True
            elif sid in WAF_QUARANTINE_NOTES:
                src["review_needed"] = True
                src["notes"] = _merge_note(src.get("notes", ""), WAF_QUARANTINE_NOTES[sid])
                changes.append(f"WAF {sid}")
                file_changed = True
            elif sid in HONEST_GAP_NOTES:
                src["review_needed"] = True
                src["notes"] = _merge_note(src.get("notes", ""), HONEST_GAP_NOTES[sid])
                changes.append(f"GAP {sid}")
                file_changed = True
        if file_changed:
            path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return changes


if __name__ == "__main__":
    applied = apply_fixes()
    print(f"Applied {len(applied)} manifest updates")
    for line in applied:
        print(f"  {line}")
