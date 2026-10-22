"""Indexable path list for Next.js sitemap (single snapshot read)."""

from __future__ import annotations

from typing import Any

from discovery.federal_schema import FEDERAL_STATE
from public_api.cache import PublicSnapshot
from public_api.states import is_map_state_code


def is_public_panel_code(code: str) -> bool:
    return is_map_state_code(code) or code == FEDERAL_STATE


def _state_path_segment(code: str) -> str:
    return code if code == FEDERAL_STATE else code


def build_sitemap_payload(snap: PublicSnapshot) -> dict[str, Any]:
    paths: list[str] = ["/"]
    hub_paths: set[str] = set()
    bill_paths: set[str] = set()
    skipped_no_slug = 0
    skipped_not_indexable = 0

    for code, bills in snap.by_state.items():
        if not bills or not is_public_panel_code(code):
            continue
        hub_paths.add(f"/states/{_state_path_segment(code)}")

    for bill in snap.bills:
        slug = str(bill.get("slug") or "").strip()
        if not slug:
            skipped_no_slug += 1
            continue
        state = str(bill.get("state") or "").strip()
        if not is_public_panel_code(state):
            skipped_not_indexable += 1
            continue
        bill_paths.add(
            f"/states/{_state_path_segment(state)}/bills/{slug}",
        )

    paths.extend(sorted(hub_paths))
    paths.extend(sorted(bill_paths))

    return {
        "paths": paths,
        "billCount": len(bill_paths),
        "liveCount": snap.live_count,
        "skippedNoSlug": skipped_no_slug,
        "skippedNotIndexable": skipped_not_indexable,
        "generatedAt": snap.generated_at.isoformat(),
        "cacheAgeSeconds": round(snap.cache_age_seconds, 1),
    }
