"""Live progress tracking for discovery / backfill runs."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PHASES = (
    "initializing",
    "legiscan",
    "state_crawl",
    "processing",
    "complete",
)


def progress_path() -> Path:
    raw = os.getenv("DISCOVERY_PROGRESS_PATH", "data/discovery_progress.json")
    path = Path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def render_bar(current: int, total: int, width: int = 32) -> str:
    if total <= 0:
        return f"[{'?' * width}]"
    current = max(0, min(current, total))
    filled = int(width * current / total)
    if filled >= width:
        return f"[{'=' * width}]"
    return f"[{'=' * filled}{'>' if filled < width else ''}{' ' * (width - filled - 1)}]"


class DiscoveryProgress:
    """Write machine-readable progress for watch scripts."""

    def __init__(self, path: Path | None = None):
        self.path = path or progress_path()
        self._state: dict[str, Any] = {
            "phase": "initializing",
            "phase_label": "Starting",
            "step_current": 0,
            "step_total": 0,
            "discovered": 0,
            "analyzed": 0,
            "rejected": 0,
            "skipped": 0,
            "errors": 0,
            "max_analyses": int(os.getenv("DISCOVERY_MAX_ANALYSES_PER_RUN", "25")),
            "detail": "",
            "updated_at": "",
        }

    def _write(self) -> None:
        self._state["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self.path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.debug("Could not write progress file: %s", exc)
        pct = self.percent
        logger.info(
            "PROGRESS phase=%s step=%s/%s pct=%s discovered=%s analyzed=%s rejected=%s skipped=%s errors=%s detail=%r",
            self._state["phase"],
            self._state["step_current"],
            self._state["step_total"],
            pct,
            self._state["discovered"],
            self._state["analyzed"],
            self._state["rejected"],
            self._state["skipped"],
            self._state["errors"],
            self._state.get("detail", ""),
        )

    @property
    def percent(self) -> int:
        total = int(self._state.get("step_total") or 0)
        current = int(self._state.get("step_current") or 0)
        if total <= 0:
            return 0
        return min(100, int(100 * current / total))

    def start(self, max_analyses: int | None = None) -> None:
        if max_analyses is not None:
            self._state["max_analyses"] = max_analyses
        self._state.update(
            phase="initializing",
            phase_label="Initializing application",
            step_current=0,
            step_total=1,
            detail="",
        )
        self._write()

    def begin_legiscan(self, total_queries: int) -> None:
        self._state.update(
            phase="legiscan",
            phase_label="LegiScan search (2020–present)",
            step_current=0,
            step_total=total_queries,
            detail="",
        )
        self._write()

    def legiscan_query(self, current: int, total: int, detail: str) -> None:
        self._state.update(
            phase="legiscan",
            step_current=current,
            step_total=total,
            detail=detail[:200],
        )
        self._write()

    def legiscan_complete(self, bill_count: int) -> None:
        self._state["detail"] = f"{bill_count} unique bills from LegiScan"
        self._write()

    def begin_state_crawl(self, total_sources: int) -> None:
        self._state.update(
            phase="state_crawl",
            phase_label="State site crawl",
            step_current=0,
            step_total=total_sources,
            detail="",
        )
        self._write()

    def state_source(self, current: int, total: int, name: str) -> None:
        self._state.update(
            phase="state_crawl",
            step_current=current,
            step_total=total,
            detail=name[:200],
        )
        self._write()

    def begin_processing(self, total_candidates: int, max_analyses: int) -> None:
        cap = min(total_candidates, max_analyses) if max_analyses > 0 else total_candidates
        self._state.update(
            phase="processing",
            phase_label="Analyzing candidates",
            step_current=0,
            step_total=max(cap, 1),
            discovered=total_candidates,
            max_analyses=max_analyses,
            detail="",
        )
        self._write()

    def processing_candidate(
        self,
        index: int,
        total: int,
        *,
        analyzed: int,
        rejected: int,
        skipped: int,
        errors: int,
        detail: str,
    ) -> None:
        self._state.update(
            phase="processing",
            step_current=index,
            step_total=total,
            analyzed=analyzed,
            rejected=rejected,
            skipped=skipped,
            errors=errors,
            detail=detail[:200],
        )
        self._write()

    def complete(self, stats) -> None:
        self._state.update(
            phase="complete",
            phase_label="Run complete",
            step_current=int(stats.analyzed),
            step_total=max(int(stats.discovered), 1),
            discovered=int(stats.discovered),
            analyzed=int(stats.analyzed),
            rejected=int(stats.rejected),
            skipped=int(stats.skipped),
            errors=int(stats.errors),
            detail="Done",
        )
        self._write()

    def summary_line(self) -> str:
        bar = render_bar(int(self._state["step_current"]), int(self._state["step_total"]))
        return (
            f"{bar} {self.percent:3d}% | {self._state['phase_label']} "
            f"({self._state['step_current']}/{self._state['step_total']}) | "
            f"found {self._state['discovered']} | "
            f"+{self._state['analyzed']} pending | "
            f"{self._state['rejected']} rejected | "
            f"{self._state['skipped']} skipped | "
            f"{self._state['errors']} errors"
        )


_tracker: DiscoveryProgress | None = None


def get_progress(enabled: bool | None = None) -> DiscoveryProgress | None:
    if enabled is False:
        return None
    if enabled is None:
        enabled = os.getenv("DISCOVERY_PROGRESS", "true").lower() in ("1", "true", "yes")
    if not enabled:
        return None
    global _tracker
    if _tracker is None:
        _tracker = DiscoveryProgress()
    return _tracker
