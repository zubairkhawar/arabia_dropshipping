"""
LLM cost & token observability for the bot.

Tracks per-customer-per-day token usage in Redis with auto-expiry, plus
process-wide counters for ops dashboards. Provides a soft cap that the
control plane can consult before invoking the LLM in `llm_first` mode.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from config import settings

logger = logging.getLogger(__name__)


# Approximate USD per 1M tokens. Update when OpenAI changes pricing.
# Values as of 2026-04 — rough so cost dashboards are directional, not authoritative.
_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4.1": {"input": 2.50, "output": 10.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


def _model_prices(model: str) -> Dict[str, float]:
    base = (model or "").split(":")[0].split("-2025")[0].split("-2024")[0]
    return _PRICING.get(base) or _PRICING.get(model) or {"input": 2.50, "output": 10.00}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    p = _model_prices(model)
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000.0


@dataclass
class LLMCallRecord:
    customer_phone: Optional[str]
    tenant_id: Optional[int]
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    tool_calls: int = 0
    error: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return int(self.input_tokens) + int(self.output_tokens)

    @property
    def cost_usd(self) -> float:
        return estimate_cost_usd(self.model, self.input_tokens, self.output_tokens)


def _redis_or_none():
    """Return a Redis client or None if memory is disabled (mirrors memory_service pattern)."""
    if not bool(getattr(settings, "conversation_memory_enabled", True)):
        return None
    try:
        from services.memory_service import _get_redis  # type: ignore

        return _get_redis()
    except Exception:
        return None


def _today_utc_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _customer_day_key(customer_phone: str) -> str:
    return f"llm_tokens:{customer_phone}:{_today_utc_key()}"


def _tenant_day_key(tenant_id: int) -> str:
    return f"llm_tokens:tenant:{tenant_id}:{_today_utc_key()}"


def record_llm_call(rec: LLMCallRecord) -> None:
    """Persist token + cost stats for one LLM call. Best-effort; never raises."""
    try:
        logger.info(
            "llm_call model=%s in=%d out=%d total=%d cost_usd=%.4f latency_ms=%d tool_calls=%d phone=%s tenant=%s%s",
            rec.model,
            rec.input_tokens,
            rec.output_tokens,
            rec.total_tokens,
            rec.cost_usd,
            rec.latency_ms,
            rec.tool_calls,
            rec.customer_phone or "?",
            rec.tenant_id if rec.tenant_id is not None else "?",
            f" error={rec.error}" if rec.error else "",
        )
    except Exception:  # noqa: BLE001
        pass

    r = _redis_or_none()
    if r is None:
        return
    try:
        if rec.customer_phone:
            k = _customer_day_key(rec.customer_phone)
            r.incrby(k, rec.total_tokens)
            r.expire(k, 60 * 60 * 36)  # 36h TTL — covers UTC day rollover
        if rec.tenant_id is not None:
            tk = _tenant_day_key(rec.tenant_id)
            r.incrby(tk, rec.total_tokens)
            r.expire(tk, 60 * 60 * 36)
    except Exception:  # noqa: BLE001
        logger.debug("llm_cost_tracker: Redis write failed (non-fatal)", exc_info=True)


def daily_tokens_for_customer(customer_phone: str) -> int:
    r = _redis_or_none()
    if r is None or not customer_phone:
        return 0
    try:
        v = r.get(_customer_day_key(customer_phone))
        return int(v or 0)
    except Exception:
        return 0


def daily_tokens_for_tenant(tenant_id: int) -> int:
    r = _redis_or_none()
    if r is None or tenant_id is None:
        return 0
    try:
        v = r.get(_tenant_day_key(tenant_id))
        return int(v or 0)
    except Exception:
        return 0


def customer_under_daily_cap(customer_phone: str) -> bool:
    """Return True when the customer is below the per-day token soft cap.

    The control plane uses this to decide whether `llm_first` is allowed for
    this turn — over-budget customers fall back to legacy state machine.
    """
    cap = int(getattr(settings, "llm_daily_token_cap_per_customer", 50_000) or 0)
    if cap <= 0:
        return True
    used = daily_tokens_for_customer(customer_phone or "")
    return used < cap


class LLMCallTimer:
    """Context manager that captures latency and produces an LLMCallRecord."""

    def __init__(
        self,
        *,
        model: str,
        customer_phone: Optional[str] = None,
        tenant_id: Optional[int] = None,
    ) -> None:
        self.model = model
        self.customer_phone = customer_phone
        self.tenant_id = tenant_id
        self._t0 = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.tool_calls = 0
        self.error: Optional[str] = None

    def __enter__(self) -> "LLMCallTimer":
        self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            self.error = f"{type(exc).__name__}: {exc!s}"[:200]
        latency_ms = int((time.monotonic() - self._t0) * 1000)
        record_llm_call(
            LLMCallRecord(
                customer_phone=self.customer_phone,
                tenant_id=self.tenant_id,
                model=self.model,
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                latency_ms=latency_ms,
                tool_calls=self.tool_calls,
                error=self.error,
            )
        )
        # Don't suppress exceptions — caller still handles fallback.
        return None
