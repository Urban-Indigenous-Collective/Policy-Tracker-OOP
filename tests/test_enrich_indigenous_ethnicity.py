"""Unit tests for Wikipedia ethnicity enrichment (mocked API, no live network)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from indigenous_database import IndigenousDatabase
from scripts.enrich_indigenous_ethnicity import (
    WikipediaEnrichClient,
    _is_generic_only_ethnicity,
    _validate_proposed,
    apply_enrichment,
    build_llm_source_text,
    build_tribe_dictionary,
    discover_mvp_targets,
    enrich_name,
    extract_ethnicity,
    load_override_keys,
    needs_llm_fallback,
    run_llm_ethnicity_fallback,
    select_all_na_targets,
    should_skip_enrichment_write,
    validate_llm_ethnicity_result,
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


def test_accepts_specific_nation_names(tribes):
    intro = "x" * 80
    for nation in ("Lakota", "Cherokee", "Ojibwe", "Navajo", "Crow", "Apache", "Pueblo"):
        assert _validate_proposed(nation, intro) is None


def test_extracts_lakota_from_intro(tribes):
    intro = (
        "Kevin Killer (born 1969) is an American politician and member of the Oglala Lakota "
        "tribe. He has served in the South Dakota House of Representatives since 2009."
    )
    ethnicity, method, confidence = extract_ethnicity(intro, {}, None, tribes)
    assert "Lakota" in ethnicity or "Oglala" in ethnicity
    assert confidence == "high"


def test_extracts_cherokee_from_intro(tribes):
    intro = (
        "Tom Cole (born April 28, 1949) is an American politician and member of the "
        "Cherokee Nation. He has served in the U.S. House since 2003."
    )
    ethnicity, method, confidence = extract_ethnicity(intro, {}, None, tribes)
    assert "Cherokee" in ethnicity
    assert confidence == "high"


def test_extracts_ojibwe_from_intro(tribes):
    intro = (
        "Mary Kunesh (born 1960) is an American politician and member of the Standing Rock "
        "Dakota and Ojibwe tribes. She has served in the Minnesota Senate since 2021."
    )
    ethnicity, method, confidence = extract_ethnicity(intro, {}, None, tribes)
    assert "Ojibwe" in ethnicity
    assert confidence == "high"


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


ANNE_MCKEIG_SOURCE = (
    "Anne McKeig (born 1967) is an American jurist and member of the White Earth Band of Ojibwe. "
    "She was appointed to the Minnesota Supreme Court in 2016."
)


def test_is_generic_only_ethnicity():
    assert _is_generic_only_ethnicity("Native American") is True
    assert _is_generic_only_ethnicity("Cherokee Nation") is False
    assert _is_generic_only_ethnicity("Native American / Cherokee Nation") is False


def test_build_llm_source_text_truncates():
    intro = "A" * 1500
    infobox = {"tribe": "B" * 800}
    text = build_llm_source_text(intro, infobox, max_chars=2000)
    assert len(text) == 2000


def test_validate_llm_ethnicity_accepts_grounded_quote():
    raw = {
        "ethnicity": "White Earth Band of Ojibwe",
        "confidence": 0.92,
        "evidence_quote": "member of the White Earth Band of Ojibwe",
    }
    result, reject = validate_llm_ethnicity_result(raw, ANNE_MCKEIG_SOURCE)
    assert reject is None
    assert result is not None
    assert "Ojibwe" in (result.ethnicity or "")


def test_validate_llm_ethnicity_rejects_low_confidence():
    raw = {
        "ethnicity": "White Earth Band of Ojibwe",
        "confidence": 0.5,
        "evidence_quote": "member of the White Earth Band of Ojibwe",
    }
    result, reject = validate_llm_ethnicity_result(raw, ANNE_MCKEIG_SOURCE)
    assert result is None
    assert reject == "low_confidence"


def test_validate_llm_ethnicity_rejects_hallucinated_quote():
    raw = {
        "ethnicity": "Cherokee Nation",
        "confidence": 0.95,
        "evidence_quote": "member of the Cherokee Nation",
    }
    result, reject = validate_llm_ethnicity_result(raw, ANNE_MCKEIG_SOURCE)
    assert result is None
    assert reject == "evidence_not_in_source"


def test_validate_llm_ethnicity_rejects_generic_only():
    source = "Jane Doe is a Native American politician from Oklahoma."
    raw = {
        "ethnicity": "Native American",
        "confidence": 0.95,
        "evidence_quote": "Native American politician",
    }
    result, reject = validate_llm_ethnicity_result(raw, source)
    assert result is None
    assert reject == "generic_only"


def test_run_llm_ethnicity_fallback_mocked():
    llm = MagicMock()
    llm.complete_json.return_value = {
        "ethnicity": "White Earth Band of Ojibwe",
        "confidence": 0.91,
        "evidence_quote": "member of the White Earth Band of Ojibwe",
    }
    entry = run_llm_ethnicity_fallback(
        llm,
        "Anne McKeig",
        "Anne McKeig",
        ANNE_MCKEIG_SOURCE,
        state="Minnesota",
        party="N/A",
    )
    assert entry["status"] == "accepted"
    assert entry["method"] == "llm_wikipedia"
    assert entry["source"] == "llm_wikipedia"
    assert "Ojibwe" in (entry.get("ethnicity") or "")
    llm.complete_json.assert_called_once()


def test_needs_llm_fallback_when_wiki_rejected():
    wiki_entry = {
        "roster_name": "Anne McKeig",
        "wikipedia_title": "Anne McKeig",
        "status": "rejected",
        "reject_reason": "no_tribe_match",
    }
    key = IndigenousDatabase._normalize_roster_name("Anne McKeig")
    assert needs_llm_fallback(wiki_entry, "N/A", key, set(), None, False) is True


def test_needs_llm_fallback_skips_known_wiki_accept():
    wiki_entry = {
        "roster_name": "James Ramos",
        "wikipedia_title": "James Ramos (politician)",
        "status": "accepted",
        "ethnicity": "Serrano / Cahuilla",
    }
    key = IndigenousDatabase._normalize_roster_name("James Ramos")
    assert needs_llm_fallback(wiki_entry, "N/A", key, set(), None, False) is False


def test_should_skip_enrichment_write_preserves_specific():
    key = IndigenousDatabase._normalize_roster_name("James Ramos")
    existing = {"status": "accepted", "ethnicity": "Serrano / Cahuilla"}
    assert should_skip_enrichment_write(key, existing, set()) is True


def test_apply_enrichment_does_not_overwrite_specific(tmp_path):
    enrichment = tmp_path / "enrichment.json"
    key = IndigenousDatabase._normalize_roster_name("James Ramos")
    existing = {
        key: {
            "roster_name": "James Ramos",
            "ethnicity": "Serrano / Cahuilla",
            "status": "accepted",
            "method": "intro_regex",
        }
    }
    enrichment.write_text(
        json.dumps({"entries": existing}),
        encoding="utf-8",
    )
    new_results = {
        key: {
            "roster_name": "James Ramos",
            "ethnicity": "Wrong Tribe",
            "status": "accepted",
            "method": "llm_wikipedia",
        }
    }
    written = apply_enrichment(new_results, enrichment, existing)
    assert written == 0
    payload = json.loads(enrichment.read_text(encoding="utf-8"))
    assert payload["entries"][key]["ethnicity"] == "Serrano / Cahuilla"
