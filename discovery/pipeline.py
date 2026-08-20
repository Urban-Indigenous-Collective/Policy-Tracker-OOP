import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from airtable_client import AirtableClient
from discovery.federal_crawler import FederalSiteSource
from discovery.legiscan_search import LegiScanSearchSource
from discovery.legiscan_quota import is_legiscan_limit_error, legiscan_quota_payload
from discovery.models import Candidate, utc_now_iso
from discovery.relevance import MMIPRelevanceGate
from discovery.seen_store import SeenStore
from discovery.site_crawler import StateSiteSource
from discovery.slack_report import discovery_slack_always, save_deferred_report, should_defer_slack
from main_application import MainApplication
from slack_client import SlackNotifier

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryRunStats:
    discovered: int = 0
    skipped: int = 0
    rejected: int = 0
    analyzed: int = 0
    errors: int = 0
    slack_items: list[dict[str, Any]] = field(default_factory=list)
    by_state: dict[str, Any] = field(default_factory=dict)
    sources_attempted: dict[str, Any] = field(default_factory=dict)
    legiscan_limited: bool = False
    legiscan_limit_reason: str = ""
    run_started_at: str = ""
    run_finished_at: str = ""


class DiscoveryPipeline:
    """Orchestrate nightly MMIP policy discovery, analysis, and Pending upload."""

    def __init__(
        self,
        main_app: MainApplication,
        seen_store: SeenStore | None = None,
        airtable: AirtableClient | None = None,
        slack: SlackNotifier | None = None,
        relevance_gate: MMIPRelevanceGate | None = None,
        legiscan_source: LegiScanSearchSource | None = None,
        state_source: StateSiteSource | None = None,
        federal_source: FederalSiteSource | None = None,
        dry_run: bool = False,
    ):
        self.main_app = main_app
        self.seen_store = seen_store or SeenStore(
            os.getenv("DISCOVERY_DB_PATH", "data/discovery.db")
        )
        self.airtable = airtable or main_app.airtable_client
        self.slack = slack or SlackNotifier()
        self.relevance_gate = relevance_gate or MMIPRelevanceGate(main_app.llm_provider)
        self.legiscan_source = legiscan_source or LegiScanSearchSource(main_app.api_client)
        self.state_source = state_source or StateSiteSource()
        self.federal_source = federal_source or FederalSiteSource()
        self.dry_run = dry_run
        self.max_analyses = int(os.getenv("DISCOVERY_MAX_ANALYSES_PER_RUN", "25"))
        self.discovery_enabled = os.getenv("DISCOVERY_ENABLED", "true").lower() in (
            "1",
            "true",
            "yes",
        )
        self._legiscan_limited = False
        self._legiscan_limit_reason = ""
        self._source_counts: dict[str, int] = {}

    def collect_candidates(self) -> list[Candidate]:
        candidates: list[Candidate] = []
        source_counts = {"legiscan": 0, "state_site": 0, "federal_site": 0}

        try:
            legiscan_candidates = list(self.legiscan_source.discover())
            source_counts["legiscan"] = len(legiscan_candidates)
            candidates.extend(legiscan_candidates)
        except Exception as exc:
            if is_legiscan_limit_error(exc):
                logger.warning("LegiScan discovery skipped (quota): %s", exc)
                self._legiscan_limited = True
                self._legiscan_limit_reason = str(exc)
            else:
                raise

        state_candidates = list(self.state_source.discover())
        source_counts["state_site"] = len(state_candidates)
        candidates.extend(state_candidates)

        try:
            federal_candidates = list(self.federal_source.discover())
        except Exception as exc:
            logger.exception("Federal site discovery failed: %s", exc)
            federal_candidates = []
        source_counts["federal_site"] = len(federal_candidates)
        candidates.extend(federal_candidates)

        if getattr(self.main_app.api_client, "quota_exhausted", False):
            self._legiscan_limited = True
            self._legiscan_limit_reason = (
                getattr(self.main_app.api_client, "last_error_alert", "")
                or "LegiScan API monthly limit reached"
            )

        self._source_counts = source_counts
        return candidates

    def _get_excerpt(self, candidate: Candidate) -> str:
        combined = f"{candidate.title}\n{candidate.snippet}"
        if len(combined.strip()) >= 200:
            return combined
        if candidate.source == "state_site":
            text, content_hash = self.state_source.fetch_page_text(candidate.url)
            if content_hash:
                candidate.content_hash = content_hash
            return text or combined
        if candidate.source == "federal_site":
            text, content_hash = self.federal_source.fetch_page_text(candidate.url)
            if content_hash:
                candidate.content_hash = content_hash
            return text or combined
        return combined

    def _process_candidate(self, candidate: Candidate, stats: DiscoveryRunStats) -> None:
        url = candidate.url.strip()
        if not url:
            stats.skipped += 1
            return

        should, reason = self.seen_store.should_process(
            url, change_hash=candidate.change_hash, content_hash=candidate.content_hash
        )
        if not should:
            logger.debug("Skipping %s: %s", url, reason)
            stats.skipped += 1
            return

        if self.airtable.url_exists_anywhere(url):
            logger.info("Already in Airtable: %s", url)
            self.seen_store.upsert(
                url,
                candidate.source,
                state=candidate.state,
                external_id=candidate.external_id,
                change_hash=candidate.change_hash,
                content_hash=candidate.content_hash,
                status="pending",
                verdict="airtable_duplicate",
            )
            stats.skipped += 1
            return

        if not self.relevance_gate.prescreen(candidate):
            self.seen_store.upsert(
                url,
                candidate.source,
                state=candidate.state,
                external_id=candidate.external_id,
                change_hash=candidate.change_hash,
                content_hash=candidate.content_hash,
                status="rejected",
                verdict="prescreen_fail",
            )
            stats.rejected += 1
            return

        excerpt = self._get_excerpt(candidate)
        is_relevant, relevance_result, stage = self.relevance_gate.evaluate(candidate, excerpt)
        if not is_relevant:
            verdict = stage
            confidence = relevance_result.confidence if relevance_result else None
            self.seen_store.upsert(
                url,
                candidate.source,
                state=candidate.state,
                external_id=candidate.external_id,
                change_hash=candidate.change_hash,
                content_hash=candidate.content_hash,
                status="rejected",
                verdict=verdict,
                confidence=confidence,
            )
            stats.rejected += 1
            return

        if stats.analyzed >= self.max_analyses:
            logger.info("Max analyses per run reached (%d), deferring %s", self.max_analyses, url)
            stats.skipped += 1
            return

        if self.dry_run:
            logger.info(
                "DRY RUN: would analyze %s (confidence=%.2f)",
                url,
                relevance_result.confidence if relevance_result else 0,
            )
            stats.analyzed += 1
            return

        try:
            doc_id = None
            if candidate.source == "legiscan":
                doc_id = self.main_app.legiscan_processor.extract_doc_id(url)

            bill_processor = self.main_app.bill_processor
            bill_processor.compiled_bill = {}

            success, message = bill_processor.get_doc_text(url, doc_id=doc_id)
            if not success:
                raise RuntimeError(message)

            bill_id = bill_processor.compiled_bill.get("bill_id")
            success, message = bill_processor.get_bill_details(bill_id)
            if not success:
                raise RuntimeError(message)

            success, message = bill_processor.summarize_bill_text()
            if not success:
                raise RuntimeError(message)

            success, message = bill_processor.parse_bill_object()
            if not success:
                raise RuntimeError(message)

            bill_data = bill_processor.compiled_bill.get("bill_data")
            if not bill_data:
                raise RuntimeError("No bill_data after processing")

            record = self.airtable.create_pending_record(
                bill_data=bill_data,
                source=(
                    "LegiScan"
                    if candidate.source == "legiscan"
                    else "Federal Site"
                    if candidate.source == "federal_site"
                    else "State Site"
                ),
                relevance_confidence=relevance_result.confidence if relevance_result else 0.0,
                relevance_rationale=relevance_result.rationale if relevance_result else "",
                discovered_on=utc_now_iso()[:10],
            )

            self.seen_store.upsert(
                url,
                candidate.source,
                state=candidate.state,
                external_id=candidate.external_id,
                change_hash=candidate.change_hash,
                content_hash=candidate.content_hash,
                status="pending",
                verdict="analyzed",
                confidence=relevance_result.confidence if relevance_result else None,
            )
            stats.analyzed += 1
            stats.slack_items.append(
                {
                    "state": bill_data.get("State", candidate.state),
                    "title": bill_data.get("Title", candidate.title),
                    "summary": bill_data.get("Summary", "")[:300],
                    "categories": bill_data.get("Categories", ""),
                    "confidence": relevance_result.confidence if relevance_result else 0.0,
                    "source_url": bill_data.get("Bill Overview", url),
                    "pending_url": "",
                }
            )
            logger.info("Created pending record for %s (id=%s)", url, record.get("id"))
        except Exception as exc:
            logger.exception("Error processing candidate %s: %s", url, exc)
            self.seen_store.upsert(
                url,
                candidate.source,
                state=candidate.state,
                external_id=candidate.external_id,
                change_hash=candidate.change_hash,
                content_hash=candidate.content_hash,
                status="error",
                verdict=str(exc),
            )
            stats.errors += 1

    def run(self) -> DiscoveryRunStats:
        if not self.discovery_enabled and not self.dry_run:
            logger.info("Discovery disabled via DISCOVERY_ENABLED")
            return DiscoveryRunStats()

        stats = DiscoveryRunStats(run_started_at=utc_now_iso())
        candidates = self.collect_candidates()
        stats.discovered = len(candidates)
        stats.sources_attempted = dict(self._source_counts)
        stats.legiscan_limited = self._legiscan_limited
        stats.legiscan_limit_reason = self._legiscan_limit_reason
        logger.info("Collected %d discovery candidates", len(candidates))

        for candidate in candidates:
            self._process_candidate(candidate, stats)

        stats.run_finished_at = utc_now_iso()
        if not self.dry_run:
            if should_defer_slack():
                save_deferred_report(stats)
            else:
                self.slack.notify_discovery_batch(stats.slack_items)
                self.slack.notify_run_complete(
                    analyzed=stats.analyzed,
                    rejected=stats.rejected,
                    skipped=stats.skipped,
                    errors=stats.errors,
                    discovered=stats.discovered,
                    by_state=stats.by_state,
                    run_started_at=stats.run_started_at,
                    run_finished_at=stats.run_finished_at,
                    sources_attempted=stats.sources_attempted,
                    always_notify=discovery_slack_always(),
                )
        self.main_app.api_client.log_stats()
        return stats
