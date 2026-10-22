"""When policy metadata was last refreshed by the nightly status pipeline."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from discovery.status_refresh import status_refresh_log_path

logger = logging.getLogger(__name__)


def _parse_run_at(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("Skipping unparsable status refresh run_at: %r", text)
        return None


def last_successful_status_refresh_at() -> datetime | None:
    """Latest completed status-refresh run (nightly pipeline), if logged."""
    path = status_refresh_log_path()
    if not path.is_file():
        return None

    last_ok: datetime | None = None
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("errors"):
                    continue
                parsed = _parse_run_at(str(payload.get("run_at") or ""))
                if parsed is not None:
                    last_ok = parsed
    except OSError as exc:
        logger.warning("Could not read status refresh log %s: %s", path, exc)
        return None

    return last_ok
