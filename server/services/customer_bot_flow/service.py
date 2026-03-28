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

BOT_FLOW_KEY = "bot_flow"

# Align with admin agent team labels (Agent.team)
TEAM_NEW_CUSTOMER = "new_customer"
TEAM_BEGINNER = "beginner"
TEAM_INTERMEDIATE = "intermediate"
TEAM_EXPERT = "expert"


def _t(lang: str, table: Dict[str, str]) -> str:
    return table.get(lang) or table.get("english") or next(iter(table.values()))


MSGS = {
    "entry": {
        "roman_urdu": (
            "👋 Salam! Welcome to *Arabia Dropshipping* 🚀\n\n"
            "Aap new customer hain ya existing customer?\n\n"
            "1️⃣ New customer\n"
            "2️⃣ Existing customer\n\n"
            "Reply mein 1 ya 2 likh dein 😊"
        ),
        "english": (
            "👋 Hi! Welcome to *Arabia Dropshipping* 🚀\n\n"
            "Are you a:\n\n"
            "1️⃣ New customer\n"
            "2️⃣ Existing customer\n\n"
            "Please reply with 1 or 2 😊"
        ),
        "arabic": (
            "👋 مرحباً! أهلاً بك في *Arabia Dropshipping* 🚀\n\n"
            "هل أنت:\n\n"
            "1️⃣ عميل جديد\n"
            "2️⃣ عميل حالي\n\n"
            "يرجى الرد بـ 1 أو 2 😊"
        ),
    },
    "new_welcome": {
        "roman_urdu": (
            "✨ Great! Welcome onboard.\n\n"
            "Hum aapki kaise madad kar sakte hain?\n\n"
            "1️⃣ Dropshipping ke baray mein maloomat\n"
            "2️⃣ Products dekhna\n"
            "3️⃣ Support se baat karna\n\n"
            "Aap apna sawal bhi likh sakte hain 💬"
        ),
        "english": (
            "✨ Great! Welcome onboard.\n\n"
            "How can we help you today?\n\n"
            "1️⃣ Learn about dropshipping\n"
            "2️⃣ View products\n"
            "3️⃣ Talk to support\n\n"
            "You can also type your question 💬"
        ),
        "arabic": (
            "✨ رائع! أهلاً بك معنا.\n\n"
            "كيف يمكننا مساعدتك؟\n\n"
            "1️⃣ التعرف على الدروبشيبينغ\n"
            "2️⃣ عرض المنتجات\n"
            "3️⃣ التحدث مع الدعم\n\n"
            "يمكنك أيضاً كتابة سؤالك 💬"
        ),
    },
    "verify": {
        "roman_urdu": (
            "🔐 Apna account verify karne ke liye code enter karein:\n\n"
            "(verification system will be added later — abhi ke liye apna code yahan likh dein.)"
        ),
        "english": (
            "🔐 Please verify your account.\n\n"
            "Enter the verification code sent to you:\n"
            "(Full verification will be enabled soon — for now, send any code to continue.)"
        ),
        "arabic": (
            "🔐 يرجى التحقق من حسابك.\n\n"
            "أدخل رمز التحقق المرسل إليك:\n"
            "(سيتم تفعيل التحقق الكامل لاحقاً — يمكنك إرسال أي رمز للمتابعة الآن.)"
        ),
    },
    "verified_menu": {
        "roman_urdu": (
            "✅ Verified successfully!\n\n"
            "Aap kya karna chahte hain?\n\n"
            "1️⃣ Order track karein 📦\n"
            "2️⃣ Account support\n"
            "3️⃣ Agent se baat karein 👨‍💼"
        ),
        "english": (
            "✅ Verified successfully!\n\n"
            "How can we assist you?\n\n"
            "1️⃣ Track your order 📦\n"
            "2️⃣ Account support\n"
            "3️⃣ Talk to agent 👨‍💼"
        ),
        "arabic": (
            "✅ تم التحقق بنجاح!\n\n"
            "كيف يمكننا مساعدتك؟\n\n"
            "1️⃣ تتبع الطلب 📦\n"
            "2️⃣ دعم الحساب\n"
            "3️⃣ التحدث مع موظف 👨‍💼"
        ),
    },
    "ask_order": {
        "roman_urdu": (
            "📦 Apna Order ID likhein:\n"
            "Example: 123456"
        ),
        "english": (
            "📦 Please enter your Order ID:\n"
            "Example: 123456"
        ),
        "arabic": (
            "📦 يرجى إدخال رقم الطلب:\n"
            "مثال: 123456"
        ),
    },
    "order_found": {
        "roman_urdu": (
            "✅ Order mil gaya!\n\n"
            "📦 Order ID: {order_id}\n"
            "📍 Status: {status}\n"
            "🚚 Delivery: {delivery}\n\n"
            "Shukriya 💙"
        ),
        "english": (
            "✅ Order found!\n\n"
            "📦 Order ID: {order_id}\n"
            "📍 Status: {status}\n"
            "🚚 Delivery: {delivery}\n\n"
            "Thank you 💙"
        ),
        "arabic": (
            "✅ تم العثور على الطلب!\n\n"
            "📦 رقم الطلب: {order_id}\n"
            "📍 الحالة: {status}\n"
            "🚚 التوصيل: {delivery}\n\n"
            "شكراً 💙"
        ),
    },
    "order_not_found": {
        "roman_urdu": (
            "❌ Order nahi mila.\n\n"
            "Dobara check karein ya *support* likhein."
        ),
        "english": (
            "❌ Order not found.\n\n"
            "Please double-check or type *support*."
        ),
        "arabic": (
            "❌ لم يتم العثور على الطلب.\n\n"
            "يرجى التحقق مرة أخرى أو اكتب *support*."
        ),
    },
    "connecting": {
        "roman_urdu": (
            "👨‍💼 Aap ko agent se connect kiya ja raha hai...\n\n"
            "Thori dair intezar karein."
        ),
        "english": (
            "👨‍💼 Connecting you to a support agent...\n\n"
            "Please wait a moment."
        ),
        "arabic": (
            "👨‍💼 جاري توصيلك بموظف الدعم...\n\n"
            "يرجى الانتظار لحظة."
        ),
    },
    "experience": {
        "roman_urdu": (
            "📊 Aap ka dropshipping experience kitna hai?\n\n"
            "1️⃣ Less than 1 year\n"
            "2️⃣ 1–2 years\n"
            "3️⃣ 3+ years"
        ),
        "english": (
            "📊 How much experience do you have in dropshipping?\n\n"
            "1️⃣ Less than 1 year\n"
            "2️⃣ 1–2 years\n"
            "3️⃣ 3+ years"
        ),
        "arabic": (
            "📊 ما مقدار خبرتك في الدروبشيبينغ؟\n\n"
            "1️⃣ أقل من سنة\n"
            "2️⃣ من 1 إلى سنتين\n"
            "3️⃣ أكثر من 3 سنوات"
        ),
    },
    "kb_wrap": {
        "roman_urdu": "💡 Yeh information aap ke liye:\n\n{body}\n\nMazeed madad ke liye *support* likhein 👨‍💼",
        "english": "💡 Here's what you need to know:\n\n{body}\n\nNeed more help? Type *support* 👨‍💼",
        "arabic": "💡 إليك المعلومات:\n\n{body}\n\nلمزيد من المساعدة اكتب *support* 👨‍💼",
    },
    "products_hint": {
        "roman_urdu": (
            "🛍️ Products ke liye hamari website / catalog dekhein (admin se link add karwa sakte hain).\n\n"
            "Aur sawal ho to likhein ya *support* likhein 👨‍💼"
        ),
        "english": (
            "🛍️ Please browse our website / catalog for products (your admin can add a direct link).\n\n"
            "Ask another question or type *support* 👨‍💼"
        ),
        "arabic": (
            "🛍️ يمكنك تصفح موقعنا / الكتالوج للمنتجات (يمكن للمسؤول إضافة رابط).\n\n"
            "اكتب سؤالاً آخر أو *support* 👨‍💼"
        ),
    },
    "account_support": {
        "roman_urdu": (
            "💬 Account support ke liye aap ko specialist se connect kiya ja raha hai...\n\n"
            "Thori dair intezar karein."
        ),
        "english": (
            "💬 Connecting you with account support...\n\n"
            "Please wait a moment."
        ),
        "arabic": (
            "💬 جاري توصيلك بدعم الحساب...\n\n"
            "يرجى الانتظار لحظة."
        ),
    },
    "fallback": {
        "roman_urdu": (
            "🤖 Samajh nahi aaya.\n\n"
            "Please 1 ya 2 select karein ya apna sawal likhein 😊"
        ),
        "english": (
            "🤖 Sorry, I didn't understand that.\n\n"
            "Please choose an option or type your question."
        ),
        "arabic": (
            "🤖 لم أفهم ذلك.\n\n"
            "يرجى اختيار خيار أو كتابة سؤالك."
        ),
    },
}


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
            escalate=await orchestrator.should_escalate(user_message),
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
        return save(
            {**flow, "step": "awaiting_customer_type", "lang": flow_lang},
            _t(flow_lang, MSGS["fallback"]),
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
            _t(flow_lang, MSGS["fallback"]),
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
            _t(flow_lang, MSGS["fallback"]),
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
