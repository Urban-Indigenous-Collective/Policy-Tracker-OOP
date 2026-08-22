"""State site crawler uses fetchers and merged manifests."""

from discovery.models import Candidate, utc_now_iso
from discovery.site_crawler import StateSiteSource
from discovery.source_schema import StateSource


def test_state_discover_uses_index_fetcher(monkeypatch):
    source = StateSiteSource()
    row = StateSource(
        state="NC",
        name="NC Governor news",
        content_type="press_release",
        method="index",
        url="https://governor.nc.gov/news",
        review_needed=False,
        source_id="nc-governor-news",
    )
    monkeypatch.setattr(source, "load_sources", lambda: [row])

    class FakeIndexFetcher:
        def discover(self, src):
            assert src.source_id == "nc-governor-news"
            yield Candidate(
                source="state_site",
                state="NC",
                url="https://governor.nc.gov/news/mmip-task-force",
                title="MMIP task force update",
                snippet="MMIP task force update",
                discovered_at=utc_now_iso(),
            )

    source.index_fetcher = FakeIndexFetcher()
    source.search_fetcher = FakeIndexFetcher()
    cands = list(source.discover())
    assert len(cands) == 1
    assert cands[0].state == "NC"
    assert cands[0].source == "state_site"


def test_state_discover_skips_review_needed(monkeypatch):
    source = StateSiteSource()
    pending = StateSource(
        state="NC",
        name="Pending",
        content_type="report",
        method="index",
        url="https://example.gov/news",
        review_needed=True,
        source_id="nc-pending",
    )
    monkeypatch.setattr(source, "load_sources", lambda: [pending])

    class FailFetcher:
        def discover(self, src):
            raise AssertionError("should not crawl review_needed source")

    source.index_fetcher = FailFetcher()
    assert list(source.discover()) == []


def test_merged_state_sources_has_enabled_rows():
    source = StateSiteSource()
    rows = source.load_sources()
    enabled = [s for s in rows if not s.review_needed]
    assert len(rows) >= 200
    assert len(enabled) >= 150
