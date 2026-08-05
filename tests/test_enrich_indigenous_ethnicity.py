"""Unit tests for Wikipedia ethnicity enrichment (mocked API, no live network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from indigenous_database import IndigenousDatabase
from scripts.enrich_indigenous_ethnicity import (
    WikipediaEnrichClient,
    build_tribe_dictionary,
    discover_mvp_targets,
    enrich_name,
    extract_ethnicity,
    load_override_keys,
    select_all_na_targets,
)

JAMES_RAMOS_INTRO = (
    "James Ramos (born August 5, 1966) is an American politician and member of "
    "the Serrano and Cahuilla tribes. A member of the Democratic Party, he has "
    "served in the California State Assembly since 2018."
)

GENERIC_INTRO = (
    "Jane Doe (born 1970) is an American politician and Native American advocate. "
    "She has served in the state legislature since 2015 representing her district."
)


@pytest.fixture
def tribes():
    return build_tribe_dictionary(
        [
            {"name": "James Ramos", "ethnicity": "N/A"},
            {"name": "Deb Haaland", "ethnicity": "Laguna Pueblo"},
            {"name": "Mary Kunesh", "ethnicity": "Standing Rock Dakota / Native Hawaiian"},
        ]
    )


def test_intro_regex_extracts_serrano_cahuilla(tribes):
    ethnicity, method, confidence = extract_ethnicity(JAMES_RAMOS_INTRO, {}, None, tribes)
    assert set(ethnicity.split(" / ")) == {"Serrano", "Cahuilla"}
    assert method == "intro_regex"
    assert confidence == "high"


def test_rejects_generic_native_american_only(tribes):
    ethnicity, method, confidence = extract_ethnicity(GENERIC_INTRO, {}, None, tribes)
    assert ethnicity == ""
    assert confidence == "rejected"


def test_disambiguation_picks_politician_page():
    client = WikipediaEnrichClient(delay=0, session=MagicMock())
    direct_resp = {"query": {"pages": {"-1": {"missing": ""}}}}
    opensearch_resp = [
        "James Ramos",
        ["James Ramos (politician)", "James Ramos (disambiguation)", "James Ramos (actor)"],
        ["desc1", "desc2", "desc3"],
        ["url1", "url2", "url3"],
    ]

    with patch.object(client, "_request", side_effect=[direct_resp, opensearch_resp]):
        title, method = client.resolve_title("James Ramos", {})
    assert title == "James Ramos (politician)"
    assert method == "opensearch"


def test_skips_known_ethnicity(tribes):
    client = WikipediaEnrichClient(delay=0)
    entry = enrich_name(
        "Deb Haaland",
        client,
        tribes,
        {},
        merged_ethnicity="Laguna Pueblo",
        override_keys=set(),
        cache_entry=None,
        refresh=False,
    )
    assert entry["status"] == "skipped_known"


def test_skips_override_entry(tribes):
    client = WikipediaEnrichClient(delay=0)
    override_keys = {IndigenousDatabase._normalize_roster_name("James Ramos")}
    entry = enrich_name(
        "James Ramos",
        client,
        tribes,
        {},
        merged_ethnicity="N/A",
        override_keys=override_keys,
        cache_entry=None,
        refresh=False,
    )
    assert entry["status"] == "skipped_override"


def test_sidecar_merge_priority(tmp_path):
    overrides = tmp_path / "overrides.json"
    enrichment = tmp_path / "enrichment.json"
    overrides.write_text(
        json.dumps({"ethnicity": {"James Ramos": "Override Tribe"}}),
        encoding="utf-8",
    )
    enrichment.write_text(
        json.dumps(
            {
                "entries": {
                    "jamesramos": {
                        "roster_name": "James Ramos",
                        "ethnicity": "Serrano/Cahuilla",
                        "status": "accepted",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        overrides_path=overrides,
        enrichment_path=enrichment,
    )
    records = db._apply_ethnicity_sidecars(
        [
            {
                "name": "James Ramos",
                "party": "Democratic",
                "state": "California",
                "ethnicity": "N/A",
                "offices_held": "N/A",
            }
        ]
    )
    assert records[0]["ethnicity"] == "Override Tribe"

    enrichment_only = tmp_path / "enrichment2.json"
    enrichment_only.write_text(
        json.dumps(
            {
                "entries": {
                    "janedoe": {
                        "roster_name": "Jane Doe",
                        "ethnicity": "Cherokee Nation",
                        "status": "accepted",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    db2 = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        overrides_path=tmp_path / "missing.json",
        enrichment_path=enrichment_only,
    )
    records2 = db2._apply_ethnicity_sidecars(
        [{"name": "Jane Doe", "party": "N/A", "state": "N/A", "ethnicity": "N/A", "offices_held": "N/A"}]
    )
    assert records2[0]["ethnicity"] == "Cherokee Nation"


def test_pick_richer_unchanged_with_enrichment(tmp_path):
    """List-page twin with known ethnicity still wins over enrichment N/A twin."""
    enrichment = tmp_path / "enrichment.json"
    enrichment.write_text(
        json.dumps(
            {
                "entries": {
                    "tysonrunningwolf": {
                        "roster_name": "Tyson Running Wolf",
                        "ethnicity": "Wrong Tribe",
                        "status": "accepted",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    db = IndigenousDatabase(
        db_path=tmp_path / "roster.json",
        enrichment_path=enrichment,
    )
    twins = [
        {
            "name": "Tyson Runningwolf",
            "party": "Democratic",
            "state": "Montana",
            "ethnicity": "Blackfeet Nation",
            "offices_held": "Representative",
        },
        {
            "name": "Tyson Running Wolf",
            "party": "N/A",
            "state": "N/A",
            "ethnicity": "N/A",
            "offices_held": "N/A",
        },
    ]
    merged = db._merge_entries(db._apply_ethnicity_sidecars(twins))
    assert merged["ethnicity"] == "Blackfeet Nation"


def test_select_all_na_targets(tmp_path):
    roster = [
        {"name": "James Ramos", "ethnicity": "N/A"},
        {"name": "Deb Haaland", "ethnicity": "Laguna Pueblo"},
        {"name": "Jane Doe", "ethnicity": "N/A"},
    ]
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"ethnicity": {"James Ramos": "Serrano/Cahuilla"}}), encoding="utf-8")
    names = select_all_na_targets(roster, overrides)
    assert "Jane Doe" in names
    assert "James Ramos" not in names
    assert "Deb Haaland" not in names


def test_discover_mvp_spot_checks(tmp_path):
    roster = [
        {"name": "James Ramos", "ethnicity": "N/A"},
        {"name": "Sharice Davids", "ethnicity": "N/A"},
        {"name": "Deb Haaland", "ethnicity": "Laguna Pueblo"},
    ]
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"ethnicity": {"James Ramos": "Serrano/Cahuilla"}}), encoding="utf-8")
    targets = discover_mvp_targets(roster, overrides, airtable_client=None, cap=30)
    assert "James Ramos" not in targets
    assert "Sharice Davids" in targets
