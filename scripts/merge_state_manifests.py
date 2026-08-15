#!/usr/bin/env python3
"""Merge per-state manifest files into sources/state_sources.json."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.source_schema import StateManifest, StateSource, StateSourcesFile  # noqa: E402

MANIFESTS_DIR = ROOT / "sources" / "manifests"
OUTPUT_PATH = ROOT / "sources" / "state_sources.json"


def load_manifest(path: Path) -> list[StateSource]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "sources" in data:
        manifest = StateManifest.model_validate(data)
        return manifest.sources
    if isinstance(data, list):
        return [StateSource.model_validate(item) for item in data]
    return [StateSource.model_validate(data)]


def dedupe_sources(sources: list[StateSource]) -> list[StateSource]:
    seen_ids: set[str] = set()
    seen_url_types: set[tuple[str, str]] = set()
    result: list[StateSource] = []
    for source in sources:
        sid = source.source_id
        url = source.primary_url().lower().rstrip("/")
        url_type = (url, source.content_type)
        if sid in seen_ids or (url and url_type in seen_url_types):
            continue
        seen_ids.add(sid)
        if url:
            seen_url_types.add(url_type)
        result.append(source)
    return result


def main():
    if not MANIFESTS_DIR.exists():
        print(f"No manifests directory at {MANIFESTS_DIR}")
        sys.exit(1)

    paths = sorted(MANIFESTS_DIR.glob("*.json"))
    if not paths:
        print(f"No manifest JSON files in {MANIFESTS_DIR}")
        sys.exit(1)

    combined: list[StateSource] = []
    for path in paths:
        try:
            combined.extend(load_manifest(path))
            print(f"  loaded {path.name}")
        except Exception as exc:
            print(f"  ! skipped {path.name}: {exc}")

    combined = dedupe_sources(combined)
    payload = StateSourcesFile(
        generated_from="sources/manifests/*.json",
        note="Set review_needed=false after verifying each crawl target URL",
        sources=combined,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload.model_dump(), f, indent=2)
        f.write("\n")
    print(f"\nWrote {len(combined)} sources to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
