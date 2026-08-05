#!/usr/bin/env python3
"""Wikipedia-based tribal affiliation enrichment for indigenous roster N/A stubs.

Dry-run by default. Pass ``--apply`` to write ``data/indigenous_ethnicity_enrichment.json``.

Usage:
  python scripts/enrich_indigenous_ethnicity.py --mvp
  python scripts/enrich_indigenous_ethnicity.py --all-na
  python scripts/enrich_indigenous_ethnicity.py --all-na --apply
  python scripts/enrich_indigenous_ethnicity.py --names "James Ramos" "Mary Kunesh"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from indigenous_database import (
    DEFAULT_DB_PATH,
    DEFAULT_ENRICHMENT_PATH,
    DEFAULT_OVERRIDES_PATH,
    IndigenousDatabase,
)
from sponsor_utils import split_sponsors

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
DEFAULT_USER_AGENT = "UIC-PolicyTracker/1.0 (+https://policy.urbanindigenouscollective.org)"
DEFAULT_ALIASES_PATH = Path("data/indigenous_wikipedia_title_aliases.json")

MVP_SPOT_CHECKS = (
    "Sharice Davids",
    "James Ramos",
    "Mary Kunesh",
    "Tyson Running Wolf",
    "Bryce Edgmon",
    "Donald Olson",
    "Deb Haaland",
    "Tom Cole",
    "Markwayne Mullin",
    "Peggy Flanagan",
    "Kevin Killer",
    "Rena Newell",
    "Shannon Pinto",
)

GENERIC_ETHNICITY = frozenset(
    {
        "native american",
        "indigenous",
        "alaska native",
        "first nations",
        "american indian",
        "indigenous american",
        "native",
    }
)

GENERIC_STANDALONE = GENERIC_ETHNICITY | frozenset(
    {
        "tribe",
        "nation",
        "people",
        "band",
    }
)

SENTENCE_MARKERS = re.compile(
    r"\b(is|was|were|are|who|served|member|employee|attorney|chief|president|representative|delegate)\b",
    re.I,
)

OFFICE_PARTY_REJECT = re.compile(
    r"\b(democratic|republican|independent|california|alaska|montana|"
    r"representative|senator|governor|politician)\b",
    re.I,
)

MEMBER_OF_PATTERN = re.compile(
    r"(?:member|citizen)\s+of\s+(?:the\s+)?(.+?)\s+(?:tribes?|nations?|bands?|peoples?)\b",
    re.I,
)
MULTI_TRIBE_AND = re.compile(
    r"(?:member|citizen)\s+of\s+(?:the\s+)?"
    r"([\w\-'\.]+(?:\s+[\w\-'\.]+)?)\s+and\s+([\w\-'\.]+(?:\s+[\w\-'\.]+)?)\s+(?:tribes?|nations?|bands?)\b",
    re.I,
)
DESCENT_PATTERN = re.compile(
    r"\b([\w\s\-'\.]{3,40}?)\s+(?:descent|heritage|ancestry)\b",
    re.I,
)
TRIBE_OF_PATTERN = re.compile(
    r"([\w\s\-'\.]+?)\s+(?:Tribe|Nation|Band|Pueblo|People)(?:\s+of\s+[\w\s]+)?",
    re.I,
)

DISAMBIG_HINTS = re.compile(
    r"\b(politician|representative|senator|governor|judge|activist)\b|"
    r"\b(Alaska|Montana|California|Minnesota|Kansas|Oklahoma|New Mexico|"
    r"Washington|South Dakota|North Dakota|Arizona|Hawaii|Wisconsin)\b",
    re.I,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _clean_tribe_label(label: str) -> str:
    label = re.sub(r"\[\d+\]", "", label).strip()
    label = re.sub(r"\s+", " ", label)
    label = label.strip(".,; ")
    if len(label) > 120:
        label = label[:120].rsplit(" ", 1)[0]
    return label


def build_tribe_dictionary(roster: list[dict]) -> set[str]:
    """Build tribe/nation dictionary from known roster ethnicities."""
    tribes: set[str] = set()
    split_re = re.compile(r"[,/;&]| and | \+ ")
    for record in roster:
        ethnicity = (record.get("ethnicity") or "").strip()
        if not ethnicity or ethnicity == "N/A":
            continue
        for part in split_re.split(ethnicity):
            part = _clean_tribe_label(part)
            if len(part) >= 3 and part.lower() not in GENERIC_ETHNICITY:
                tribes.add(part)
    extra = (
        "Serrano",
        "Cahuilla",
        "Ho-Chunk",
        "Standing Rock Dakota",
        "Blackfeet Nation",
        "Oglala Lakota",
        "Oglala Sioux",
        "Laguna Pueblo",
        "Cherokee Nation",
        "Navajo",
        "Seminole Nation of Oklahoma",
        "Passamaquoddy",
        "Sandia",
        "Isleta Pueblo",
        "Menominee",
        "Lumbee",
        "Muscogee Creek Nation",
        "Citizen of the Cherokee Nation",
        "Yup'ik",
        "Iñupiat",
        "Inupiaq",
        "Aleut",
        "Tlingit",
        "Haida",
        "Tsimshian",
        "Dena'ina",
        "Gwich'in",
        "Deg Hit'an",
        "Koyukon",
    )
    tribes.update(extra)
    return tribes


class WikipediaEnrichClient:
    def __init__(
        self,
        user_agent: str | None = None,
        delay: float = 1.0,
        timeout: float = 20.0,
        session: requests.Session | None = None,
    ):
        self.user_agent = user_agent or os.getenv("CRAWLER_USER_AGENT") or DEFAULT_USER_AGENT
        self.delay = delay
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(4):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                self._last_request = time.monotonic()
                for header in ("X-RateLimit-Limit", "X-RateLimit-Remaining"):
                    if header in resp.headers:
                        logger.debug("%s: %s", header, resp.headers[header])
                if resp.status_code in (429, 503):
                    wait = 2 ** attempt
                    logger.warning("HTTP %s; backing off %ss", resp.status_code, wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == 3:
                    raise
                wait = 2 ** attempt
                logger.warning("Request failed (%s); retry in %ss", exc, wait)
                time.sleep(wait)
        raise RuntimeError("unreachable")

    def resolve_title(
        self,
        roster_name: str,
        aliases: dict[str, str],
    ) -> tuple[str | None, str]:
        if roster_name in aliases:
            return aliases[roster_name], "alias"

        params = {
            "action": "query",
            "format": "json",
            "titles": roster_name,
            "redirects": 1,
        }
        data = self._request(WIKI_API, params)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            if int(page.get("pageid", -1)) < 0:
                break
            title = page.get("title", "")
            if "(disambiguation)" in title.lower():
                break
            return title, "direct"

        params = {
            "action": "opensearch",
            "format": "json",
            "search": roster_name,
            "limit": 5,
            "namespace": 0,
        }
        data = self._request(WIKI_API, params)
        if len(data) < 2 or not data[1]:
            return None, "page_missing"

        roster_norm = IndigenousDatabase._normalize_roster_name(roster_name)
        best_title: str | None = None
        best_score = 0
        for title in data[1]:
            if "(disambiguation)" in title.lower():
                continue
            score = 0
            if DISAMBIG_HINTS.search(title):
                score += 3
            title_norm = IndigenousDatabase._normalize_roster_name(title.split("(")[0])
            if roster_norm == title_norm or roster_norm in title_norm:
                score += 4
            if score > best_score:
                best_score = score
                best_title = title

        if best_score < 3:
            return None, "disambiguation_unresolved"
        return best_title, "opensearch"

    def fetch_intro(self, title: str) -> str:
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
        }
        data = self._request(WIKI_API, params)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            return (page.get("extract") or "").strip()
        return ""

    def fetch_infobox_fields(self, title: str) -> dict[str, str]:
        params = {
            "action": "parse",
            "format": "json",
            "page": title,
            "prop": "wikitext",
        }
        data = self._request(WIKI_API, params)
        wikitext_raw = (data.get("parse") or {}).get("wikitext") or ""
        if isinstance(wikitext_raw, dict):
            wikitext = wikitext_raw.get("*") or ""
        else:
            wikitext = str(wikitext_raw)
        if not wikitext:
            return {}
        match = re.search(r"\{\{Infobox[^}]*?(?:\{\{[^}]*\}\}[^}]*)*\}\}", wikitext, re.I | re.S)
        if not match:
            return {}
        block = match.group(0)
        fields: dict[str, str] = {}
        for key, val in re.findall(r"\|\s*([\w\s]+?)\s*=\s*([^\n|]+)", block):
            key_clean = key.strip().lower()
            if any(k in key_clean for k in ("tribe", "nationality", "citizenship", "ethnicity", "ancestry", "people")):
                val_clean = re.sub(r"\[\[([^|\]]+\|)?([^\]]+)\]\]", r"\2", val)
                val_clean = re.sub(r"\{\{[^}]+\}\}", "", val_clean).strip()
                fields[key_clean] = val_clean
        return fields

    def fetch_wikidata_ethnicity(self, title: str) -> str | None:
        params = {
            "action": "query",
            "format": "json",
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "titles": title,
            "redirects": 1,
        }
        data = self._request(WIKI_API, params)
        qid = None
        for page in data.get("query", {}).get("pages", {}).values():
            qid = (page.get("pageprops") or {}).get("wikibase_item")
        if not qid:
            return None

        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": qid,
            "props": "claims",
        }
        entity_data = self._request(WIKIDATA_API, params)
        entity = (entity_data.get("entities") or {}).get(qid) or {}
        claims = entity.get("claims") or {}
        for prop in ("P172", "P27"):
            for claim in claims.get(prop) or []:
                try:
                    val_id = claim["mainsnak"]["datavalue"]["value"]["id"]
                except (KeyError, TypeError):
                    continue
                label_params = {
                    "action": "wbgetentities",
                    "format": "json",
                    "ids": val_id,
                    "props": "labels",
                    "languages": "en",
                }
                label_data = self._request(WIKIDATA_API, label_params)
                label = (
                    (label_data.get("entities") or {})
                    .get(val_id, {})
                    .get("labels", {})
                    .get("en", {})
                    .get("value")
                )
                if label:
                    return label
        return None


def _match_dictionary(text: str, tribes: set[str]) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    for tribe in sorted(tribes, key=len, reverse=True):
        if tribe.lower() in GENERIC_STANDALONE:
            continue
        pattern = re.compile(r"\b" + re.escape(tribe.lower()) + r"\b")
        if pattern.search(lowered) and tribe not in found:
            found.append(tribe)
    return found


def _split_tribe_phrase(phrase: str) -> list[str]:
    phrase = _clean_tribe_label(phrase)
    phrase = re.sub(r"^the\s+", "", phrase, flags=re.I)
    if not phrase:
        return []
    if re.search(r"\band\b", phrase, re.I):
        parts = re.split(r"\s+and\s+", phrase, flags=re.I)
        cleaned = []
        for p in parts:
            p = _clean_tribe_label(re.sub(r"^the\s+", "", p.strip(), flags=re.I))
            if p:
                cleaned.append(p)
        return cleaned
    return [phrase]


def _is_valid_tribe_candidate(candidate: str, tribes: set[str]) -> bool:
    candidate = _clean_tribe_label(candidate)
    if len(candidate) < 3 or candidate.lower() in GENERIC_ETHNICITY:
        return False
    if OFFICE_PARTY_REJECT.search(candidate):
        return False
    lowered = candidate.lower()
    if any(t.lower() == lowered or t.lower() in lowered or lowered in t.lower() for t in tribes):
        return True
    return bool(re.search(r"\b(tribe|nation|band|pueblo|people|sioux|cree|ojibwe|iñupiat|inupiat|yup'ik)\b", candidate, re.I))


def _extract_from_patterns(intro: str, tribes: set[str]) -> list[str]:
    found: list[str] = []
    snippet = intro[:500]

    for tribe in _match_dictionary(snippet, tribes):
        if tribe not in found:
            found.append(tribe)

    for match in MULTI_TRIBE_AND.finditer(snippet):
        for idx in (1, 2):
            part = _clean_tribe_label(match.group(idx))
            if _is_valid_tribe_candidate(part, tribes) and part not in found:
                found.append(part)

    for match in MEMBER_OF_PATTERN.finditer(snippet):
        for part in _split_tribe_phrase(match.group(1)):
            if _is_valid_tribe_candidate(part, tribes) and part not in found:
                found.append(part)

    for match in DESCENT_PATTERN.finditer(snippet):
        candidate = _clean_tribe_label(match.group(1))
        if _is_valid_tribe_candidate(candidate, tribes) and candidate not in found:
            found.append(candidate)

    for match in TRIBE_OF_PATTERN.finditer(snippet):
        candidate = _clean_tribe_label(match.group(1))
        if _is_valid_tribe_candidate(candidate, tribes) and candidate not in found:
            found.append(candidate)

    return found


def _join_ethnicities(nations: list[str]) -> str:
    if not nations:
        return ""
    unique = []
    for nation in nations:
        if nation not in unique:
            unique.append(nation)
    unique.sort(key=str.lower)
    if len(unique) > 3:
        return " / ".join(unique[:3])
    return " / ".join(unique)


def _clean_ethnicity_segments(ethnicity: str) -> str:
    segments = [s.strip() for s in ethnicity.split(" / ") if s.strip()]
    kept: list[str] = []
    for segment in segments:
        if len(segment) < 3 or len(segment) > 45:
            continue
        if segment.lower() in GENERIC_STANDALONE:
            continue
        if SENTENCE_MARKERS.search(segment):
            continue
        if re.search(r"\d", segment):
            continue
        if re.search(r"\bon the\b|\bnative american\b|\bdutch\b|\battorney\b", segment, re.I):
            continue
        if not re.match(r"[A-Z0-9\"']", segment):
            continue
        if segment not in kept:
            kept.append(segment)
    return " / ".join(kept[:3])


def _validate_proposed(ethnicity: str, intro: str) -> str | None:
    cleaned = _clean_ethnicity_segments(ethnicity)
    if not cleaned:
        return "generic_only"
    if len(cleaned) < 3:
        return "too_short"
    segments = [s.strip() for s in cleaned.split(" / ")]
    if all(s.lower() in GENERIC_STANDALONE for s in segments):
        return "generic_only"
    if OFFICE_PARTY_REJECT.search(cleaned):
        return "office_or_party"
    if len(intro) < 80:
        return "intro_too_short"
    return None


def extract_ethnicity(
    intro: str,
    infobox: dict[str, str],
    wikidata_label: str | None,
    tribes: set[str],
) -> tuple[str, str, str]:
    """Return (ethnicity, method, confidence)."""
    nations = _extract_from_patterns(intro, tribes)
    if nations:
        ethnicity = _join_ethnicities(nations)
        reject = _validate_proposed(ethnicity, intro)
        if reject:
            return "", "intro_regex", "rejected"
        return ethnicity, "intro_regex", "high"

    for val in infobox.values():
        nations = _extract_from_patterns(val, tribes)
        if nations:
            ethnicity = _join_ethnicities(nations)
            reject = _validate_proposed(ethnicity, intro or val)
            if not reject:
                return ethnicity, "infobox", "high"

    if wikidata_label:
        nations = _match_dictionary(wikidata_label, tribes)
        if nations and any(w in intro.lower() for w in ("native", "indigenous", "tribe", "pueblo", "nation")):
            ethnicity = _join_ethnicities(nations)
            reject = _validate_proposed(ethnicity, intro)
            if not reject:
                return ethnicity, "wikidata", "low"

    if intro and _match_dictionary(intro, tribes):
        pass
    elif intro and re.search(r"\b(native american|indigenous|alaska native)\b", intro, re.I):
        if not _match_dictionary(intro, tribes):
            return "", "intro_regex", "rejected"

    return "", "none", "rejected"


def load_title_aliases(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload.get("aliases") or payload)


def load_enrichment_cache(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload.get("entries") or {})


def load_roster(db_path: Path) -> list[dict]:
    payload = json.loads(db_path.read_text(encoding="utf-8"))
    records = payload.get("politicians") or []
    db = IndigenousDatabase(db_path=db_path)
    return db._dedupe_roster(records)


def load_override_keys(overrides_path: Path) -> set[str]:
    if not overrides_path.is_file():
        return set()
    payload = json.loads(overrides_path.read_text(encoding="utf-8"))
    return {
        IndigenousDatabase._normalize_roster_name(name)
        for name in (payload.get("ethnicity") or {})
    }


def discover_mvp_targets(
    roster: list[dict],
    overrides_path: Path,
    airtable_client: Any | None = None,
    cap: int = 30,
) -> list[str]:
    override_keys = load_override_keys(overrides_path)
    db = IndigenousDatabase(overrides_path=overrides_path)
    db.database = list(roster)

    freq: Counter[str] = Counter()
    sponsor_fields = ("Indigenous Sponsorship", "Sponsors of the Legislation")

    if airtable_client is not None:
        for table in (airtable_client.pending_table, airtable_client.live_table):
            for record in table.all():
                fields = record.get("fields") or {}
                for field in sponsor_fields:
                    raw = fields.get(field) or ""
                    for sponsor in split_sponsors(str(raw)):
                        entry = db.get_indigenous_sponsor_entry(sponsor)
                        if not entry:
                            continue
                        if not _is_na(entry.get("ethnicity")):
                            continue
                        key = IndigenousDatabase._normalize_roster_name(entry.get("name") or "")
                        if key in override_keys:
                            continue
                        freq[entry.get("name") or ""] += 1

    targets: list[str] = []
    seen: set[str] = set()

    for name in MVP_SPOT_CHECKS:
        key = IndigenousDatabase._normalize_roster_name(name)
        if key in override_keys or key in seen:
            continue
        for record in roster:
            if IndigenousDatabase._normalize_roster_name(record.get("name") or "") == key:
                if _is_na(record.get("ethnicity")):
                    targets.append(record["name"])
                    seen.add(key)
                break

    for name, _count in freq.most_common():
        key = IndigenousDatabase._normalize_roster_name(name)
        if key in seen or key in override_keys:
            continue
        targets.append(name)
        seen.add(key)
        if len(targets) >= cap:
            break

    return targets[:cap]


def _is_na(value: str | None) -> bool:
    return not value or value.strip() in ("", "N/A")


def select_all_na_targets(roster: list[dict], overrides_path: Path) -> list[str]:
    override_keys = load_override_keys(overrides_path)
    names: list[str] = []
    for record in roster:
        if not _is_na(record.get("ethnicity")):
            continue
        key = IndigenousDatabase._normalize_roster_name(record.get("name") or "")
        if key in override_keys:
            continue
        names.append(record.get("name") or "")
    return sorted(names, key=str.lower)


def enrich_name(
    roster_name: str,
    client: WikipediaEnrichClient,
    tribes: set[str],
    aliases: dict[str, str],
    merged_ethnicity: str,
    override_keys: set[str],
    cache_entry: dict | None,
    refresh: bool,
) -> dict[str, Any]:
    key = IndigenousDatabase._normalize_roster_name(roster_name)
    base: dict[str, Any] = {
        "roster_name": roster_name,
        "wikipedia_title": None,
        "ethnicity": None,
        "status": "rejected",
        "method": None,
        "confidence": None,
        "evidence": None,
        "fetched_at": _utc_now_iso(),
        "reject_reason": None,
    }

    if not _is_na(merged_ethnicity):
        base["status"] = "skipped_known"
        base["reject_reason"] = "known_ethnicity"
        return base

    if key in override_keys:
        base["status"] = "skipped_override"
        base["reject_reason"] = "override_present"
        return base

    if cache_entry and cache_entry.get("status") == "accepted" and not refresh:
        return dict(cache_entry)

    try:
        title, resolve_method = client.resolve_title(roster_name, aliases)
    except requests.RequestException as exc:
        base["status"] = "rejected"
        base["reject_reason"] = f"api_error: {exc}"
        return base

    if not title:
        base["status"] = resolve_method if resolve_method in ("page_missing", "disambiguation_unresolved") else "page_missing"
        base["reject_reason"] = resolve_method
        return base

    base["wikipedia_title"] = title

    try:
        intro = client.fetch_intro(title)
        infobox = client.fetch_infobox_fields(title) if intro else {}
        wikidata = None
        ethnicity, method, confidence = extract_ethnicity(intro, infobox, wikidata, tribes)

        if not ethnicity and intro:
            wikidata = client.fetch_wikidata_ethnicity(title)
            ethnicity, method, confidence = extract_ethnicity(intro, infobox, wikidata, tribes)

        base["method"] = method
        base["confidence"] = confidence
        base["evidence"] = intro[:300] if intro else None

        if ethnicity and confidence != "rejected":
            ethnicity = _clean_ethnicity_segments(ethnicity)
            reject = _validate_proposed(ethnicity, intro or "")
            if reject or not ethnicity:
                base["status"] = "rejected"
                base["reject_reason"] = reject or "generic_only"
            else:
                base["status"] = "accepted"
                base["ethnicity"] = ethnicity
        else:
            base["status"] = "rejected"
            base["reject_reason"] = "no_tribe_match"
    except requests.RequestException as exc:
        base["status"] = "rejected"
        base["reject_reason"] = f"api_error: {exc}"

    return base


def write_report(report: dict, report_path: Path | None) -> tuple[Path, Path]:
    reports_dir = ROOT / "scripts" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    json_path = report_path or reports_dir / f"indigenous_ethnicity_enrichment_{stamp}.json"
    md_path = json_path.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    counts = report.get("counts") or {}
    lines = [
        "# Indigenous Ethnicity Enrichment Report",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Mode: {report.get('mode')}",
        "",
        "## Summary",
        "",
        f"- Targets: {counts.get('targets', 0)}",
        f"- Accepted: {counts.get('accepted', 0)}",
        f"- Rejected: {counts.get('rejected', 0)}",
        f"- Unresolved: {counts.get('disambiguation_unresolved', 0)}",
        f"- Page missing: {counts.get('page_missing', 0)}",
        f"- Skipped (override): {counts.get('skipped_override', 0)}",
        f"- Skipped (known): {counts.get('skipped_known', 0)}",
        "",
        "## Accepted entries",
        "",
    ]
    for entry in report.get("entries") or []:
        if entry.get("status") == "accepted":
            lines.append(
                f"- **{entry.get('roster_name')}** → {entry.get('ethnicity')} "
                f"({entry.get('method')}, {entry.get('wikipedia_title')})"
            )

    lines.extend(["", "## Rejected / unresolved", ""])
    for entry in report.get("entries") or []:
        if entry.get("status") not in ("accepted", "skipped_override", "skipped_known"):
            lines.append(
                f"- {entry.get('roster_name')}: {entry.get('status')} "
                f"— {entry.get('reject_reason') or 'n/a'}"
            )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def apply_enrichment(
    results: dict[str, dict],
    enrichment_path: Path,
    existing: dict[str, dict],
) -> None:
    merged = dict(existing)
    merged.update(results)
    payload = {
        "generated_at": _utc_now_iso(),
        "source": "wikipedia",
        "version": 1,
        "entries": merged,
    }
    enrichment_path.parent.mkdir(parents=True, exist_ok=True)
    enrichment_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mvp", action="store_true", help="Enrich MVP high-impact N/A cohort (~30)")
    parser.add_argument("--all-na", action="store_true", help="Enrich all N/A stubs not in overrides")
    parser.add_argument("--names", nargs="+", help="Explicit roster names")
    parser.add_argument("--apply-report", type=Path, help="Apply accepted entries from an existing dry-run report JSON")
    parser.add_argument("--apply", action="store_true", help="Write accepted results to enrichment sidecar")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch even if cached accepted entry exists")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between Wikipedia requests")
    parser.add_argument("--report", type=Path, help="Report JSON output path")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--overrides-path", default=str(DEFAULT_OVERRIDES_PATH))
    parser.add_argument("--enrichment-path", default=str(DEFAULT_ENRICHMENT_PATH))
    parser.add_argument("--aliases-path", default=str(DEFAULT_ALIASES_PATH))
    args = parser.parse_args()
    enrichment_path = Path(args.enrichment_path)

    if args.apply_report:
        report = json.loads(args.apply_report.read_text(encoding="utf-8"))
        cache = load_enrichment_cache(enrichment_path)
        accepted: dict[str, dict] = {}
        for entry in report.get("entries") or []:
            if entry.get("status") != "accepted":
                continue
            ethnicity = _clean_ethnicity_segments(entry.get("ethnicity") or "")
            reject = _validate_proposed(ethnicity, entry.get("evidence") or "x" * 80)
            if reject or not ethnicity:
                continue
            key = IndigenousDatabase._normalize_roster_name(entry.get("roster_name") or "")
            accepted[key] = {**entry, "ethnicity": ethnicity, "status": "accepted"}
        apply_enrichment(accepted, enrichment_path, cache)
        print(f"Applied {len(accepted)} filtered entries from {args.apply_report}")
        return 0

    if not (args.mvp or args.all_na or args.names):
        parser.error("Specify --mvp, --all-na, or --names")

    db_path = Path(args.db_path)
    overrides_path = Path(args.overrides_path)
    aliases = load_title_aliases(Path(args.aliases_path))
    roster = load_roster(db_path)
    tribes = build_tribe_dictionary(roster)
    override_keys = load_override_keys(overrides_path)
    cache = load_enrichment_cache(enrichment_path)

    db = IndigenousDatabase(db_path=db_path, overrides_path=overrides_path, enrichment_path=enrichment_path)
    db.database = db._apply_ethnicity_sidecars(db._dedupe_roster(list(roster)))
    merged_by_key = {
        IndigenousDatabase._normalize_roster_name(r["name"]): r.get("ethnicity", "N/A")
        for r in db.database
    }

    if args.names:
        targets = args.names
        mode = "names"
    elif args.all_na:
        targets = select_all_na_targets(roster, overrides_path)
        mode = "all-na"
    else:
        airtable_client = None
        try:
            from airtable_client import AirtableClient

            if os.getenv("AIRTABLE_API_KEY") and os.getenv("AIRTABLE_BASE_ID"):
                airtable_client = AirtableClient()
        except Exception as exc:
            logger.warning("Airtable unavailable for MVP discovery: %s", exc)
        targets = discover_mvp_targets(roster, overrides_path, airtable_client)
        mode = "mvp"

    client = WikipediaEnrichClient(delay=args.delay)
    results: dict[str, dict] = {}
    entries_report: list[dict] = []

    logger.info("Enriching %d targets (mode=%s, apply=%s)", len(targets), mode, args.apply)

    for i, name in enumerate(targets, 1):
        key = IndigenousDatabase._normalize_roster_name(name)
        merged_eth = merged_by_key.get(key, "N/A")
        cache_entry = cache.get(key)
        logger.info("[%d/%d] %s", i, len(targets), name)
        entry = enrich_name(
            name,
            client,
            tribes,
            aliases,
            merged_eth,
            override_keys,
            cache_entry,
            args.refresh,
        )
        results[key] = entry
        entries_report.append(entry)

    counts = Counter(e.get("status") for e in entries_report)
    report = {
        "generated_at": _utc_now_iso(),
        "mode": mode,
        "targets": targets,
        "counts": {
            "targets": len(targets),
            "accepted": counts.get("accepted", 0),
            "rejected": counts.get("rejected", 0),
            "disambiguation_unresolved": counts.get("disambiguation_unresolved", 0),
            "page_missing": counts.get("page_missing", 0),
            "skipped_override": counts.get("skipped_override", 0),
            "skipped_known": counts.get("skipped_known", 0),
        },
        "entries": entries_report,
    }

    json_path, md_path = write_report(report, args.report)
    logger.info("Report: %s", json_path)
    logger.info("Summary: %s", md_path)
    print(
        f"Targets={len(targets)} accepted={counts.get('accepted', 0)} "
        f"rejected={counts.get('rejected', 0)} "
        f"unresolved={counts.get('disambiguation_unresolved', 0)} "
        f"missing={counts.get('page_missing', 0)}"
    )

    if args.apply:
        accepted = {k: v for k, v in results.items() if v.get("status") == "accepted"}
        apply_enrichment(accepted, enrichment_path, cache)
        logger.info("Applied %d accepted entries to %s", len(accepted), enrichment_path)
    else:
        logger.info("Dry-run only; pass --apply to write sidecar")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
