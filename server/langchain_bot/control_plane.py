"""
Control plane (Phase 3 of the bot redesign).

This is the deterministic safety layer between the customer and the
LLM-first orchestrator. It enforces three concerns the LLM is **not**
trusted with:

  1. **What is allowed now** — verification gate filters tools per turn,
     handoff lock returns immediately when an agent is assigned, cost
     guard falls back to legacy when a customer's daily token cap is hit.
  2. **What gets executed safely** — every tool call is re-validated
     server-side; outbound text is PII-redacted; rate limits via Redis.
  3. **Routing** — whether this turn should run through the LLM-first
     orchestrator at all (vs. fall back to the legacy state machine).

Design rule (also documented in tools/schemas.py):
   The LLM drafts; the control plane gates and executes; templates are
   the protocol library for messages whose exact bytes are contractually
   meaningful (security, branding, parser contracts). Anything else —
   greetings, errors, explanations, summaries — is LLM-drafted.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import settings
from langchain_bot.llm_cost_tracker import customer_under_daily_cap
from langchain_bot.orchestrator import OrchestratorResult, run_turn
from langchain_bot.tools import ToolDefinition, tools_for_verification_state

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Routing decision: should this turn use llm_first?
# ─────────────────────────────────────────────────────────────────────────────
def _llm_first_enabled_for_tenant(tenant_id: int) -> bool:
    raw = (getattr(settings, "bot_mode_llm_first_tenants", "") or "").strip()
    if raw:
        ids = {x.strip() for x in raw.split(",") if x.strip()}
        return str(tenant_id) in ids
    return (getattr(settings, "bot_mode", "legacy") or "legacy").lower() == "llm_first"


def _flow_in_active_deterministic_state(bot_flow: Dict[str, Any]) -> Optional[str]:
    """Return a string label if the legacy flow is mid-script and the LLM
    must NOT take over this turn. None means 'safe to route to LLM'."""
    step = str(bot_flow.get("step") or "").strip()
    blocked_steps = {
        "awaiting_customer_type",
        "existing_awaiting_email",
        "existing_awaiting_verification_code",
        "existing_awaiting_mobile",
        "existing_awaiting_order_id",
        "existing_awaiting_experience",
        "awaiting_agent",
        "awaiting_resume_choice",
        "sourcing_collecting_details",
        "trending_awaiting_country",
        "trending_showing_products",
    }
    if step in blocked_steps:
        return f"deterministic_step:{step}"
    return None


def should_route_to_llm_first(
    *,
    tenant_id: int,
    customer_phone: str,
    bot_flow: Dict[str, Any],
    agent_assigned: bool,
) -> Optional[str]:
    """Return None when llm_first should run, else a string reason for falling
    back to the legacy state machine. Reasons are logged for observability."""
    if agent_assigned:
        return "agent_assigned"
    if not _llm_first_enabled_for_tenant(tenant_id):
        return "tenant_in_legacy_mode"
    blocking = _flow_in_active_deterministic_state(bot_flow)
    if blocking:
        return blocking
    if not customer_under_daily_cap(customer_phone or ""):
        return "daily_token_cap_exceeded"
    return None  # ✅ route to LLM


# ─────────────────────────────────────────────────────────────────────────────
# Tool-list gating
# ─────────────────────────────────────────────────────────────────────────────
def filter_allowed_tools(*, bot_flow: Dict[str, Any]) -> List[ToolDefinition]:
    """Per-turn tool list. Verification gate is the primary safety mechanism:
    account_data tools are physically removed from the LLM's options when the
    customer is unverified."""
    verified = bool(bot_flow.get("verified"))
    in_verif_flow = str(bot_flow.get("step") or "").startswith("existing_awaiting_")
    return tools_for_verification_state(verified=verified, in_verification_flow=in_verif_flow)


# ─────────────────────────────────────────────────────────────────────────────
# PII redaction on outbound LLM text (defense in depth — prompt rules already
# tell the LLM not to echo PII, but we belt-and-suspenders here).
# ─────────────────────────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d[\d\-\s]{7,18}\d)\b")


def redact_pii(text: str, *, customer_email: Optional[str] = None, customer_phone: Optional[str] = None) -> str:
    """Mask the customer's own email and phone if the LLM tries to echo them.

    Note: we do NOT redact every email/phone in the reply (the bot must be able
    to share Arabia's support contacts). We only redact substrings that match
    the *customer's* known identifiers — those should never be echoed.
    """
    if not text:
        return text
    out = text
    ce = (customer_email or "").strip().lower()
    cp = re.sub(r"\D", "", customer_phone or "")
    if ce:
        out = re.sub(re.escape(ce), "[redacted-email]", out, flags=re.IGNORECASE)
    if cp and len(cp) >= 7:
        # Match the digits with optional spaces/dashes between them.
        digit_pattern = r"[\s\-]?".join(re.escape(d) for d in cp)
        out = re.sub(digit_pattern, "[redacted-phone]", out)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Top-level entry: run one turn through llm_first
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class TurnResult:
    """Returned to the caller (process_customer_bot_message wrapper)."""

    reply_text: str
    escalation_signal: bool = False
    verification_signal: Optional[Dict[str, Any]] = None
    csv_signal: Optional[Dict[str, Any]] = None
    trending_signal: Optional[Dict[str, Any]] = None
    tool_calls: List[Dict[str, Any]] = None  # type: ignore[assignment]
    fell_back: bool = False
    fallback_reason: Optional[str] = None


def _load_recent_conversation_history(db: Session, conversation_id: Optional[int], limit: int = 8) -> str:
    """Pull the last N turns from the DB so the LLM can resolve references
    like 'tell me order details' (referring to an order id from the
    previous turn). Without this the orchestrator runs blind and the LLM
    either calls tools with hallucinated args OR drafts confused 'Store
    API error' replies from prompt rules that don't actually apply.

    Best-effort: returns "None" if conversation_id is missing or the query
    fails — never raises.
    """
    if not conversation_id:
        return "None"
    try:
        from sqlalchemy import desc

        from models import Message

        rows = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(desc(Message.id))
            .limit(limit)
            .all()
        )
        rows.reverse()
        if not rows:
            return "None"
        lines = []
        for m in rows:
            label = (
                "Customer"
                if m.sender_type == "customer"
                else ("Agent" if m.sender_type == "agent" else "Bot")
            )
            body = (m.content or "").strip().replace("\n", " ")
            if len(body) > 400:
                body = body[:397] + "..."
            lines.append(f"{label}: {body}")
        return "\n".join(lines)
    except Exception:
        logger.debug("load_recent_conversation_history failed", exc_info=True)
        return "None"


async def run_one_turn(
    *,
    db: Session,
    tenant_id: int,
    customer_phone: str,
    conversation_id: Optional[int],
    user_message: str,
    language: str,
    bot_flow: Dict[str, Any],
    store_client: Any,
    agent_assigned: bool,
    extra_context_blocks: Optional[Dict[str, str]] = None,
    customer_email: Optional[str] = None,
) -> TurnResult:
    """Decide whether to use llm_first; if so, drive the orchestrator with the
    correct tool subset and return a normalized result.

    Callers in the legacy state machine consult ``fell_back`` and
    ``fallback_reason`` to decide whether to handle this turn themselves.
    """
    fallback_reason = should_route_to_llm_first(
        tenant_id=tenant_id,
        customer_phone=customer_phone,
        bot_flow=bot_flow,
        agent_assigned=agent_assigned,
    )
    if fallback_reason is not None:
        logger.debug("control_plane: falling back to legacy (%s)", fallback_reason)
        return TurnResult(
            reply_text="",
            fell_back=True,
            fallback_reason=fallback_reason,
            tool_calls=[],
        )

    allowed = filter_allowed_tools(bot_flow=bot_flow)
    logger.debug(
        "control_plane: routing to llm_first (tenant=%s, verified=%s, tools=%d)",
        tenant_id,
        bool(bot_flow.get("verified")),
        len(allowed),
    )

    # Build the LLM context blocks. Critically, include recent conversation
    # history so multi-turn references ('Tell me order details' after the
    # customer just typed an order id) resolve correctly. Without this, the
    # LLM runs blind and either calls tools with hallucinated args or drafts
    # a 'Store API error' message from a prompt rule that doesn't apply.
    blocks: Dict[str, str] = dict(extra_context_blocks or {})
    if "conversation_history" not in blocks:
        blocks["conversation_history"] = _load_recent_conversation_history(db, conversation_id)
    # Include a brief identity hint so the LLM knows the customer is verified
    # and which seller scope is active, without re-fetching all orders/invoices.
    if "customer_context" not in blocks and bool(bot_flow.get("verified")):
        sid = bot_flow.get("seller_id")
        cust_name = (
            (bot_flow.get("verified_customer") or {}).get("name")
            if isinstance(bot_flow.get("verified_customer"), dict)
            else None
        )
        identity_lines = ["Customer verification status: VERIFIED."]
        if sid:
            identity_lines.append(f"Seller scope: seller_id={sid}.")
        if cust_name:
            identity_lines.append(f"Customer/store name: {cust_name}.")
        identity_lines.append(
            "When the customer references an order id from earlier in the conversation, "
            "call lookup_order with that id. If they ask 'tell me order details' or "
            "similar without naming a new id, look at conversation_history above for the "
            "most recent order id mentioned and use that."
        )
        blocks["customer_context"] = "\n".join(identity_lines)

    orch_result: OrchestratorResult = await run_turn(
        db=db,
        tenant_id=tenant_id,
        customer_phone=customer_phone,
        conversation_id=conversation_id,
        user_message=user_message,
        language=language,
        bot_flow=bot_flow,
        store_client=store_client,
        allowed_tools=allowed,
        extra_context_blocks=blocks,
    )

    redacted = redact_pii(
        orch_result.reply_text,
        customer_email=customer_email,
        customer_phone=customer_phone,
    )

    return TurnResult(
        reply_text=redacted,
        escalation_signal=orch_result.escalation_signal,
        verification_signal=orch_result.verification_signal,
        csv_signal=orch_result.csv_signal,
        trending_signal=orch_result.trending_signal,
        tool_calls=orch_result.tool_calls,
        fell_back=orch_result.used_fallback,
        fallback_reason="llm_failure" if orch_result.used_fallback else None,
    )
