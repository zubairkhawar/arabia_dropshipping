"""
Structured onboarding / support flow for customer-facing channels (web, WhatsApp).

State is stored on Conversation.conversation_metadata under key "bot_flow".
Team routing uses Agent.team values: new_customer, beginner, intermediate, expert.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import settings
from models import Conversation, Message, Order
from services.ai_orchestrator_service.services import (
    AIOrchestrator,
    _extract_order_id_from_message,
)
from services.store_integration_service.client import StoreIntegrationClient
from services.human_handoff_intent import (
    is_slash_reset_command,
    solo_menu_digit,
    wants_bot_flow_reset,
    wants_human_agent,
)
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


def _looks_like_free_text_question(text: str) -> bool:
    """
    Detect likely FAQ/free-text requests at the entry step so we don't hard-loop
    on the 1/2 qualifier menu for real questions.
    """
    s = (text or "").strip().lower()
    if not s:
        return False
    if _looks_like_greeting(s):
        return False
    if solo_menu_digit(s):
        return False
    if _parse_choice(
        s,
        {"1": "new", "new": "new", "n": "new", "2": "existing", "existing": "existing", "old": "existing", "e": "existing"},
    ):
        return False
    if "?" in s:
        return True
    faq_markers = (
        "tell me",
        "about",
        "what is",
        "who are",
        "dropship arabia",
        "maloomat",
        "btao",
        "batao",
        "kya",
        "ka btao",
    )
    return any(m in s for m in faq_markers) and len(s) >= 8


def _looks_like_order_status_question(text: str) -> bool:
    """Order / tracking intent while user is still on the new-customer menu."""
    t = (text or "").strip().lower()
    if len(t) < 6:
        return False
    # Ignore obvious FAQ/company-info prompts.
    info_markers = (
        "what is",
        "tell me about",
        "why should i",
        "how does",
        "compare",
        "about dropship",
        "dropship arabia",
        "who are you",
        "services",
    )
    strict_order_markers = (
        "my order",
        "mera order",
        "mere order",
        "order status",
        "track my order",
        "track order",
        "tracking id",
        "where is my order",
        "order id",
        "delivery status",
    )
    # If this looks like an FAQ and has no strict order marker, keep it out of order flow.
    if any(m in t for m in info_markers) and not any(k in t for k in strict_order_markers):
        return False
    if any(k in t for k in strict_order_markers):
        return True

    # Secondary gate: require both order-domain and "asking" intent.
    has_order_domain = any(k in t for k in ("order", "tracking", "track", "parcel", "package"))
    is_asking = ("?" in t) or any(k in t for k in ("where", "when", "status", "kab", "kahan"))
    if has_order_domain and is_asking:
        return True
    return False


def _is_likely_order_id_only(text: str) -> bool:
    s = (text or "").strip()
    if len(s) < 4 or len(s) > 20:
        return False
    return bool(re.fullmatch(r"[\d\-\s#]+", s))


def _is_likely_email(text: str) -> bool:
    s = (text or "").strip().lower()
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s))


def _state_back_to_customer_pick(flow: Dict[str, Any]) -> Dict[str, Any]:
    """Let user choose 2 (existing) for order flow after wrong-path message."""
    return {
        **flow,
        "customer_kind": None,
        "verified": False,
        "step": "awaiting_customer_type",
        "intro_shown": True,
        "experience_team": None,
    }


def _naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _last_customer_message_created_at(db: Session, conversation_id: int) -> Optional[datetime]:
    row = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.sender_type == "customer",
        )
        .order_by(desc(Message.created_at))
        .first()
    )
    return row.created_at if row else None


def _apply_inactivity_bot_reset(
    db: Session,
    conversation: Conversation,
    meta: Dict[str, Any],
    flow: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Clear bot_flow if the last customer message was more than N days ago (0 = disabled)."""
    if flow.get("step") == "awaiting_resume_choice":
        return meta, flow
    days = int(getattr(settings, "customer_bot_inactivity_reset_days", 7) or 0)
    if days <= 0:
        return meta, flow
    last_at = _last_customer_message_created_at(db, conversation.id)
    anchor: Optional[datetime] = last_at or conversation.created_at
    if anchor is None:
        return meta, flow
    if datetime.utcnow() - _naive_utc(anchor) <= timedelta(days=days):
        return meta, flow
    return {**meta, BOT_FLOW_KEY: {}}, {}


def _flow_is_tabula_rasa(flow: Dict[str, Any]) -> bool:
    """True when user is still only on the new/existing entry (no path chosen yet)."""
    if not flow:
        return True
    if flow.get("customer_kind"):
        return False
    step = flow.get("step") or "awaiting_customer_type"
    if step == "awaiting_resume_choice":
        return False
    return step in ("awaiting_customer_type", "entry")


def _parse_choice(text: str, mapping: Dict[str, str]) -> Optional[str]:
    raw = (text or "").strip().lower()
    raw = unicodedata.normalize("NFKC", raw)
    raw = raw.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    raw = re.sub(r"[^\w\u0600-\u06FF\s]", " ", raw)
    parts = raw.split()
    first = parts[0] if parts else ""
    if first in mapping:
        return mapping[first]
    if raw in mapping:
        return mapping[raw]
    digit_keys = [k for k in mapping if len(k) == 1 and k.isdigit()]
    if digit_keys:
        allowed = "".join(sorted(set(digit_keys)))
        d = solo_menu_digit(text, allowed)
        if d and d in mapping:
            return mapping[d]
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
    """
    Returns (order_dict_or_None, source).

    source is one of: \"db\" | \"api\" | \"not_found\" | \"api_error\"
    """
    ref = (order_ref or "").strip()
    if not ref:
        return None, "not_found"

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

    detail: Optional[Dict[str, Any]] = None
    try:
        detail = await store_client.get_order_by_id(ref)
        if not detail:
            detail = await store_client.get_order_by_number(ref)
    except Exception:
        return None, "api_error"

    if not detail:
        return None, "not_found"

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

    meta = _normalize_meta(conversation)
    flow = _get_flow(meta)
    meta, flow = _apply_inactivity_bot_reset(db, conversation, meta, flow)

    lang = await orchestrator.detect_language(user_message)
    if not (user_message or "").strip():
        lang = "roman_urdu"
    sticky = flow.get("lang")
    if isinstance(sticky, str) and sticky.strip():
        t0 = (user_message or "").strip()
        if t0 and (
            len(t0) <= 8
            or bool(re.fullmatch(r"[\d\-\s#]+", t0))
        ):
            lang = sticky
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

    if is_slash_reset_command(text):
        nf = {"step": "awaiting_customer_type", "intro_shown": False, "lang": flow_lang}
        return save(nf, _t(flow_lang, MSGS["entry"]), skip_api=False)

    if step == "awaiting_resume_choice":
        snap = flow.get("resume_snapshot")
        if not isinstance(snap, dict):
            snap = {}
        choice = _parse_choice(
            text,
            {
                "1": "continue",
                "2": "fresh",
                "continue": "continue",
                "c": "continue",
                "resume": "continue",
                "fresh": "fresh",
                "new": "fresh",
                "restart": "fresh",
                "start fresh": "fresh",
                "start over": "fresh",
            },
        )
        if choice == "continue":
            restored = {**snap}
            restored.pop("resume_snapshot", None)
            restored["lang"] = flow_lang
            return save(restored, _t(flow_lang, MSGS["resume_continued"]))
        if choice == "fresh":
            nf = {"step": "awaiting_customer_type", "intro_shown": False, "lang": flow_lang}
            return save(nf, _t(flow_lang, MSGS["entry"]), skip_api=False)
        return save(flow, _t(flow_lang, MSGS["welcome_back"]))

    # Clear stale WhatsApp/web bot state (e.g. old "verified" session) — before handoff
    if wants_bot_flow_reset(text):
        nf = {"step": "awaiting_customer_type", "intro_shown": False, "lang": flow_lang}
        return save(nf, _t(flow_lang, MSGS["entry"]), skip_api=False)

    # Global handoff: any step (incl. verification) when user asks for a human agent
    if wants_human_agent(text):
        kind = flow.get("customer_kind")
        exp_team = flow.get("experience_team")
        if kind == "new" or not kind:
            team = TEAM_NEW_CUSTOMER
        else:
            team = exp_team or TEAM_BEGINNER
        f = {
            **flow,
            "step": "awaiting_agent",
            "intro_shown": True,
            "pending_handoff_team": team,
        }
        return save(
            f,
            _t(flow_lang, MSGS["connecting"]),
            team=team,
            esc=True,
        )

    # Sets step awaiting_resume_choice; reply uses MSGS["welcome_back"] from templates.
    if not _flow_is_tabula_rasa(flow) and _looks_like_greeting(text):
        snap = {k: v for k, v in flow.items() if k != "resume_snapshot"}
        wb: Dict[str, Any] = {
            "step": "awaiting_resume_choice",
            "intro_shown": True,
            "lang": flow_lang,
            "resume_snapshot": snap,
        }
        return save(wb, _t(flow_lang, MSGS["welcome_back"]))

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
                    "step": "existing_awaiting_email",
                }
                return save(f, _t(flow_lang, MSGS["ask_email"]))
            if _looks_like_free_text_question(text):
                f = {**base, "step": "awaiting_customer_type"}
                return ai_forward("[Customer entry question] " + text, f, skip_api=True)
            return save(base, _t(flow_lang, MSGS["entry"]))
        if choice == "new":
            f = {**flow, "customer_kind": "new", "step": "new_main_menu", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["new_welcome"]))
        if choice == "existing":
            f = {
                **flow,
                "customer_kind": "existing",
                "verified": False,
                "step": "existing_awaiting_email",
                "lang": flow_lang,
            }
            return save(f, _t(flow_lang, MSGS["ask_email"]))
        if _looks_like_free_text_question(text):
            f = {**flow, "step": "awaiting_customer_type", "intro_shown": True, "lang": flow_lang}
            return ai_forward("[Customer entry question] " + text, f, skip_api=True)
        # Unclear reply (e.g. "hi") — send the fixed entry template again, not generic fallback.
        return save(
            {**flow, "step": "awaiting_customer_type", "lang": flow_lang},
            _t(flow_lang, MSGS["entry"]),
        )

    if step == "existing_awaiting_email":
        email = (text or "").strip().lower()
        if not _is_likely_email(email):
            return save(flow, _t(flow_lang, MSGS["email_invalid"]))
        sent = await store_client.send_verification_code(email)
        if not sent:
            return save(flow, _t(flow_lang, MSGS["verify_send_error"]))
        f = {
            **flow,
            "pending_email": email,
            "verified": False,
            "step": "existing_awaiting_verification_code",
            "lang": flow_lang,
        }
        return save(f, _t(flow_lang, MSGS["code_sent"]))

    if step == "existing_awaiting_verification_code":
        code = (text or "").strip()
        pending_email = (flow.get("pending_email") or "").strip().lower()
        if not pending_email:
            f = {
                **flow,
                "step": "existing_awaiting_email",
                "lang": flow_lang,
            }
            return save(f, _t(flow_lang, MSGS["ask_email"]))
        if len(code) < 4:
            return save(flow, _t(flow_lang, MSGS["verify"]))
        verified = await store_client.verify_code(pending_email, code)
        if not verified:
            return save(flow, _t(flow_lang, MSGS["verify_invalid_code"]))
        f = {
            **flow,
            "verified": False,
            "step": "existing_awaiting_mobile",
            "lang": flow_lang,
        }
        return save(f, _t(flow_lang, MSGS["ask_mobile"]))

    if step == "existing_awaiting_mobile":
        pending_email = (flow.get("pending_email") or "").strip().lower()
        mobile = (text or "").strip()
        if not pending_email:
            f = {
                **flow,
                "step": "existing_awaiting_email",
                "lang": flow_lang,
            }
            return save(f, _t(flow_lang, MSGS["ask_email"]))
        if len(mobile) < 7:
            return save(flow, _t(flow_lang, MSGS["ask_mobile"]))
        customer = await store_client.get_customer_by_email_mobile(pending_email, mobile)
        if not customer:
            return save(flow, _t(flow_lang, MSGS["customer_not_found_after_verify"]))
        f = {
            **flow,
            "verified": True,
            "step": "existing_verified_menu",
            "verified_customer": customer,
            "seller_id": customer.get("seller_id"),
            "pending_mobile": mobile,
            "lang": flow_lang,
        }
        return save(f, _t(flow_lang, MSGS["verified_menu"]))

    if step == "existing_verified_menu":
        choice = _parse_choice(text, {"1": "track", "2": "details", "3": "support"})
        if choice == "track":
            f = {**flow, "step": "existing_awaiting_order_id", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["ask_order"]))
        if choice == "details":
            f = {**flow, "step": "existing_awaiting_order_id", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["ask_order"]))
        if choice == "support":
            f = {**flow, "step": "existing_awaiting_experience", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["experience"]))
        if _looks_like_order_status_question(text) or _is_likely_order_id_only(text):
            ref = ""
            if _is_likely_order_id_only(text):
                ref = re.sub(r"[^\d\-#]", "", (text or "").strip()) or (text or "").strip()
            else:
                ref = (_extract_order_id_from_message(text, phone) or "").strip()
            if ref:
                order, src = await _lookup_order(db, tenant_id, ref, store_client)
                if order:
                    body = _t(flow_lang, MSGS["order_found"]).format(
                        order_id=order["order_number"],
                        status=order["status"],
                        delivery=order["delivery"],
                    )
                    f = {**flow, "step": "existing_verified_menu", "lang": flow_lang}
                    return save(f, body)
                if src == "api_error":
                    f = {**flow, "step": "existing_verified_menu", "lang": flow_lang}
                    return save(f, _t(flow_lang, MSGS["order_lookup_error"]))
                f = {**flow, "step": "existing_verified_menu", "lang": flow_lang}
                return save(f, _t(flow_lang, MSGS["order_not_found"]))
            f = {**flow, "step": "existing_awaiting_order_id", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["ask_order"]))
        if _looks_like_greeting(text):
            f = {**flow, "step": "existing_verified_menu", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["verified_menu"]))
        f = {**flow, "step": "existing_verified_menu", "lang": flow_lang}
        return ai_forward("[Customer question] " + text, f, skip_api=True)

    if step == "existing_awaiting_order_id":
        raw = (text or "").strip()
        ref = raw if _is_likely_order_id_only(raw) else (_extract_order_id_from_message(raw, phone) or raw)
        order, src = await _lookup_order(db, tenant_id, ref, store_client)
        if order:
            body = _t(flow_lang, MSGS["order_found"]).format(
                order_id=order["order_number"],
                status=order["status"],
                delivery=order["delivery"],
            )
            f = {**flow, "step": "existing_verified_menu", "lang": flow_lang}
            return save(f, body)
        f = {**flow, "step": "existing_awaiting_order_id", "lang": flow_lang}
        if src == "api_error":
            return save(f, _t(flow_lang, MSGS["order_lookup_error"]))
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
            routed = team_map[c2]
            f = {
                **flow,
                "experience_team": routed,
                "step": "awaiting_agent",
                "lang": flow_lang,
                "pending_handoff_team": routed,
            }
            return save(
                f,
                _t(flow_lang, MSGS["connecting"]),
                team=routed,
                esc=True,
            )
        return save(
            {**flow, "step": "existing_awaiting_experience", "lang": flow_lang},
            _t(flow_lang, MSGS["experience"]),
        )

    if step == "new_main_menu":
        choice = _parse_choice(text, {"1": "products", "2": "info", "3": "support"})
        if choice == "products":
            f = {**flow, "step": "new_main_menu", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["products_hint"]))
        if choice == "info":
            f = {**flow, "step": "new_main_menu", "lang": flow_lang}
            return ai_forward(
                "[Customer selected: get information — answer from knowledge base, concise.] "
                + text,
                f,
                skip_api=True,
            )
        if choice == "support":
            f = {
                **flow,
                "step": "awaiting_agent",
                "lang": flow_lang,
                "pending_handoff_team": TEAM_NEW_CUSTOMER,
            }
            return save(
                f,
                _t(flow_lang, MSGS["connecting"]),
                team=TEAM_NEW_CUSTOMER,
                esc=True,
            )
        # FAQ/info questions should be answered directly from KB in new customer flow.
        if _looks_like_free_text_question(text):
            f = {**flow, "step": "new_main_menu", "lang": flow_lang}
            return ai_forward(text, f, skip_api=True)
        if _looks_like_order_status_question(text) or _is_likely_order_id_only(text):
            f = _state_back_to_customer_pick(flow)
            return save(
                f,
                _t(flow_lang, MSGS["new_customer_order_use_existing_flow"]),
            )
        if _looks_like_greeting(text):
            f = {**flow, "step": "new_main_menu", "lang": flow_lang}
            return save(f, _t(flow_lang, MSGS["new_menu_after_greeting"]))
        # Free-form question → AI, no store API
        f = {**flow, "step": "new_main_menu", "lang": flow_lang}
        return ai_forward(text, f, skip_api=True)

    if step == "awaiting_agent":
        if flow.get("customer_kind") == "existing" and flow.get("verified"):
            team = (
                flow.get("pending_handoff_team")
                or flow.get("experience_team")
                or TEAM_BEGINNER
            )
            f = {
                **flow,
                "step": "awaiting_agent",
                "lang": flow_lang,
                "pending_handoff_team": team,
            }
            return save(
                f,
                _t(flow_lang, MSGS["handoff_retry"]),
                team=team,
                esc=True,
                skip_api=False,
            )
        if flow.get("customer_kind") == "new":
            team = flow.get("pending_handoff_team") or TEAM_NEW_CUSTOMER
            f = {
                **flow,
                "customer_kind": "new",
                "step": "awaiting_agent",
                "lang": flow_lang,
                "pending_handoff_team": team,
            }
            return save(
                f,
                _t(flow_lang, MSGS["handoff_retry"]),
                team=team,
                esc=True,
                skip_api=True,
            )
        nf = {"step": "awaiting_customer_type", "intro_shown": False, "lang": flow_lang}
        return save(nf, _t(flow_lang, MSGS["entry"]), skip_api=False)

    # Unknown step — reset
    f = {"step": "awaiting_customer_type", "intro_shown": False, "lang": flow_lang}
    return save(f, _t(flow_lang, MSGS["entry"]), skip_api=False)
