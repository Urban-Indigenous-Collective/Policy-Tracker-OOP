"""Tests for state source schema."""

import pytest
from pydantic import ValidationError

from discovery.source_schema import (
    StateSource,
    load_sources_data,
    slugify_id,
)


def test_index_source_requires_url():
    with pytest.raises(ValidationError):
        StateSource(state="NC", name="Bad", method="index", url="")


def test_search_source_builds_url():
    source = StateSource(
        state="NC",
        name="NC search",
        method="search",
        search_url="https://www.nc.gov/search?query={query}",
        search_param="query",
        search_queries=["MMIP"],
    )
    assert "MMIP" in source.build_search_url("MMIP")


def test_legacy_source_upgrade():
    raw = {
        "state": "WA",
        "name": "WA — app.leg.wa.gov",
        "url": "https://app.leg.wa.gov/billsummary?BillNumber=1639",
        "type": "index",
        "review_needed": True,
    }
    sources = load_sources_data({"sources": [raw]})
    assert len(sources) == 1
    assert sources[0].state == "WA"
    assert sources[0].method == "index"


def test_slugify_id():
    assert slugify_id("NC", "Governor press releases").startswith("nc-")


def test_proclamation_default_max_pages():
    source = StateSource(
        state="NC",
        name="NC proclamations",
        method="index",
        url="https://governor.nc.gov/news/procs",
        content_type="proclamation",
    )
    assert source.max_pages == 15


def test_explicit_max_pages_not_overridden():
    source = StateSource(
        state="NC",
        name="NC proclamations",
        method="index",
        url="https://governor.nc.gov/news/procs",
        content_type="proclamation",
        max_pages=95,
    )
    assert source.max_pages == 95
