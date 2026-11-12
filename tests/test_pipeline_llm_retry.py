"""LLM infrastructure failures must not permanently suppress rediscovery."""

from discovery.models import Candidate
from discovery.pipeline import DiscoveryPipeline, DiscoveryRunStats
from discovery.seen_store import SeenStore


class StubDuplicateIndex:
    def is_duplicate(self, *args, **kwargs):
        return False


class StubMainApp:
    def __init__(self):
        self.airtable_client = object()
        self.llm_provider = None
        self.api_client = None
        self.bill_processor = None
        self.legiscan_processor = None


class FailingRelevanceGate:
    def __init__(self, stage: str):
        self.stage = stage
        self.evaluations = 0

    def prescreen(self, candidate):
        return True

    def evaluate(self, candidate, excerpt=""):
        self.evaluations += 1
        return False, None, self.stage


class NotMmipGate:
    def __init__(self):
        self.evaluations = 0

    def prescreen(self, candidate):
        return True

    def evaluate(self, candidate, excerpt=""):
        self.evaluations += 1

        class Result:
            confidence = 0.9
            rationale = "Not about MMIP."
            is_mmip = False

        return False, Result(), "llm"


def _candidate(url="https://example.com/bill/retry-me"):
    return Candidate(
        source="legiscan",
        state="NM",
        url=url,
        title="Missing Indigenous persons task force",
        snippet="A bill establishing an MMIP advisory council and data sharing.",
    )


def _pipeline(tmp_path, gate):
    return DiscoveryPipeline(
        main_app=StubMainApp(),
        seen_store=SeenStore(tmp_path / "test.db"),
        airtable=object(),
        slack=object(),
        relevance_gate=gate,
        duplicate_index=StubDuplicateIndex(),
        dry_run=True,
    )


def test_llm_error_does_not_write_rejected_and_retries_next_run(tmp_path):
    gate = FailingRelevanceGate("llm_error")
    pipeline = _pipeline(tmp_path, gate)
    cand = _candidate()
    stats = DiscoveryRunStats()

    pipeline._process_candidate(cand, stats)

    assert stats.llm_errors == 1
    assert stats.rejected == 0
    assert pipeline.seen_store.get(cand.url) is None

    should, reason = pipeline.seen_store.should_process(cand.url)
    assert should is True
    assert reason == "new"

    # Second run hits the LLM again.
    pipeline._process_candidate(cand, DiscoveryRunStats())
    assert gate.evaluations == 2


def test_llm_fail_does_not_write_rejected(tmp_path):
    gate = FailingRelevanceGate("llm_fail")
    pipeline = _pipeline(tmp_path, gate)
    cand = _candidate()
    stats = DiscoveryRunStats()

    pipeline._process_candidate(cand, stats)

    assert stats.llm_errors == 1
    assert stats.rejected == 0
    assert pipeline.seen_store.get(cand.url) is None


def test_genuine_llm_reject_still_terminal(tmp_path):
    gate = NotMmipGate()
    pipeline = _pipeline(tmp_path, gate)
    cand = _candidate()
    stats = DiscoveryRunStats()

    pipeline._process_candidate(cand, stats)

    assert stats.rejected == 1
    assert stats.llm_errors == 0
    row = pipeline.seen_store.get(cand.url)
    assert row is not None
    assert row["status"] == "rejected"
    assert row["verdict"] == "llm"

    should, reason = pipeline.seen_store.should_process(cand.url)
    assert should is False
    assert reason == "already_rejected"


def test_historical_rejected_llm_error_is_retried(tmp_path):
    store = SeenStore(tmp_path / "hist.db")
    url = "https://example.com/bill/stuck"
    store.upsert(url, "legiscan", status="rejected", verdict="llm_error")

    gate = FailingRelevanceGate("llm_error")
    pipeline = DiscoveryPipeline(
        main_app=StubMainApp(),
        seen_store=store,
        airtable=object(),
        slack=object(),
        relevance_gate=gate,
        duplicate_index=StubDuplicateIndex(),
        dry_run=True,
    )
    stats = DiscoveryRunStats()
    pipeline._process_candidate(_candidate(url), stats)

    assert gate.evaluations == 1
    assert stats.llm_errors == 1
    # Still no permanent reject write from this failure path.
    should, reason = store.should_process(url)
    assert should is True
    assert reason == "retry_llm_error"
