"""Discovery must dedupe against an in-memory index, not per-candidate Airtable queries."""

from discovery.models import Candidate
from discovery.pipeline import DiscoveryPipeline
from discovery.seen_store import SeenStore


class CountingTable:
    def __init__(self, records, error=None):
        self.records = records
        self.error = error
        self.all_calls = 0

    def all(self, **kwargs):
        self.all_calls += 1
        if self.error:
            raise self.error
        return self.records


class FakeAirtable:
    def __init__(self, live_records=None, pending_error=None):
        self.live_table = CountingTable(live_records or [])
        self.pending_table = CountingTable([], error=pending_error)

    def url_exists_anywhere(self, url):
        raise AssertionError("discovery must not issue per-candidate Airtable lookups")


class RejectingGate:
    def __init__(self):
        self.prescreened = []

    def prescreen(self, candidate):
        self.prescreened.append(candidate.url)
        return False


class EmptySource:
    def discover(self):
        return []

    def active_sources(self):
        return []


class ListSource(EmptySource):
    def __init__(self, candidates):
        self.candidates = candidates

    def discover(self):
        return list(self.candidates)


class StubApiClient:
    quota_exhausted = False

    def log_stats(self):
        pass


class StubMainApp:
    def __init__(self, airtable):
        self.airtable_client = airtable
        self.llm_provider = None
        self.api_client = StubApiClient()


def _pipeline(tmp_path, airtable, candidates, gate):
    return DiscoveryPipeline(
        main_app=StubMainApp(airtable),
        seen_store=SeenStore(str(tmp_path / "seen.db")),
        airtable=airtable,
        slack=object(),
        relevance_gate=gate,
        legiscan_source=ListSource(candidates),
        state_source=EmptySource(),
        federal_source=EmptySource(),
        dry_run=True,
    )


def _candidates(n):
    return [
        Candidate(source="legiscan", state="NM", url=f"https://legiscan.com/NM/bill/SB{i}/2026", title="t")
        for i in range(n)
    ]


def test_discovery_loads_each_table_once_regardless_of_candidate_count(tmp_path):
    airtable = FakeAirtable(
        live_records=[{"fields": {"Bill Overview (Link)": "https://legiscan.com/NM/bill/SB0/2026"}}]
    )
    gate = RejectingGate()
    pipeline = _pipeline(tmp_path, airtable, _candidates(50), gate)

    stats = pipeline.run()

    assert airtable.live_table.all_calls == 1
    assert airtable.pending_table.all_calls == 1
    assert stats.skipped == 1  # SB0 already live
    assert len(gate.prescreened) == 49


def test_discovery_stops_when_index_load_is_rate_limited(tmp_path):
    airtable = FakeAirtable(pending_error=RuntimeError("too many 429 error responses"))
    gate = RejectingGate()
    pipeline = _pipeline(tmp_path, airtable, _candidates(5), gate)

    stats = pipeline.run()

    assert stats.airtable_rate_limited
    assert gate.prescreened == []
