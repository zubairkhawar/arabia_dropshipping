"""
Structured onboarding / support flow for customer-facing channels (web, WhatsApp).

State is stored on Conversation.conversation_metadata under key "bot_flow".
Team routing uses Agent.team values: new_customer, beginner, intermediate, expert.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from models import Conversation, Order
from services.ai_orchestrator_service.services import AIOrchestrator
from services.store_integration_service.client import StoreIntegrationClient
from services.customer_bot_flow.templates import BOT_FLOW_TEMPLATES

BOT_FLOW_KEY = "bot_flow"

# Verbatim copy from templates module (never composed by the LLM).
MSGS = BOT_FLOW_TEMPLATES

# Align with admin agent team labels (Agent.team)
TEAM_NEW_CUSTOMER = "new_customer"
TEAM_BEGINNER = "beginner"
TEAM_INTERMEDIATE = "intermediate"
TEAM_EXPERT = "expert"


def _t(lang: str, table: Dict[str, str]) -> str:
    return table.get(lang) or table.get("english") or next(iter(table.values()))


def format_kb_reply(lang: str, ai_body: str) -> str:
    """Wrap a knowledge/AI answer for new-customer style responses."""
    return _t(lang, MSGS["kb_wrap"]).format(body=(ai_body or "").strip())


def _normalize_meta(conv: Conversation) -> Dict[str, Any]:
    raw = conv.conversation_metadata
    if raw is None or not isinstance(raw, dict):
        return {}
    return dict(raw)


def _get_flow(meta: Dict[str, Any]) -> Dict[str, Any]:
    bf = meta.get(BOT_FLOW_KEY)
    if not isinstance(bf, dict):
        return {}
    return dict(bf)


def _merge_flow(meta: Dict[str, Any], flow: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(meta)
    out[BOT_FLOW_KEY] = flow
    return out


def _looks_like_greeting(text: str) -> bool:
    """
    Short salam / hi / hello style messages on the new-customer menu should not
    go through the LLM with kb_wrap (that is for real questions).
    """
    s = (text or "").strip().lower()
    if not s or len(s) > 55 or "?" in s:
        return False
    tokens = [t for t in re.sub(r"[^\w\s\u0600-\u06FF]", " ", s).split() if t]
    if len(tokens) > 6:
        return False
    blob = " ".join(tokens)
    if any(
        x in blob
        for x in (
            "salam",
            "salaam",
            "assalam",
            "asslam",
            "alaikum",
            "alikum",
            "walaikum",
            "walaykum",
        )
    ):
        return True
    if blob in ("hi", "hey", "hello", "hi there", "hey there", "namaste"):
        return True
    if re.match(r"^good (morning|evening|afternoon)$", blob):
        return True
    if any("\u0600" <= ch <= "\u06FF" for ch in s) and len(tokens) <= 4:
        # Short Arabic-only nicety e.g. مرحبا
        if any(w in blob for w in ("marhaba", "مرحب", "السلام", "سلام")):
            return True
    return False


def _is_escalation_trigger(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    phrases = (
        "support",
        "agent",
        "help",
        "baat karni hai",
        "talk to human",
        "human",
        "talk to",
        "speak with",
        "madad",
        "representative",
    )
    return any(p in t for p in phrases)


def _parse_choice(text: str, mapping: Dict[str, str]) -> Optional[str]:
    raw = (text or "").strip().lower()
    raw = re.sub(r"[^\w\u0600-\u06FF\s]", " ", raw)
    parts = raw.split()
    first = parts[0] if parts else ""
    if first in mapping:
        return mapping[first]
    if raw in mapping:
        return mapping[raw]
    return None


def _delivery_status(order: Order) -> str:
    data = order.order_data or {}
    if isinstance(data, dict):
        for key in ("delivery_status", "fulfillment_status", "shipping_status"):
            v = data.get(key)
            if v:
                return str(v)
    return "—"


async def _lookup_order(
    db: Session,
    tenant_id: int,
    order_ref: str,
    store_client: StoreIntegrationClient,
) -> Tuple[Optional[Dict[str, Any]], str]:
    ref = (order_ref or "").strip()
    if not ref:
        return None, ""

    row = (
        db.query(Order)
        .filter(Order.tenant_id == tenant_id, Order.order_number == ref)
        .first()
    )
    if row:
        return {
            "order_number": row.order_number,
            "status": row.status,
            "delivery": _delivery_status(row),
        }, "db"

    detail = await store_client.get_order_by_id(ref)
    if not detail:
        detail = await store_client.get_order_by_number(ref)
    if not detail:
        return None, ""

    return {
        "order_number": str(detail.get("order_number") or detail.get("id") or ref),
        "status": str(detail.get("status") or "unknown"),
        "delivery": str(
            (detail.get("delivery_status") or detail.get("fulfillment_status") or "—")
        ),
    }, "api"


@dataclass
class BotFlowResult:
    """Result of one customer message through the structured bot flow."""

    reply_text: str
    merge_metadata: Dict[str, Any]
    use_ai: bool
    """If True, caller should run LangChain with augmented user text and optional API skip."""
    ai_user_message: str
    skip_store_api: bool
    assign_team: Optional[str]
    escalate: bool
    handled: bool
    """False means caller should use legacy behavior (e.g. human agent owns chat)."""


async def process_customer_bot_message(
    *,
    db: Session,
    conversation: Optional[Conversation],
    user_message: str,
    tenant_id: int,
    orchestrator: AIOrchestrator,
    phone: Optional[str] = None,
) -> BotFlowResult:
    if conversation is None:
        return BotFlowResult(
            reply_text="",
            merge_metadata={},
            use_ai=True,
            ai_user_message=user_message,
            skip_store_api=False,
            assign_team=None,
            escalate=await orchestrator.should_escalate(user_message),
            handled=False,
        )

    if conversation.agent_id is not None:
        return BotFlowResult(
            reply_text="",
            merge_metadata={},
            use_ai=False,
            ai_user_message=user_message,
            skip_store_api=False,
            assign_team=None,
            escalate=False,
            handled=False,
        )

    lang = await orchestrator.detect_language(user_message)
    if not (user_message or "").strip():
        lang = "roman_urdu"

    meta = _normalize_meta(conversation)
    flow = _get_flow(meta)
    step = flow.get("step") or "awaiting_customer_type"
    flow_lang = lang

    store_client = StoreIntegrationClient()
    escalate_for_ai_turn = await orchestrator.should_escalate(user_message)

    def save(
        f: Dict[str, Any],
        reply: str,
        team: Optional[str] = None,
        esc: bool = False,
        skip_api: Optional[bool] = None,
    ):
        f["lang"] = flow_lang
        if skip_api is None:
            skip_api = f.get("customer_kind") == "new"
        return BotFlowResult(
            reply_text=reply,
            merge_metadata=_merge_flow(meta, f),
            use_ai=False,
            ai_user_message=user_message,
            skip_store_api=bool(skip_api),
            assign_team=team,
            escalate=esc,
            handled=True,
        )

    def ai_forward(msg: str, f: Dict[str, Any], skip_api: bool):
        f["lang"] = flow_lang
        return BotFlowResult(
            reply_text="",
            merge_metadata=_merge_flow(meta, f),
            use_ai=True,
            ai_user_message=msg,
            skip_store_api=skip_api,
            assign_team=None,
            escalate=escalate_for_ai_turn,
            handled=True,
        )

    text = (user_message or "").strip()

    # Global escalation
    if _is_escalation_trigger(text) and step != "existing_awaiting_verification":
        kind = flow.get("customer_kind")
        exp_team = flow.get("experience_team")
        if kind == "new" or not kind:
            team = TEAM_NEW_CUSTOMER
        else:
            team = exp_team or TEAM_BEGINNER
        f = {**flow, "step": "awaiting_agent", "intro_shown": True}
        return save(
            f,
            _t(flow_lang, MSGS["connecting"]),
            team=team,
            esc=True,
        )

    # New / existing qualification (first turns)
    if not flow.get("customer_kind") and step in (
        "awaiting_customer_type",
        "entry",
    ):
        choice = _parse_choice(
            text,
            {
                "1": "new",
                "new": "new",
                "n": "new",
                "2": "existing",
                "existing": "existing",
                "old": "existing",
                "e": "existing",
            },
        )
        if not flow.get("intro_shown"):
            base = {**flow, "intro_shown": True, "step": "awaiting_customer_type", "lang": flow_lang}
            if choice == "new":
                f = {**base, "customer_kind": "new", "step": "new_main_menu"}
                return save(f, _t(flow_lang, MSGS["new_welcome"]))
            if choice == "existing":
                f = {
                    **base,
                    "customer_kind": "existing",
                    "verified": False,
                    "step": "existing_awaiting_verification",
                }
                return save(f, _t(flow_lang, MSGS["verify"]))
            return save(base, _t(flow_lang, MSGS["entry"]))
        if choice == "new":
            f = {**flow, "customer_kind": "new", "step": "new_main_menu", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["new_welcome"]))
        if choice == "existing":
            f = {
                **flow,
                "customer_kind": "existing",
                "verified": False,
                "step": "existing_awaiting_verification",
                "lang": flow_lang,
            }
            return save(f, _t(flow_lang, MSGS["verify"]))
        # Unclear reply (e.g. "hi") — send the fixed entry template again, not generic fallback.
        return save(
            {**flow, "step": "awaiting_customer_type", "lang": flow_lang},
            _t(flow_lang, MSGS["entry"]),
        )

    if step == "existing_awaiting_verification":
        # Placeholder: any non-empty message completes verification
        if len(text) >= 1:
            f = {
                **flow,
                "verified": True,
                "step": "existing_verified_menu",
                "lang": flow_lang,
            }
            return save(f, _t(flow_lang, MSGS["verified_menu"]))
        return save(flow, _t(flow_lang, MSGS["verify"]))

    if step == "existing_verified_menu":
        choice = _parse_choice(text, {"1": "track", "2": "account", "3": "agent"})
        if choice == "track":
            f = {**flow, "step": "existing_awaiting_order_id", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["ask_order"]))
        if choice == "account":
            f = {**flow, "step": "awaiting_agent", "lang": flow_lang}
            return save(
                f,
                _t(flow_lang, MSGS["account_support"]),
                team=TEAM_INTERMEDIATE,
                esc=True,
            )
        if choice == "agent":
            f = {**flow, "step": "existing_awaiting_experience", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["experience"]))
        return save(
            {**flow, "step": "existing_verified_menu", "lang": flow_lang},
            _t(flow_lang, MSGS["verified_menu"]),
        )

    if step == "existing_awaiting_order_id":
        order, _src = await _lookup_order(db, tenant_id, text, store_client)
        if order:
            body = _t(flow_lang, MSGS["order_found"]).format(
                order_id=order["order_number"],
                status=order["status"],
                delivery=order["delivery"],
            )
            f = {**flow, "step": "existing_verified_menu", "lang": flow_lang}
            return save(f, body)
        f = {**flow, "step": "existing_awaiting_order_id", "lang": flow_lang}
        return save(f, _t(flow_lang, MSGS["order_not_found"]))

    if step == "existing_awaiting_experience":
        c2 = _parse_choice(
            text,
            {"1": "beginner", "2": "intermediate", "3": "expert"},
        )
        team_map = {
            "beginner": TEAM_BEGINNER,
            "intermediate": TEAM_INTERMEDIATE,
            "expert": TEAM_EXPERT,
        }
        if c2 in team_map:
            f = {
                **flow,
                "experience_team": team_map[c2],
                "step": "awaiting_agent",
                "lang": flow_lang,
            }
            return save(
                f,
                _t(flow_lang, MSGS["connecting"]),
                team=team_map[c2],
                esc=True,
            )
        return save(
            {**flow, "step": "existing_awaiting_experience", "lang": flow_lang},
            _t(flow_lang, MSGS["experience"]),
        )

    if step == "new_main_menu":
        choice = _parse_choice(text, {"1": "learn", "2": "products", "3": "support"})
        if choice == "learn":
            f = {**flow, "step": "new_main_menu", "lang": flow_lang}
            return ai_forward(
                "[Customer selected: learn about dropshipping — answer from knowledge base, concise.] "
                + text,
                f,
                skip_api=True,
            )
        if choice == "products":
            f = {**flow, "step": "new_main_menu", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["products_hint"]))
        if choice == "support":
            f = {**flow, "step": "awaiting_agent", "lang": flow_lang}
            return save(
                f,
                _t(flow_lang, MSGS["connecting"]),
                team=TEAM_NEW_CUSTOMER,
                esc=True,
            )
        if _looks_like_greeting(text):
            f = {**flow, "step": "new_main_menu", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["new_menu_after_greeting"]))
        # Free-form question → AI, no store API
        f = {**flow, "step": "new_main_menu", "lang": flow_lang}
        return ai_forward(text, f, skip_api=True)

    if step == "awaiting_agent":
        if flow.get("customer_kind") == "existing" and flow.get("verified"):
            nf = {**flow, "step": "existing_verified_menu", "lang": flow_lang}
            return save(nf, _t(flow_lang, MSGS["verified_menu"]), skip_api=False)
        nf = {**flow, "customer_kind": "new", "step": "new_main_menu", "lang": flow_lang}
        return save(nf, _t(flow_lang, MSGS["new_welcome"]), skip_api=True)

    # Unknown step — reset
    f = {"step": "awaiting_customer_type", "intro_shown": False, "lang": flow_lang}
    return save(f, _t(flow_lang, MSGS["entry"]), skip_api=False)
