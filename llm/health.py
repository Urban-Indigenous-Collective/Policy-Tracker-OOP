"""Lightweight LLM reachability probe for nightly ops alerts."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LlmHealthResult:
    ok: bool
    base_url: str
    model: str
    latency_ms: int = 0
    error: str = ""
    checked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _llm_base_url() -> str:
    return (
        os.getenv("LLM_BASE_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or "http://localhost:11434/v1"
    ).rstrip("/")


def _llm_model() -> str:
    return (
        os.getenv("LLM_MODEL")
        or os.getenv("OLLAMA_MODEL")
        or "qwen2.5vl:32b"
    )


def probe_llm(*, timeout_sec: float | None = None) -> LlmHealthResult:
    """Return whether the configured OpenAI-compatible LLM answers promptly.

    Uses ``models.list`` only (cheap) so we do not burn GPU tokens on every check.
    """
    from discovery.models import utc_now_iso

    base_url = _llm_base_url()
    model = _llm_model()
    timeout = float(
        timeout_sec
        if timeout_sec is not None
        else os.getenv("LLM_HEALTH_TIMEOUT_SEC", "8")
    )
    checked_at = utc_now_iso()
    api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("OLLAMA_API_KEY")
        or "ollama"
    )

    t0 = time.monotonic()
    try:
        from openai import OpenAI

        client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        listed = client.models.list()
        latency_ms = int((time.monotonic() - t0) * 1000)
        ids = [getattr(m, "id", "") for m in (listed.data or [])]
        # Some servers list a different id than LLM_MODEL; reachability is enough.
        result = LlmHealthResult(
            ok=True,
            base_url=base_url,
            model=model,
            latency_ms=latency_ms,
            checked_at=checked_at,
        )
        if ids and model and model not in ids:
            # Still ok (server up) but note mismatch for operators.
            result.error = f"model {model!r} not in listed ids ({len(ids)} models)"
            logger.warning(
                "LLM health: reachable but model %r not in /v1/models (%s…)",
                model,
                ", ".join(ids[:5]),
            )
        else:
            logger.info(
                "LLM health ok base=%s model=%s latency_ms=%d",
                base_url,
                model,
                latency_ms,
            )
        return result
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        err = f"{type(exc).__name__}: {exc}"
        logger.error(
            "LLM health FAILED base=%s model=%s after %dms: %s",
            base_url,
            model,
            latency_ms,
            err,
        )
        return LlmHealthResult(
            ok=False,
            base_url=base_url,
            model=model,
            latency_ms=latency_ms,
            error=err[:500],
            checked_at=checked_at,
        )
