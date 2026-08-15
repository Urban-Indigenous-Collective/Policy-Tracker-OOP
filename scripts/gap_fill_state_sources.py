#!/usr/bin/env python3
"""Fill governor / legislature / agency gaps in state MMIP source manifests.

Candidate URLs come from sources/manual_seeds.json plus governor path templates.
Every candidate is HTTP-probed; only URLs that return a real page are written
into sources/manifests/{ST}.json.

Usage:
  python scripts/gap_fill_state_sources.py --states TX CA --dry-run
  python scripts/gap_fill_state_sources.py --states TX CA --apply
  python scripts/gap_fill_state_sources.py --all --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from discovery.source_schema import (  # noqa: E402
    StateManifest,
    StateSource,
    is_blocked_domain,
    load_sources_data,
)

MANIFESTS_DIR = ROOT / "sources" / "manifests"
SEEDS_PATH = ROOT / "sources" / "manual_seeds.json"
REPORT_PATH = ROOT / "sources" / "gap_fill_report.md"

USER_AGENT = "UIC-PolicyTracker/1.0 (+https://urbanindigenouscollective.org)"
# Some state portals reject the crawler UA outright. When that happens we retry
# with a browser UA and pin it on the source so the crawler sends the same thing.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
PROBE_TIMEOUT = 25
MIN_BODY_BYTES = 800

GENERIC_STATE_SEARCH_RE = re.compile(r"^https?://(www\.)?[a-z]{2}\.gov/search", re.I)
MAIN_V3_SEED_RE = re.compile(r"\(Main v3 seed\)", re.I)
MALFORMED_SEARCH_URL_RE = re.compile(r"^(press_release|legislation|other|report|letter)$", re.I)

# Jurisdictions with a single legislative chamber; "both chambers" phrasing is
# wrong for these and the coverage audit treats chambers as N/A.
SINGLE_CHAMBER = {"NE", "DC"}

# Governor listing paths tried when a state's seed entry supplies only a base host.
GOVERNOR_PATH_TEMPLATES: dict[str, tuple[str, ...]] = {
    "governor_news": (
        "/news",
        "/news/press-releases",
        "/newsroom",
        "/media/press-releases",
        "/press-releases",
        "/newsroom/press-releases",
    ),
    "executive_order": (
        "/news/executive-orders",
        "/executive-orders",
        "/orders",
        "/executive-actions",
        "/news/executive-actions",
    ),
    "proclamation": (
        "/news/proclamations",
        "/proclamations",
        "/news/category/proclamation",
    ),
}

ROLE_LABELS: dict[str, str] = {
    "governor_news": "Governor news",
    "executive_order": "Governor executive orders",
    "proclamation": "Governor proclamations",
    "agency_press": "agency press releases",
    "legislature_search": "Legislature bill search",
    "legislature_session": "Bills and session documents",
    "house": "House bill search",
    "senate": "Senate bill search",
}

ROLE_CONTENT_TYPE: dict[str, str] = {
    "governor_news": "press_release",
    "executive_order": "executive_order",
    "proclamation": "proclamation",
    "agency_press": "press_release",
    "legislature_search": "legislation",
    "legislature_session": "legislation",
    "house": "legislation",
    "senate": "legislation",
}


@dataclass
class Candidate:
    state: str
    role: str
    url: str
    method: str = "index"
    name: str = ""
    notes: str = ""
    content_type: str = ""
    search_param: str = "q"
    ssl_verify: bool = True
    ignore_robots: bool = False
    render_js: bool = False
    user_agent: str = ""
    # Probe outcome
    ok: bool = False
    detail: str = ""

    @property
    def probe_url(self) -> str:
        if self.method == "search":
            return self.url.replace("{query}", "MMIP")
        return self.url


@dataclass
class StateResult:
    state: str
    added: list[Candidate] = field(default_factory=list)
    failed: list[Candidate] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)


def load_seeds() -> dict[str, list[dict]]:
    if not SEEDS_PATH.exists():
        return {}
    with open(SEEDS_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_manifest(state: str) -> StateManifest:
    path = MANIFESTS_DIR / f"{state}.json"
    if not path.exists():
        return StateManifest(state=state, sources=[])
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return StateManifest(state=state, sources=load_sources_data(data))


def write_manifest(manifest: StateManifest) -> None:
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = MANIFESTS_DIR / f"{manifest.state}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest.model_dump(), f, indent=2)
        f.write("\n")


def _probe_response(
    candidate: Candidate,
    response: requests.Response,
    url: str,
    user_agent: str,
) -> Candidate:
    if response.status_code >= 400:
        candidate.ok = False
        candidate.detail = f"HTTP {response.status_code}"
        return candidate

    body = response.text or ""
    if len(body) < MIN_BODY_BYTES:
        candidate.ok = False
        candidate.detail = f"body too small ({len(body)} bytes)"
        return candidate

    lowered = body[:4000].lower()
    if "page not found" in lowered or "404 error" in lowered:
        candidate.ok = False
        candidate.detail = "soft 404"
        return candidate

    # Redirect away from the requested path usually means the listing does not exist.
    final = urlparse(response.url)
    wanted = urlparse(url)
    if wanted.path.rstrip("/") and final.path.rstrip("/") in ("", "/"):
        candidate.ok = False
        candidate.detail = f"redirected to root ({response.url})"
        return candidate

    candidate.ok = True
    candidate.user_agent = user_agent
    candidate.detail = f"HTTP {response.status_code}, {len(body)} bytes"
    return candidate


def probe(candidate: Candidate) -> Candidate:
    """GET the candidate URL and decide whether it is a usable listing page."""
    url = candidate.probe_url
    if is_blocked_domain(url):
        candidate.ok = False
        candidate.detail = "blocked domain"
        return candidate

    for user_agent in (USER_AGENT, BROWSER_USER_AGENT):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": user_agent},
                timeout=PROBE_TIMEOUT,
                allow_redirects=True,
                verify=candidate.ssl_verify,
            )
        except requests.exceptions.SSLError as exc:
            candidate.ok = False
            candidate.detail = f"ssl error ({str(exc)[:60]})"
            return candidate
        except Exception as exc:
            candidate.ok = False
            candidate.detail = f"{type(exc).__name__}: {str(exc)[:60]}"
            return candidate

        if response.status_code == 403 and user_agent == USER_AGENT:
            continue

        return _probe_response(candidate, response, url, user_agent)

    candidate.ok = False
    candidate.detail = "HTTP 403"
    return candidate


def build_name(state: str, role: str, explicit: str) -> str:
    if explicit:
        return explicit
    label = ROLE_LABELS.get(role, role.replace("_", " "))
    name = f"{state} — {label}"
    if role in ("legislature_search", "legislature_session") and state not in SINGLE_CHAMBER:
        name = f"{name} (both chambers)"
    return name


def candidates_for_state(state: str, seeds: list[dict]) -> list[Candidate]:
    """Expand seed entries into probe candidates, including governor path templates."""
    candidates: list[Candidate] = []
    for seed in seeds:
        role = seed.get("role", "")
        base = seed.get("base", "")
        if base and role in GOVERNOR_PATH_TEMPLATES:
            for path in GOVERNOR_PATH_TEMPLATES[role]:
                candidates.append(
                    Candidate(
                        state=state,
                        role=role,
                        url=base.rstrip("/") + path,
                        method="index",
                        name=seed.get("name", ""),
                        notes=seed.get("notes", ""),
                        content_type=seed.get("content_type", ""),
                        ssl_verify=seed.get("ssl_verify", True),
                        ignore_robots=seed.get("ignore_robots", False),
                        render_js=seed.get("render_js", False),
                    )
                )
            continue

        url = seed.get("search_url") or seed.get("url") or ""
        if not url:
            continue
        candidates.append(
            Candidate(
                state=state,
                role=role,
                url=url,
                method=seed.get("method", "index"),
                name=seed.get("name", ""),
                notes=seed.get("notes", ""),
                content_type=seed.get("content_type", ""),
                search_param=seed.get("search_param", "q"),
                ssl_verify=seed.get("ssl_verify", True),
                ignore_robots=seed.get("ignore_robots", False),
                render_js=seed.get("render_js", False),
            )
        )
    return candidates


def to_source(candidate: Candidate) -> StateSource:
    content_type = candidate.content_type or ROLE_CONTENT_TYPE.get(candidate.role, "other")
    name = build_name(candidate.state, candidate.role, candidate.name)
    notes = candidate.notes or "Probe-verified during coverage gap fill"
    kwargs: dict = {
        "state": candidate.state,
        "name": name,
        "content_type": content_type,
        "method": candidate.method,
        "review_needed": False,
        "discovered_by": "gap_fill_probe",
        "discovered_on": date.today().isoformat(),
        "notes": notes,
        "confidence": "high",
        "ssl_verify": candidate.ssl_verify,
        "ignore_robots": candidate.ignore_robots,
        "render_js": candidate.render_js,
        "user_agent": candidate.user_agent,
    }
    if candidate.method == "search":
        kwargs["search_url"] = candidate.url
        kwargs["search_param"] = candidate.search_param
    else:
        kwargs["url"] = candidate.url
    return StateSource(**kwargs)


def existing_urls(manifest: StateManifest) -> set[str]:
    return {s.primary_url().lower().rstrip("/") for s in manifest.sources if s.primary_url()}


def existing_roles(manifest: StateManifest) -> set[str]:
    """Roles already satisfied by an enabled source, so we do not add duplicates."""
    roles: set[str] = set()
    for source in manifest.sources:
        if source.review_needed:
            continue
        blob = f"{source.name} {source.notes} {source.primary_url()}".lower()
        if source.content_type == "executive_order":
            roles.add("executive_order")
        if source.content_type == "proclamation":
            roles.add("proclamation")
        if "governor" in blob and source.content_type in ("press_release", "report"):
            roles.add("governor_news")
        if source.content_type == "legislation" and source.method in ("search", "api"):
            roles.add("legislature_search")
    return roles


def gap_fill_state(
    state: str,
    seeds: dict[str, list[dict]],
    do_probe: bool,
) -> tuple[StateResult, StateManifest]:
    manifest = load_manifest(state)
    result = StateResult(state=state)
    seen = existing_urls(manifest)

    candidates = candidates_for_state(state, seeds.get(state, []))
    if not candidates:
        return result, manifest

    if do_probe:
        with ThreadPoolExecutor(max_workers=6) as pool:
            candidates = list(pool.map(probe, candidates))
    else:
        for candidate in candidates:
            candidate.ok = True
            candidate.detail = "probe skipped"

    # Keep at most one winner per role: the first template path that responded.
    claimed: set[str] = set()
    for candidate in candidates:
        if not candidate.ok:
            result.failed.append(candidate)
            continue
        key = candidate.url.replace("{query}", "").lower().rstrip("/")
        if key in seen:
            result.skipped_existing.append(candidate.url)
            continue
        if candidate.role in claimed:
            continue
        claimed.add(candidate.role)
        seen.add(key)
        result.added.append(candidate)
        manifest.sources.append(to_source(candidate))

    return result, manifest


def _is_stub_source(source: StateSource) -> bool:
    url = source.primary_url()
    if source.method == "search" and GENERIC_STATE_SEARCH_RE.match(url):
        return True
    if MAIN_V3_SEED_RE.search(source.name):
        return True
    return False


def _clean_malformed_search_url(source: StateSource) -> bool:
    search_url = (source.search_url or "").strip()
    if not search_url:
        return False
    if source.method == "search":
        return False
    if search_url.startswith("http"):
        return False
    source.search_url = ""
    return True


def normalize_manifests(states: list[str] | None = None) -> int:
    """Rewrite manifests so schema normalization (e.g. blank bad search_url) is persisted."""
    changed = 0
    for path in sorted(MANIFESTS_DIR.glob("*.json")):
        state = path.stem.upper()
        if states and state not in states:
            continue
        before = path.read_text(encoding="utf-8")
        manifest = load_manifest(state)
        for source in manifest.sources:
            _clean_malformed_search_url(source)
        after = json.dumps(manifest.model_dump(), indent=2) + "\n"
        if after != before:
            path.write_text(after, encoding="utf-8")
            changed += 1
    return changed


def downgrade_stubs(states: list[str] | None = None) -> int:
    """Mark generic {st}.gov search and Main v3 homepage seeds for review."""
    normalize_manifests(states)
    changed = 0
    paths = sorted(MANIFESTS_DIR.glob("*.json"))
    for path in paths:
        state = path.stem.upper()
        if states and state not in states:
            continue
        manifest = load_manifest(state)
        touched = False
        for source in manifest.sources:
            if _clean_malformed_search_url(source):
                touched = True
            if _is_stub_source(source) and not source.review_needed:
                source.review_needed = True
                touched = True
        if touched:
            write_manifest(manifest)
            changed += 1
    return changed


def write_report(results: list[StateResult]) -> None:
    lines = [
        "# State Source Gap-Fill Report",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "## Summary",
        "",
        f"- States processed: {len(results)}",
        f"- Sources added: {sum(len(r.added) for r in results)}",
        f"- Candidates rejected by probe: {sum(len(r.failed) for r in results)}",
        "",
        "## Added sources",
        "",
    ]
    for result in sorted(results, key=lambda r: r.state):
        if not result.added:
            continue
        lines.append(f"### {result.state}")
        lines.append("")
        for candidate in result.added:
            lines.append(
                f"- `{candidate.role}` {build_name(candidate.state, candidate.role, candidate.name)}"
            )
            lines.append(f"  - {candidate.url}")
            lines.append(f"  - probe: {candidate.detail}")
        lines.append("")

    failed = [(r.state, c) for r in results for c in r.failed]
    if failed:
        lines.extend(["## Rejected candidates", ""])
        for state, candidate in sorted(failed, key=lambda x: (x[0], x[1].role)):
            lines.append(f"- **{state}** `{candidate.role}` {candidate.url} — {candidate.detail}")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill state source coverage gaps")
    parser.add_argument("--states", nargs="*", help="State codes to process")
    parser.add_argument("--all", action="store_true", help="Process every state in the seeds file")
    parser.add_argument("--apply", action="store_true", help="Write manifest changes")
    parser.add_argument("--dry-run", action="store_true", help="Probe and print without writing")
    parser.add_argument("--no-probe", action="store_true", help="Skip HTTP probing (unsafe)")
    parser.add_argument(
        "--downgrade-stubs",
        action="store_true",
        help="Set review_needed=true on generic {st}.gov search and Main v3 homepage seeds",
    )
    args = parser.parse_args()

    if args.downgrade_stubs:
        states = [s.upper() for s in args.states] if args.states else None
        count = downgrade_stubs(states)
        print(f"Downgraded stub sources in {count} manifest(s)")
        if not args.apply and not args.dry_run and not args.states and not args.all:
            return 0

    seeds = load_seeds()
    if not seeds:
        print(f"No seeds found at {SEEDS_PATH}")
        return 1

    if args.all:
        states = sorted(seeds)
    elif args.states:
        states = [s.upper() for s in args.states]
    else:
        parser.error("pass --states or --all")

    results: list[StateResult] = []
    for state in states:
        result, manifest = gap_fill_state(state, seeds, do_probe=not args.no_probe)
        results.append(result)

        status = "APPLY" if args.apply else "DRY-RUN"
        print(f"\n[{status}] {state}: +{len(result.added)} added, {len(result.failed)} rejected")
        for candidate in result.added:
            print(f"  + {candidate.role:22} {candidate.url}")
        for candidate in result.failed:
            print(f"  - {candidate.role:22} {candidate.url}  ({candidate.detail})")

        if args.apply and result.added:
            write_manifest(manifest)

    write_report(results)
    print(f"\nReport written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
