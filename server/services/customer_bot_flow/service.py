"""
Structured onboarding / support flow for customer-facing channels (web, WhatsApp).

State is stored on Conversation.conversation_metadata under key "bot_flow".
Team routing uses Agent.team values: new_customer, beginner, intermediate, expert.
"""
from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import get_openai_api_key, settings
from langchain_bot.prompts import strip_followup_block_when_disabled
from models import Conversation, Message, Order, TenantSchedule
from services.ai_orchestrator_service.services import (
    AIOrchestrator,
    _extract_order_id_from_message,
)
from services.order_date_range import (
    parse_date_range_from_message as _parse_date_range,
    looks_like_orders_in_period_message,
)
from services.phone_lookup_variants import normalize_mobile_for_flow
from services.store_integration_service.client import (
    StoreIntegrationClient,
    merchant_seller_scope_from_row,
    synthetic_order_stub_from_invoices,
    _orders_list_date_window,
)
from services.trending_products_service.bot_query import (
    get_trending_product_by_id,
    list_active_non_trending_for_country,
    list_active_trending_for_country,
)
from services.human_handoff_intent import (
    is_conversational_acknowledgment,
    is_slash_reset_command,
    solo_menu_digit,
    wants_bot_flow_reset,
    wants_human_agent,
)
from services.customer_bot_flow.templates import BOT_FLOW_TEMPLATES
from services.intent_detector import IntentDetector
from services.memory_service import ConversationMemory, normalize_memory_scope_id
from services.customer_bot_flow.trending_llm_runner import (
    TrendingLLMResult,
    memory_to_flow_patch,
    run_trending_llm,
)
from services.tenant_schedule_text import (
    format_tenant_schedule_for_customer,
    format_tenant_schedule_line_for_handoff,
)
try:
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:  # pragma: no cover — older langchain pin
    from langchain.schema import HumanMessage, SystemMessage

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


def _memory_apply_entities(mem_id: Optional[str], text: str) -> None:
    if not mem_id or not (text or "").strip():
        return
    oid = IntentDetector.extract_order_id(text)
    if oid:
        ConversationMemory.store_extracted_entity(mem_id, "order_id", oid, 0.95, "regex")
    ctry = IntentDetector.extract_country(text)
    if ctry:
        ConversationMemory.store_extracted_entity(mem_id, "country", ctry, 0.9, "keyword")
    pid = IntentDetector.extract_product_id(text)
    if pid:
        ConversationMemory.store_extracted_entity(mem_id, "product_id", pid, 0.85, "regex")
    _topic, _intent = IntentDetector.detect_topic_and_intent(text)
    if _intent and _intent != "general_question":
        ConversationMemory.store_last_intent(mem_id, _intent)


def _memory_store_pending_entry_menu(mem_id: Optional[str], text: str) -> None:
    """Remember topic keywords before new/existing clarifying reply."""
    if not mem_id:
        return
    t = (text or "").strip()
    tl = t.lower()
    if tl in {"1", "2", "n", "e", "y", "yes", "no", "haan", "nahi", "ji"}:
        return
    if len(t) < 2:
        return
    topic, intent_type = IntentDetector.detect_topic_and_intent(t)
    if intent_type in ("general_question", "escalation"):
        return
    if intent_type == "verification" and "existing" not in tl and "verify" not in tl:
        return
    ConversationMemory.store_pending_intent(
        mem_id,
        topic or "general",
        intent_type,
        t,
        confidence=0.8,
    )


def _memory_pending_ai_prefix(mem_id: Optional[str]) -> str:
    if not mem_id:
        return ""
    p = ConversationMemory.get_pending_intent(mem_id)
    if not p:
        return ""
    return (
        "[Customer memory: They asked about "
        f"{p.get('topic')} ({p.get('intent_type')}) earlier. "
        f"Original message: {p.get('original_question', '')}. "
        "Answer that topic first, helpfully and accurately.]\n\n"
    )

BOT_FLOW_KEY = "bot_flow"

# Verbatim copy from templates module (never composed by the LLM).
MSGS = BOT_FLOW_TEMPLATES

# Align with admin agent team labels (Agent.team)
TEAM_NEW_CUSTOMER = "new_customer"
TEAM_BEGINNER = "beginner"
TEAM_INTERMEDIATE = "intermediate"
TEAM_EXPERT = "expert"

# Verbatim copy previously under BOT_FLOW_TEMPLATES; lives here so templates stay slimmer.
_RESUME_CHOICE_MSGS: Dict[str, str] = {
    "english": (
        "Welcome back! Would you like to continue where we left off or start fresh?\n\n"
        "1️⃣ Continue\n"
        "2️⃣ Start fresh"
    ),
    "arabic": (
        "مرحبًا بعودتك! هل تريد المتابعة من حيث توقفت أم البدء من جديد؟\n\n"
        "1️⃣ متابعة\n"
        "2️⃣ البدء من جديد"
    ),
    "roman_urdu": (
        "Welcome back! Aap wahan se continue karna chahte hain jahan chhore the, ya naye siray se?\n\n"
        "1️⃣ Continue\n"
        "2️⃣ Start fresh"
    ),
}
_RESUME_CONTINUED_MSGS: Dict[str, str] = {
    "english": "Great — we'll pick up where you left off. 👍",
    "arabic": "تمام — سنكمل من حيث توقفنا. 👍",
    "roman_urdu": "Theek hai — jahan se chhore the wahan se continue karte hain. 👍",
}
_AGENT_SCHEDULE_UNKNOWN_MSGS: Dict[str, str] = {
    "english": (
        "We do not have a published human-agent schedule in the system yet. "
        'Type "agent" or "support" to request a human, or reply **1** for new / **2** for existing.'
    ),
    "arabic": (
        'لا يوجد جدول دعم بشري محدد في النظام بعد. '
        'اكتب "agent" أو "support" لطلب موظف، أو **1** للجديد / **2** للحالي.'
    ),
    "roman_urdu": (
        "Abhi system mein human agents ka schedule save nahi mila. "
        '"agent" ya "support" likhein, ya **1** new / **2** existing ke liye.'
    ),
}


def _t(lang: str, table: Dict[str, str]) -> str:
    return table.get(lang) or table.get("english") or next(iter(table.values()))


def _is_agency_topic(text: str) -> bool:
    """Return True when the reply body is about the Agency Partnership Program."""
    t = (text or "").lower()
    return bool(
        re.search(r"\bagency\b", t)
        or re.search(r"\bpartnership\s+program\b", t)
        or re.search(r"\bcommission\b", t)
        or re.search(r"\breferral\b", t)
        or re.search(r"\bagent\s+partner\b", t)
        or "agency.arabiadropship" in t
    )


def format_kb_reply(lang: str, ai_body: str, source: Optional[str] = None) -> str:
    """Wrap a knowledge/AI answer (KB turns). Source line is always the public website in templates."""
    body = (ai_body or "").strip()
    # Strip source/footer lines the LLM may have copied from conversation history
    body = re.sub(r"\n*📌[^\n]*", "", body).strip()
    body = re.sub(r'\n*(?:Type "support"|Or type "support"|"support" likhein|اكتب "support"|أو اكتب "support")[^\n]*', "", body, flags=re.IGNORECASE).strip()
    body = re.sub(r"\n*(?:If you need more information|You can also visit|Agar aapko mazeed|Aap hamari website|إذا كنت بحاجة|يمكنك أيضاً زيارة)[^\n]*", "", body, flags=re.IGNORECASE).strip()
    # Strip LLM-generated "contact support" / "raabta karein" closings that duplicate the footer
    body = re.sub(r"\n*(?:.*?customer support se raabta.*|.*?support se raabta.*|.*?contact (?:our )?(?:customer )?support.*|.*?reach out to (?:our )?(?:customer )?support.*|.*?hamari support team.*|.*?support team se.*)", "", body, flags=re.IGNORECASE).strip()
    # Strip "feel free to ask" / "befikr hokar poochein" type closings from LLM
    body = re.sub(r"\n*(?:.*?feel free to (?:ask|reach|contact).*|.*?befikr hokar pooch.*|.*?mazeed sawalat.*pooch.*)", "", body, flags=re.IGNORECASE).strip()
    # Strip agency link if LLM already included it (the footer will add it properly)
    body = re.sub(r"\n*(?:.*?agency\.arabiadropship\.com[^\n]*)", "", body, flags=re.IGNORECASE).strip()
    body = strip_followup_block_when_disabled(body)
    # Follow-up block often ends with a generic "anything else?" line; kb_wrap repeats that intent.
    body = re.sub(
        r"\n{1,3}(?:"
        r"Is there anything else I can help(?: you)? with\??|"
        r"Anything else I can help(?: you)? with\??|"
        r"Let me know if (?:you need|there's) anything else[^\n.]*\.?|"
        r"Kya aur koi madad chahiye\??|"
        r"Aur kuch madad chahiye\??|"
        r"هل هناك أي شيء آخر (?:يمكنني|أستطيع) (?:المساعدة|مساعدتك)[^\n]*\??|"
        r"هل يمكنني مساعدتك في أي شيء آخر[^\n]*\??"
        r")\s*$",
        "",
        body,
        flags=re.IGNORECASE,
    ).strip()
    if not body:
        return body
    template_key = "kb_wrap_agency" if _is_agency_topic(body) else "kb_wrap"
    return _t(lang, MSGS[template_key]).format(body=body)


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
    # One-shot flag: first customer turn after agent closed chat (LLM handover context).
    out.pop("awaiting_first_customer_after_agent_close", None)
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
    # Roman Urdu / Urdu greetings (substring match)
    if any(
        x in blob
        for x in (
            "salam",
            "salaam",
            "sallam",
            "assalam",
            "asslam",
            "alaikum",
            "alikum",
            "walaikum",
            "walaykum",
            "walikum",
            "adab",
            "adaab",
        )
    ):
        return True
    # English exact-match greetings
    if blob in (
        "hi", "hey", "hello", "hi there", "hey there", "hello there",
        "hiya", "howdy", "yo", "greetings", "morning",
        "namaste", "sat sri akal",
        "aoa", "wsalam",
        "whatsup", "wassup", "whats up", "what's up", "whazzup",
        "sup",
    ):
        return True
    # Roman Urdu short greeting phrases
    if blob in ("kya haal hai", "kaise ho", "kya haal", "kaise hain"):
        return True
    if re.match(r"^good (morning|evening|afternoon|night)$", blob):
        return True
    # Arabic script greetings
    if any("\u0600" <= ch <= "\u06FF" for ch in s) and len(tokens) <= 4:
        if any(
            w in blob
            for w in (
                "marhaba", "مرحب", "السلام", "سلام",
                "آداب", "وعلیکم", "ہیلو", "صبح بخیر", "شب بخیر",
            )
        ):
            return True
    return False


def _is_natural_language(text: str) -> bool:
    """True when the input is clearly a sentence/question, not structured data (email/code/phone)."""
    s = (text or "").strip()
    if len(s) < 8:
        return False
    words = s.split()
    if len(words) < 3:
        return False
    alpha = sum(1 for c in s if c.isalpha() or "\u0600" <= c <= "\u06FF")
    return alpha > len(s) * 0.4


def _conversation_bail_from_trending(flow: Dict[str, Any], lang: str) -> Dict[str, Any]:
    nf = {**flow, "step": "conversational", "lang": lang}
    for k in TRENDING_STATE_KEYS:
        nf.pop(k, None)
    return nf


def _wants_new_customer_path(text: str) -> bool:
    """Detect when a customer says 'I'm new / I don't want to verify / skip verification'."""
    s = (text or "").strip().lower()
    s = re.sub(r"[^\w\u0600-\u06FF\s]", " ", s)
    markers = (
        "new customer", "i am new", "i m new", "im new",
        "naya customer", "naye customer", "new hoon", "new hon",
        "mein new", "main new",
        "don't want to verify", "dont want to verify",
        "skip verification", "no verification",
        "verification nhi", "verify nhi", "verification nahi", "verify nahi",
    )
    return any(m in s for m in markers)


def _wants_existing_customer_path(text: str) -> bool:
    """Detect when a customer says they already have an account / are not new."""
    s = (text or "").strip().lower()
    s = re.sub(r"[^\w\u0600-\u06FF\s]", " ", s)
    markers = (
        "existing customer",
        "i am existing",
        "i m existing",
        "im existing",
        "already customer",
        "already a customer",
        "old customer",
        "returning customer",
        "purana customer",
        "pehle se customer",
        "pehle se hun",
        "pehle se hoon",
        "account hai",
        "mera account",
        "not new",
        "not a new",
        "naya customer nahi",
        "naya customer nhi",
        "naya nahi",
        "naya nhi",
        "naye customer nahi",
        "new customer nahi",
        "new customer nhi",
        "mein naya customer nahi",
        "main naya customer nahi",
        "mein naya nahi",
        "main naya nahi",
    )
    return any(m in s for m in markers)


def _script_verification_bypassed() -> bool:
    return bool(getattr(settings, "customer_bot_bypass_script_verification", False))


def _extract_standalone_email(text: str) -> Optional[str]:
    """Single-token email or trailing email after one short word (e.g. 'email x@y.com')."""
    raw = (text or "").strip()
    if not raw:
        return None
    parts = raw.split()
    if len(parts) == 1 and _is_likely_email(parts[0]):
        return parts[0].strip().lower()
    if len(parts) == 2 and _is_likely_email(parts[1]):
        return parts[1].strip().lower()
    return None


def _existing_identity_entry(
    flow: Dict[str, Any],
    flow_lang: str,
    *,
    verify_reason: Optional[str],
    pending_order_ref: Optional[str],
    intro_key: str,
) -> Tuple[Dict[str, Any], str]:
    """
    Start existing-customer identity: full verification script, or order-number-only when bypassed.
    """
    if _script_verification_bypassed():
        return (
            {
                **flow,
                "step": "existing_awaiting_order_id",
                "customer_kind": "existing",
                "intro_shown": True,
                "verify_reason": None,
                "pending_order_ref": pending_order_ref or None,
            },
            _t(flow_lang, MSGS["order_verify_bypass_intro"]),
        )
    return (
        {
            **flow,
            "step": "existing_awaiting_email",
            "customer_kind": "existing",
            "intro_shown": True,
            "verify_reason": verify_reason,
            "pending_order_ref": pending_order_ref or None,
        },
        _t(flow_lang, MSGS[intro_key]),
    )


def _bail_to_conversational(flow: Dict[str, Any], flow_lang: str) -> Dict[str, Any]:
    """Clear verification state and return to conversational step."""
    return {
        **flow,
        "step": "conversational",
        "pending_email": None,
        "pending_mobile": None,
        "verify_reason": None,
        "pending_order_ref": None,
        "lang": flow_lang,
    }


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
    if solo_menu_digit(s, "12"):
        return False
    if _parse_choice(
        s,
        {"1": "new", "new": "new", "n": "new", "2": "existing", "existing": "existing", "old": "existing", "e": "existing"},
    ):
        return False
    if "?" in s:
        return True
    # Topic keywords the customer can ask about without needing new/existing selection.
    # Includes Arabia service topics and common FAQ entry points.
    topic_keywords = (
        "dropshipping", "dropship", "fulfillment", "fulfilment",
        "3pl", "courier", "whatsapp order", "agency", "partnership",
        "profit", "payment", "commission", "sourcing", "china sourcing",
        "store creation", "store setup", "marketing", "shipping",
        "return", "refund", "policy", "policies", "price", "pricing",
        "services", "service", "how", "help", "support",
        "register", "sign up", "start", "begin",
        # Urdu/Roman Urdu topic starters
        "kya hai", "kya hota", "service", "charges", "fee", "cost",
    )
    if any(s == kw or s.startswith(kw) for kw in topic_keywords):
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


def _deterministic_kb_answer(text: str, lang: str) -> Optional[str]:
    """
    High-confidence FAQ overrides for critical business facts.
    Returns a plain answer body (without kb_wrap footer) or None.
    """
    t = (text or "").strip().lower()
    if not t:
        return None

    def _contains_any(*parts: str) -> bool:
        return any(p in t for p in parts)

    # Intent priority: confirmation topics MUST win over country coverage.
    confirmation_markers = (
        "confirmation", "confirm", "order confirm", "confirm service",
        "call confirmation", "whatsapp confirmation", "order confirmation",
    )
    asks_confirmation = _contains_any(*confirmation_markers)
    asks_confirmation_service = asks_confirmation and _contains_any(
        "service", "charges", "charge", "facility", "timing", "proof", "transparent",
        "whatsapp", "activate", "activated", "activation", "karwa", "karwaen", "karwain",
    )
    asks_confirmation_charges = asks_confirmation and _contains_any(
        "charges", "charge", "rate", "pricing", "per order", "cost", "kia charges", "kia charge"
    )
    if asks_confirmation_charges:
        if lang == "english":
            return (
                "Arabia WhatsApp Order Confirmation charges are: UAE = 1 AED per order, KSA = 2 SAR per order "
                "(whether confirmed or canceled). Pakistan does not currently have this confirmation service."
            )
        if lang == "arabic":
            return (
                "رسوم خدمة تأكيد الطلبات عبر واتساب هي: الإمارات 1 درهم لكل طلب، والسعودية 2 ريال لكل طلب "
                "(سواء تم التأكيد أو الإلغاء). هذه الخدمة غير متاحة حاليا في باكستان."
            )
        return (
            "Arabia WhatsApp order confirmation charges: UAE mein 1 AED per order, KSA mein 2 SAR per order "
            "(confirm ya cancel dono surat mein). Pakistan mein filhaal yeh confirmation service available nahi hai."
        )

    asks_activate_confirmation = asks_confirmation and _contains_any(
        "activate", "activated", "activation", "activate kar", "activate karwa",
        "karwaen", "karwain", "kese activated", "kaise activated",
        "service kese", "service kesy", "service kaise", "confirmation service kese",
        "confirmation service kesy", "confirmation service kaise",
        "on karna", "start karna", "shuru karna", "tarika", "tareeqa", "process",
    )
    if asks_activate_confirmation:
        if lang == "english":
            return "To activate Order Confirmation service, please contact Customer Support. They will guide you through activation. No separate upfront activation payment step is required."
        if lang == "arabic":
            return "لتفعيل خدمة تأكيد الطلبات، يرجى التواصل مع فريق دعم العملاء. سيقومون بإرشادك لخطوات التفعيل، ولا توجد خطوة دفع مبدئية منفصلة للتفعيل."
        return "Confirmation service activate karwane ke liye Customer Support se rabta karein. Team aapko activation process guide karegi. Is ke liye koi alag upfront activation payment step required nahi hota."

    asks_reliability = _contains_any("reliable", "bharosa", "trust", "trusted", "authentic")
    if asks_reliability and _contains_any("arabia"):
        if lang == "english":
            return "Yes, Arabia Dropship is reliable. It has delivered 10M+ COD orders, serves 12K+ sellers, and reports 98.4% on-time dispatch with 12+ courier partners."
        if lang == "arabic":
            return "نعم، Arabia Dropship منصة موثوقة. تم تسليم أكثر من 10 ملايين طلب COD، وتخدم أكثر من 12 ألف بائع، مع معدل شحن في الوقت المحدد 98.4% عبر أكثر من 12 شركة شحن."
        return "Ji, Arabia Dropship reliable hai. Platform ne 10M+ COD orders deliver kiye hain, 12K+ sellers ko serve karta hai, aur 98.4% on-time dispatch rate report karta hai (12+ courier partners ke sath)."

    asks_confirmation_timing = _contains_any("confirmation timing", "kitny time", "kitne time", "3 attempt", "3 attempts", "how many attempts")
    asks_confirmation_proof = _contains_any("proof", "screenshot", "transparent", "transparency", "koi proof", "call confirmation", "whatsapp confirmation")
    if asks_confirmation and (asks_confirmation_timing or asks_confirmation_proof):
        if lang == "english":
            return (
                "Arabia confirms orders via WhatsApp (not phone calls). A total of 3 confirmation attempts are made at different times, "
                "and each attempt is documented with screenshot proof for transparency. You can view the proof in your dashboard under Orders > Order Confirmation."
            )
        if lang == "arabic":
            return (
                "تتم عملية تأكيد الطلبات عبر واتساب (وليس مكالمات هاتفية). يتم إجراء 3 محاولات في أوقات مختلفة، "
                "وكل محاولة موثقة بلقطة شاشة لضمان الشفافية. ويمكنك مشاهدة الإثبات من لوحة التحكم: الطلبات > تأكيد الطلب."
            )
        return (
            "Arabia order confirmation WhatsApp ke zariye hoti hai (phone call se nahi). Total 3 attempts mukhtalif times par ki jati hain, "
            "aur har attempt ka screenshot proof upload hota hai transparency ke liye. Proof dashboard mein Orders > Order Confirmation section mein milta hai."
        )

    if asks_confirmation_service:
        if lang == "english":
            return "Arabia provides WhatsApp Order Confirmation service in UAE and KSA. Pakistan market does not currently have this service."
        if lang == "arabic":
            return "تقدم Arabia خدمة تأكيد الطلبات عبر واتساب في الإمارات والسعودية. هذه الخدمة غير متاحة حاليا في سوق باكستان."
        return "Arabia WhatsApp order confirmation service UAE aur KSA mein deta hai. Pakistan market mein yeh service filhaal available nahi hai."

    asks_countries = (
        _contains_any("kitny countr", "kitne countr", "which countr", "market coverage", "active countries")
        or (_contains_any("uae", "ksa", "pak", "pakistan", "qatar") and _contains_any("active", "work", "service", "operate"))
    )
    if asks_countries:
        if lang == "english":
            return (
                "Arabia Dropship is currently active in 3 countries: UAE, Saudi Arabia (KSA), and Pakistan. "
                "Qatar is the 4th market and is coming soon."
            )
        if lang == "arabic":
            return (
                "تعمل Arabia Dropship حاليا بشكل نشط في 3 دول: الإمارات، السعودية (KSA)، وباكستان. "
                "أما قطر فهي السوق الرابع وقريبا سيتم تشغيلها."
            )
        return (
            "Arabia Dropship abhi 3 countries mein active kaam kar raha hai: UAE, KSA aur Pakistan. "
            "Qatar 4th market hai jo jald operational ho jayegi."
        )

    return None


def _looks_like_order_status_question(text: str) -> bool:
    """Order / tracking intent while user is still on the new-customer menu."""
    t = (text or "").strip().lower()
    if len(t) < 6:
        return False

    # ── Policy / FAQ / hypothetical patterns ──
    # These mention "order" in a general/hypothetical sense, NOT "check MY specific order."
    # They take priority over everything else — if the message is clearly a policy
    # question we must NOT route to verification regardless of other markers.
    policy_markers = (
        "does arabia",
        "do arabia",
        "arabia provide",
        "compensation",
        "penalty",
        "any reason",
        "for any reason",
        "if my order is not",
        "if order is not",
        "if the order",
        "if an order",
        "not shipped",
        "not delivered",
        "cancel policy",
        "cancellation",
        "return policy",
        "return charges",
        "refund policy",
        "refund",
        "shipping policy",
        "shipping cost",
        "how long does",
        "how much",
        "how many days",
        "kitne din",
        "policy",
        "commission",
        "protection",
        "guarantee",
        "seller protection",
        "seller invoice",
        # Roman Urdu policy patterns
        "kya arabia",
        "arabia kya",
        "kya hota hai",
        "kya milta",
        "kaise hota",
        "agar order",
        "agar mera order",
    )
    if any(m in t for m in policy_markers):
        return False

    # ── General FAQ / info prompts ──
    info_markers = (
        "what is",
        "what markets",
        "which markets",
        "operate in",
        "do i need",
        "do i have to",
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
        "my orders",
        "mera order",
        "mere order",
        "mere orders",
        "meray order",
        "order status",
        "order details",
        "order detail",
        "order info",
        "order information",
        "orders details",
        "orders detail",
        "order ki detail",
        "order ki tafseel",
        "track my order",
        "track order",
        "tracking id",
        "where is my order",
        "order id",
        "delivery status",
        # Asking intent with "order" → "i want/need/show my order(s)..."
        "want order",
        "want my order",
        "want to see my order",
        "need order",
        "show order",
        "show my order",
        "show me order",
        "show me my order",
        "give me order",
        "give my order",
        "get my order",
        "check my order",
        "check order",
        "view my order",
        "view order",
    )
    # If this looks like an FAQ and has no strict order marker, keep it out of order flow.
    if any(m in t for m in info_markers) and not any(k in t for k in strict_order_markers):
        return False
    if any(k in t for k in strict_order_markers):
        return True
    # "order 185196", "order #185196" — user gives the id inline without
    # "order id" / "my order" wording; the secondary gate below would miss these.
    if re.search(r"\border\b\s*[#:]?\s*\d{4,14}\b", t):
        return True

    # Secondary gate: require both order-domain and "asking" intent.
    # Use word boundaries — substring "order" matches inside "inventory" and misroutes FAQ to verify.
    has_order_domain = bool(
        re.search(r"\border\b", t)
        or re.search(r"\btracking\b", t)
        or re.search(r"\btrack\b", t)
        or re.search(r"\bparcel\b", t)
        or re.search(r"\bpackage\b", t)
    )
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


def _normalize_phone(raw: str) -> Optional[str]:
    """Delegates to shared PK/UAE/KSA normalizer (also used for multi-format API lookup)."""
    return normalize_mobile_for_flow(raw)


def _verified_at_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_verified_at(raw: str) -> Optional[datetime]:
    """Parse bot_flow verified_at (ISO UTC with optional Z suffix)."""
    s = (raw or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1]
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _clear_verification_state(flow: Dict[str, Any]) -> None:
    """Drop script verification fields (manual /reset uses _reset_bot_flow instead)."""
    flow["verified"] = False
    flow["seller_id"] = None
    flow["customer_email"] = None
    flow["verified_at"] = None
    flow["verified_customer"] = None
    if flow.get("customer_kind") == "existing":
        flow["customer_kind"] = None
    st = str(flow.get("step") or "")
    if st in ("existing_awaiting_order_id", "existing_verified_menu"):
        flow["step"] = "conversational"


def _apply_verification_expiry(flow: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    If verified_at is older than settings.customer_bot_verification_expiry_days,
    clear verification state. Returns (flow, expired_this_turn).
    """
    if not flow.get("verified"):
        return flow, False
    days = int(getattr(settings, "customer_bot_verification_expiry_days", 3) or 0)
    if days <= 0:
        return flow, False
    verified_at = flow.get("verified_at")
    if not verified_at:
        _clear_verification_state(flow)
        return flow, True
    verified_dt = _parse_verified_at(str(verified_at))
    if verified_dt is None:
        _clear_verification_state(flow)
        return flow, True
    if datetime.utcnow() - verified_dt > timedelta(days=days):
        _clear_verification_state(flow)
        return flow, True
    return flow, False


def _migrate_legacy_bot_flow(flow: Dict[str, Any]) -> Dict[str, Any]:
    """Map old menu-based steps to the conversational engine."""
    if not flow:
        return {"step": "conversational", "intro_shown": False}
    step = str(flow.get("step") or "")
    if step in ("entry", "new_main_menu"):
        out = {**flow, "step": "conversational"}
        out.pop("customer_kind", None)
        return out
    if step == "existing_verified_menu":
        return {**flow, "step": "conversational"}
    return flow


def _default_skip_store_api(f: Dict[str, Any]) -> bool:
    if f.get("customer_kind") == "new":
        return True
    if f.get("verified"):
        return False
    return True


TRENDING_PAGE_SIZE = 5
TRENDING_STATE_KEYS = (
    "trending_country",
    "trending_products_cache",
    "trending_products_all",
    "trending_category",
    "trending_offset",
    "trending_mode",
)


def _trending_mode(flow: Dict[str, Any]) -> str:
    """Read the active list mode from flow state. "trending" is the default."""
    m = str(flow.get("trending_mode") or "").strip().lower()
    return "non_trending" if m == "non_trending" else "trending"


def _trending_tpl(mode: str, key: str) -> str:
    """Map a ``trending_...`` template key to its ``non_trending_...`` sibling when appropriate.

    Keys that don't start with ``trending_`` (or that lack a ``non_`` variant)
    are returned unchanged so that reusable copy like product-detail replies
    works for both modes.
    """
    if mode == "non_trending" and key.startswith("trending_"):
        mapped = "non_" + key
        if mapped in MSGS:
            return mapped
    return key


# ---------------------------------------------------------------------------
# LLM-driven trending flow gating
# ---------------------------------------------------------------------------


def _trending_llm_mode_global() -> str:
    """Return the globally-configured LLM mode: "off" | "shadow" | "on"."""

    mode = str(getattr(settings, "trending_llm_mode", "") or "").strip().lower()
    if mode not in {"off", "shadow", "on"}:
        return "off"
    return mode


def _trending_llm_allowlist_tokens() -> frozenset[str]:
    raw = str(getattr(settings, "trending_llm_allowlist", "") or "")
    tokens = {t.strip().lower() for t in raw.split(",") if t.strip()}
    return frozenset(tokens)


def _trending_llm_effective_mode(phone: Optional[str]) -> str:
    """Resolve the effective mode for *this* conversation.

    Allowlist semantics: if the allowlist is non-empty, only matching
    customer phones get the configured mode; everyone else stays on "off".
    If the allowlist is empty, the global mode applies to everyone.
    """

    base = _trending_llm_mode_global()
    if base == "off":
        return "off"
    allow = _trending_llm_allowlist_tokens()
    if not allow:
        return base
    ident = str(phone or "").strip().lower()
    return base if ident and ident in allow else "off"
TRENDING_CATEGORY_ALIASES: Dict[str, tuple[str, ...]] = {
    "Electronics": ("electronics", "electronic", "gadgets", "gadget", "mobile", "phone"),
    "Fashion": ("fashion", "clothes", "clothing", "apparel"),
    "Beauty": ("beauty", "makeup", "cosmetics", "skin care", "skincare"),
    "Home & Living": ("home", "living", "home decor", "furniture"),
    "Toys & Games": ("toys", "games", "toy"),
    "Sports & Outdoors": ("sports", "outdoor", "fitness"),
    "Pets": ("pets", "pet", "pet care"),
    "Automotive": ("automotive", "car", "bike", "vehicle"),
    "Baby & Kids": ("baby", "kids", "children"),
    "Books & Media": ("books", "media", "book"),
    "Office & Stationery": ("office", "stationery", "school supplies"),
    "Groceries & Food": ("groceries", "grocery", "food", "snacks"),
    "Health & Wellness": ("health", "wellness", "supplements"),
    "Jewelry & Watches": ("jewelry", "jewellery", "watches", "watch"),
    "Luggage & Travel": ("luggage", "travel", "bag", "bags"),
    "Tools & Home Improvement": ("tools", "home improvement", "hardware"),
    "Garden & Outdoor": ("garden", "gardening"),
    "Musical Instruments": ("musical", "instruments", "instrument"),
    "Art & Crafts": ("art", "crafts", "craft"),
    "Party & Occasion": ("party", "occasion", "decorations"),
}


def _trending_footer_country_label(country_code: str) -> str:
    c = (country_code or "").strip().upper()
    if c == "PK":
        return "Pakistan"
    return c


def _trending_followup_other_markets(cc: str) -> Tuple[str, str]:
    """Two other markets for ChatGPT-style follow-up bullets (current = cc)."""
    c = (cc or "").strip().upper()
    if c == "KSA":
        return "UAE", "Pakistan"
    if c == "UAE":
        return "KSA", "Pakistan"
    if c == "PK":
        return "KSA", "UAE"
    return "UAE", "KSA"


def _trending_followup_block(
    lang: str, country_code: str, *, mode: str = "trending"
) -> str:
    """Return just the follow-up suggestions block (empty string when disabled)."""
    if not bool(getattr(settings, "llm_followup_suggestions", True)):
        return ""
    oa, ob = _trending_followup_other_markets(country_code)
    tpl_key = _trending_tpl(mode, "trending_followup_suggestions")
    return _t(lang, MSGS[tpl_key]).format(other_a=oa, other_b=ob)


def _append_trending_followup_suggestions(
    lang: str, country_code: str, text: str, *, mode: str = "trending"
) -> str:
    """Append deterministic follow-ups when LLM_FOLLOWUP_SUGGESTIONS is enabled (trending is non-LLM)."""
    base = (text or "").strip()
    if not base:
        return base
    block = _trending_followup_block(lang, country_code, mode=mode)
    return f"{base}{block}".strip() if block else base


_EMPTY_CATALOG_FOLLOWUPS: Dict[str, Dict[str, List[str]]] = {
    "en": {
        "trending": [
            "Show trending in {other_a}",
            "Show trending in {other_b}",
            "Show non-trending in {country}",
        ],
        "non_trending": [
            "Show non-trending in {other_a}",
            "Show non-trending in {other_b}",
            "Show trending in {country}",
        ],
    },
    "ar": {
        "trending": [
            "أرني المنتجات الرائجة في {other_a}",
            "أرني المنتجات الرائجة في {other_b}",
            "أرني المنتجات غير الرائجة في {country}",
        ],
        "non_trending": [
            "أرني المنتجات غير الرائجة في {other_a}",
            "أرني المنتجات غير الرائجة في {other_b}",
            "أرني المنتجات الرائجة في {country}",
        ],
    },
    "roman_urdu": {
        "trending": [
            "{other_a} ke trending products dikhao",
            "{other_b} ke trending products dikhao",
            "{country} ke non-trending products dikhao",
        ],
        "non_trending": [
            "{other_a} ke non-trending products dikhao",
            "{other_b} ke non-trending products dikhao",
            "{country} ke trending products dikhao",
        ],
    },
    "ur": {
        "trending": [
            "{other_a} کے ٹرینڈنگ پراڈکٹس دکھاؤ",
            "{other_b} کے ٹرینڈنگ پراڈکٹس دکھاؤ",
            "{country} کے غیر ٹرینڈنگ پراڈکٹس دکھاؤ",
        ],
        "non_trending": [
            "{other_a} کے غیر ٹرینڈنگ پراڈکٹس دکھاؤ",
            "{other_b} کے غیر ٹرینڈنگ پراڈکٹس دکھاؤ",
            "{country} کے ٹرینڈنگ پراڈکٹس دکھاؤ",
        ],
    },
}


def _empty_catalog_followups(country_code: str, mode: str, lang: str) -> List[str]:
    """Three short next-step suggestions shown below an empty-catalogue reply.

    Example (trending, UAE, roman_urdu):
        • KSA ke trending products dikhao
        • Pakistan ke trending products dikhao
        • UAE ke non-trending products dikhao
    """
    if not bool(getattr(settings, "llm_followup_suggestions", True)):
        return []
    normalized_mode = "non_trending" if mode == "non_trending" else "trending"
    lang_map = _EMPTY_CATALOG_FOLLOWUPS.get(lang) or _EMPTY_CATALOG_FOLLOWUPS["en"]
    templates = lang_map.get(normalized_mode) or lang_map["trending"]
    other_a, other_b = _trending_followup_other_markets(country_code)
    country_label = _trending_footer_country_label(country_code)
    out: List[str] = []
    for tpl in templates:
        try:
            out.append(tpl.format(country=country_label, other_a=other_a, other_b=other_b))
        except (IndexError, KeyError):
            continue
    return out


def _exit_trending_for_greeting(flow: Dict[str, Any], flow_lang: str) -> Tuple[Dict[str, Any], str]:
    """Leave trending steps on hi/hello; keep customer_kind when set, else acknowledge and go conversational."""
    nf = {**flow, "lang": flow_lang}
    for k in TRENDING_STATE_KEYS:
        nf.pop(k, None)
    nf["step"] = "conversational"
    nf["intro_shown"] = True
    if flow.get("customer_kind"):
        return nf, _t(flow_lang, MSGS["hello_ack"])
    nf["customer_kind"] = None
    return nf, _t(flow_lang, MSGS["hello_ack"])


def _parse_trending_category(text: str) -> Optional[str]:
    s = (text or "").strip().lower()
    if not s:
        return None
    for category, aliases in TRENDING_CATEGORY_ALIASES.items():
        if category.lower() in s:
            return category
        for a in aliases:
            if a in s:
                return category
    return None


def _filter_trending_items_by_category(items: List[Dict[str, Any]], category: Optional[str]) -> List[Dict[str, Any]]:
    if not category:
        return items
    c = category.strip().lower()
    return [it for it in items if str(it.get("category") or "").strip().lower() == c]


def _trending_visible_list(
    all_items: List[Dict[str, Any]], category: Optional[Any]
) -> List[Dict[str, Any]]:
    if isinstance(category, str) and category.strip():
        return _filter_trending_items_by_category(all_items, category)
    return list(all_items)


def _trending_emoji_rank(i: int) -> str:
    em = {
        1: "1️⃣",
        2: "2️⃣",
        3: "3️⃣",
        4: "4️⃣",
        5: "5️⃣",
        6: "6️⃣",
        7: "7️⃣",
        8: "8️⃣",
        9: "9️⃣",
        10: "🔟",
    }
    return em.get(i, f"{i}.")


def _trending_list_line(rank: int, it: Dict[str, Any]) -> str:
    """Product list line: name + price only. Description is shown only when user picks a product."""
    nm = str(it.get("product_name") or "").strip()
    pb = _trending_price_bit(it)
    bullet = _trending_emoji_rank(rank)
    if not nm:
        return bullet
    if pb:
        return f"{bullet} {nm} - {pb}"
    return f"{bullet} {nm}"


# Short single/double-word pagination triggers. Matched on whole-token basis so
# unrelated words containing these letters (e.g. "more expensive") don't fire.
_TRENDING_MORE_TOKEN_PHRASES: tuple[tuple[str, ...], ...] = (
    # English
    ("more",),
    ("m",),
    ("next",),
    ("continue",),
    ("go",),
    ("yes",),
    ("ya",),
    # Arabic
    ("مزيد",),
    ("المزيد",),
    ("التالي",),
    ("أكثر",),
    ("اكثر",),
    ("كمان",),
    ("كمل",),
    ("زيد",),
    ("استمر",),
    # Roman Urdu / Urdu
    ("aur",),
    ("aage",),
    ("mazeed",),
    ("mazid",),
    ("mazyed",),
    ("zyada",),
    ("ziada",),
    ("chalao",),
    # Two-token acks
    ("yes", "more"),
    ("show", "more"),
    ("see", "more"),
    ("give", "more"),
    ("load", "more"),
    ("more", "please"),
    ("next", "page"),
)

# Multi-word pagination phrases. Substring match on the normalised text.
_TRENDING_MORE_PHRASES: tuple[str, ...] = (
    # English
    "show me more",
    "show some more",
    "show more",
    "see more",
    "see some more",
    "give me more",
    "send more",
    "load more",
    "keep going",
    "more products",
    "more items",
    "more trending",
    "next page",
    "anything else",
    "what else",
    # Arabic — "more", "show me more", "more products", etc.
    "المزيد",
    "مزيد",
    "اعرض المزيد",
    "أعرض المزيد",
    "اظهر المزيد",
    "أظهر المزيد",
    "ارسل المزيد",
    "أرسل المزيد",
    "ورني المزيد",
    "منتجات اكثر",
    "منتجات أكثر",
    "التالي",
    "كمل",
    "كمان",
    "استمر",
    # Roman Urdu
    "aur dikhao",
    "aur dikha",
    "aur dikha do",
    "aur dikhaiye",
    "aur dekhna",
    "aur products",
    "aur product",
    "aur items",
    "aur batao",
    "aur cheezen",
    "aur cheezain",
    "mazeed dikhao",
    "mazid dikhao",
    "mazyed dikhao",
    "zyada dikhao",
    "ziada dikhao",
    "aage dikhao",
    "aage dikha",
    "continue karo",
    "agay dikhao",
)


def _wants_trending_more(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    flat = unicodedata.normalize("NFKC", t).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    # Strip common ending punctuation/emoji so "more?" / "more!" still match.
    flat = re.sub(r"[\.!\?،,؟]+$", "", flat).strip()
    tokens = [x for x in re.split(r"\s+", flat) if x]
    if 1 <= len(tokens) <= 2:
        tup = tuple(tokens)
        if tup in _TRENDING_MORE_TOKEN_PHRASES:
            return True
    return any(p in flat for p in _TRENDING_MORE_PHRASES)


def _trending_footer_template_key(
    *, first_batch: bool, has_more: bool, mode: str = "trending"
) -> tuple[str, bool]:
    """Return (MSGS key, whether template expects {country}).

    The ``mode`` argument is forwarded through :func:`_trending_tpl` so the
    non-trending list reuses the same footer logic with its own copy.
    """
    if first_batch and has_more:
        base = "trending_footer_first_has_more"
        return (_trending_tpl(mode, base), False)
    if first_batch and not has_more:
        base = "trending_footer_first_only"
        return (_trending_tpl(mode, base), True)
    if not first_batch and has_more:
        base = "trending_footer_more_has_more"
        return (_trending_tpl(mode, base), False)
    base = "trending_footer_more_end"
    return (_trending_tpl(mode, base), True)


def _parse_trending_country_reply(text: str) -> Optional[str]:
    raw = (text or "").strip()
    if not raw:
        return None
    t = unicodedata.normalize("NFKC", raw).lower()
    t = t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    # Menu order: 1 = KSA, 2 = UAE, 3 = Pakistan
    if t == "1":
        return "KSA"
    if t == "2":
        return "UAE"
    if t == "3":
        return "PK"
    if t in ("971",):
        return "UAE"
    if t in ("966",):
        return "KSA"
    if t in ("92",):
        return "PK"
    if t in ("uae",):
        return "UAE"
    if t in ("ksa", "pk"):
        return t.upper()
    if "uae" in t or "emirates" in t or "dubai" in t or "abu dhabi" in t:
        return "UAE"
    if "ksa" in t or "saudi" in t or "riyadh" in t or "jeddah" in t:
        return "KSA"
    if "pakistan" in t or "lahore" in t or "karachi" in t:
        return "PK"
    if t == "sa" and len(t) <= 3:
        return "KSA"
    return None


def _trending_price_bit(it: Dict[str, Any]) -> str:
    pr = float(it.get("price") or 0)
    cur = str(it.get("currency") or "").strip()
    if pr > 0 and cur:
        if pr == int(pr):
            return f"{pr:g} {cur}"
        return f"{pr} {cur}"
    return ""


def _wa_caption_for_trending_row(it: Dict[str, Any], *, rank: Optional[int] = None) -> str:
    """WhatsApp image caption; optional global list rank (1️⃣ …) matches inbox list lines."""
    name = str(it.get("product_name") or "").strip()
    pb = _trending_price_bit(it)
    if rank is not None and rank >= 1:
        bullet = _trending_emoji_rank(rank)
        if pb:
            return f"{bullet} {name} - {pb}"
        return f"{bullet} {name}"
    if pb:
        return f"📦 {name}\n💰 {pb}"
    return f"📦 {name}"


def _wa_images_for_trending_row(
    it: Dict[str, Any], *, rank: Optional[int] = None
) -> List[Dict[str, str]]:
    """Build the WhatsApp image payload(s) for a single trending product.

    The first entry carries the caption; subsequent images use an empty
    caption so they render as a compact gallery under the first one. Covers
    both the multi-image ``image_urls`` list (populated by the resolver) and
    the legacy single ``image_url`` field.
    """
    urls: List[str] = []
    raw = it.get("image_urls")
    if isinstance(raw, list):
        for u in raw:
            s = str(u or "").strip()
            if s and s not in urls:
                urls.append(s)
    primary = str(it.get("image_url") or "").strip()
    if primary and primary not in urls:
        urls.insert(0, primary)
    if not urls:
        return []
    caption = _wa_caption_for_trending_row(it, rank=rank)
    out: List[Dict[str, str]] = [{"image_url": urls[0], "caption": caption}]
    for u in urls[1:]:
        out.append({"image_url": u, "caption": ""})
    return out


def _trending_global_rank(visible: List[Dict[str, Any]], row: Dict[str, Any]) -> Optional[int]:
    rid = row.get("id")
    if rid is not None:
        for j, v in enumerate(visible):
            if v.get("id") == rid:
                return j + 1
    try:
        return visible.index(row) + 1
    except ValueError:
        return None


def _trending_inbox_and_web_body(
    lang: str,
    country: str,
    items: List[Dict[str, Any]],
    *,
    category: Optional[str] = None,
    start_rank: int = 1,
    is_more_batch: bool = False,
    mode: str = "trending",
) -> str:
    if not items:
        no_key = _trending_tpl(mode, "trending_no_products")
        return _t(lang, MSGS[no_key]).format(
            country=_trending_footer_country_label(country)
        )
    if category:
        base = "trending_intro_more_category" if is_more_batch else "trending_intro_first_category"
        intro_key = _trending_tpl(mode, base)
        intro = _t(lang, MSGS[intro_key]).format(country=country, category=category)
    else:
        base = "trending_intro_more" if is_more_batch else "trending_intro_first"
        intro_key = _trending_tpl(mode, base)
        intro = _t(lang, MSGS[intro_key]).format(country=country)
    lines = [intro]
    for i, it in enumerate(items):
        lines.append(_trending_list_line(start_rank + i, it))
    return "\n\n".join(lines)


def _strip_trending_detail_query(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(
        r"(?i)^(?:tell me about|details on|detail on|details for|info on|information on|"
        r"more about|what about|about|explain|describe)\s+",
        "",
        s,
    ).strip()
    s = re.sub(r"(?i)^(?:the\s+)?(?:product|item)\s+#?", "", s).strip()
    s = re.sub(r"(?i)^(?:product|item)\s+number\s*", "", s).strip()
    m = re.search(r"(?i)(?:product|item)\s*#?\s*(\d+)\s*$", s)
    if m and s.strip().lower().startswith(("product", "item")):
        return m.group(1)
    return s


def _select_trending_product_from_list(
    items: List[Dict[str, Any]], text: str
) -> Optional[Dict[str, Any]]:
    if not items or not (text or "").strip():
        return None
    raw = text.strip()
    t_norm = unicodedata.normalize("NFKC", raw).lower()
    t_norm = t_norm.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    query = _strip_trending_detail_query(t_norm)
    query = query.lstrip("#").strip()
    if len(query) < 2 and not re.fullmatch(r"\d+", query):
        return None
    ord_m = re.search(r"(?i)^(\d{1,3})\s*(?:st|nd|rd|th)\b", query)
    if ord_m and len(query) <= 14:
        query = ord_m.group(1)
    # Reuse the pagination detector so *every* variant of "show me more" we now
    # understand is prevented from being read as a product name.
    if _wants_trending_more(query):
        return None

    if re.fullmatch(r"\d+", query):
        idx = int(query) - 1
        if 0 <= idx < len(items):
            return items[idx]

    if query:
        for row in items:
            nm = str(row.get("product_name") or "").strip().lower()
            if nm and (nm in query or query in nm):
                return row

        name_lowers = [str(x.get("product_name") or "").strip().lower() for x in items]
        name_lowers = [n for n in name_lowers if n]
        best = difflib.get_close_matches(query, name_lowers, n=1, cutoff=0.72)
        if best:
            for row in items:
                if str(row.get("product_name") or "").strip().lower() == best[0]:
                    return row

        qflat = re.sub(r"[^\w\u0600-\u06FF\s]", " ", query)
        qflat = re.sub(r"\s+", " ", qflat).strip()
        for row in items:
            desc = str(row.get("description") or "").strip().lower()
            if len(desc) >= 10 and qflat and qflat in desc:
                return row
    return None


def _extract_sourcing_product_name(text: str) -> Optional[str]:
    """
    Best-effort product name extraction from sourcing messages.
    e.g. "muje seoul cream chaie" → "seoul cream"
    """
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    # Strip common prefixes
    low = re.sub(
        r"^(?:muje|mujhe|mjy|mujhay|i want|i need|main|mein)\s+",
        "",
        low,
    ).strip()
    # Strip common suffixes
    low = re.sub(
        r"\s+(?:chahiye|chaiye|chahie|chaie|mangta|mangti|chahte|"
        r"local market.*|se.*chahiye|from local.*|mil sakta.*|mil skta.*|"
        r"piece.*|pieces.*|pcs.*|unit.*|units.*|qty.*)$",
        "",
        low,
    ).strip()
    # Strip filler words
    low = re.sub(
        r"\b(?:ye|yeh|wo|woh|ek|ik|is|ka|ki|ke|ko|se|mein|hai|app|aap)\b",
        "",
        low,
    ).strip()
    low = re.sub(r"\s+", " ", low).strip()
    # If what remains is too short or too long, give up
    if not low or len(low) < 3 or len(low) > 80:
        return None
    # Don't return if it's just generic words
    generic = {"product", "products", "item", "items", "order", "rate", "price", "bulk"}
    if low in generic:
        return None
    return low


def _wants_product_sourcing(text: str) -> bool:
    """
    Detect product sourcing, bulk order, or wholesale inquiry that requires agent handoff.
    Examples: "muje seoul cream chaie", "500 piece chahiye", "local market se", "bulk order"
    """
    t = (text or "").strip().lower()
    if not t or len(t) < 6:
        return False
    flat = re.sub(r"[^\w\u0600-\u06FF\s]", " ", t)
    flat = re.sub(r"\s+", " ", flat).strip()

    # Strong sourcing / bulk phrases — immediate match
    strong_markers = (
        "local market",
        "bulk order",
        "wholesale",
        "wholesale price",
        "wholesale rate",
        "source product",
        "source karo",
        "source kardo",
        "source kar do",
        "arrange kar do",
        "arrange kardo",
        "arrange karo",
        "mangwa do",
        "mangwao",
        "mangwa dein",
        "kahan se milay ga",
        "kahan se milega",
        "kaha se milega",
        "kahan milega",
    )
    if any(m in flat for m in strong_markers):
        return True

    # Quantity patterns: "500 piece", "100 units", "50 pcs" etc.
    has_quantity = bool(re.search(r"\b\d{2,}\s*(?:piece|pieces|pcs|unit|units|qty)\b", flat))
    # Product-want signals
    want_markers = (
        "chahiye", "chaiye", "chahie", "chaie", "chaie",
        "chahte", "mangta", "mangti",
        "rate batao", "rate btao", "rate batain", "rate btain",
        "rate bata", "price batao", "price btao",
        "price bata do", "rate bata do",
        "kitne ka hai", "kitne ka",
        "kitnay ka", "kitna rate",
    )
    has_want = any(m in flat for m in want_markers)

    if has_quantity:
        return True
    if has_quantity and has_want:
        return True

    # "product chahiye" / "[product name] chahiye" + implies sourcing when message is short enough
    # and NOT a general question (no "kya", "how", "?")
    if has_want and "?" not in t:
        # Check if the message mentions a specific product (not a general phrase)
        general_words = {"information", "help", "madad", "maloomat", "details", "jankari", "kya", "how", "what", "question", "sawal"}
        tokens = set(flat.split())
        if not tokens & general_words:
            return True

    return False


def _wants_non_trending_products(text: str) -> bool:
    """Detects a customer asking for products that are **NOT** trending.

    Examples:
        - "show me products which are not trending"
        - "ksa k prodcuts dikhao jo trending nhi hain"
        - "non-trending products"
        - "المنتجات غير الرائجة"

    The non-trending list is served from the same trending-flow pipeline with
    ``trending_mode = "non_trending"`` (country selection, pagination,
    product-detail fetch all work identically). We detect the intent here so
    we don't fall through to the positive ``_wants_trending_products``
    handler and show the opposite of what was asked.
    """
    t = (text or "").strip().lower()
    if not t or len(t) > 220:
        return False
    flat = t.replace("\n", " ")

    # Must still be talking about products at all; otherwise phrases like
    # "not trending right now?" (about something unrelated) wouldn't qualify.
    # ``prod`` covers "product / products / prodcut / prodcts" (typos).
    product_markers = (
        "prod",
        "item",
        "cheez",
        "maal",
        "samaan",
        "saman",
        "منتج",
        "منتجات",
        "سلع",
        "سلعة",
    )
    if not any(m in flat for m in product_markers):
        return False

    # English + Arabic + Roman-Urdu negations around the word "trending".
    if re.search(r"\b(not|without|no)\s+trending\b", flat):
        return True
    if re.search(r"\bnon[-\s]*trending\b", flat):
        return True
    if re.search(
        r"\btrending\s+(nahi|nahin|nhi|mat|na)\b",
        flat,
    ):
        return True
    # Arabic: "غير رائج", "ليست رائجة", "ما هي غير الرائجة"
    if re.search(r"(غير|ليست|ليس|ما)\s*(ال)?\s*رائج", flat):
        return True
    return False


def _wants_trending_products(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t or len(t) > 220:
        return False
    flat = t.replace("\n", " ")
    # Negation — user explicitly does NOT want trending products. Catches
    # English, Roman-Urdu, and Arabic variants (see _wants_non_trending_products).
    if _wants_non_trending_products(text):
        return False
    if re.search(r"\bnot\s+trending\b|\bnon[\s-]?trending\b|\bwithout\s+trending\b", flat):
        return False
    # Order / account intent owns messages that mention "order", "tracking",
    # "invoice", "parcel", etc. — even "give me product details" type phrases
    # that happen to share the word "product" with the browse-catalog flow.
    # The trending catalog is for *browsing*; anything about a specific order
    # or a specific product's spec sheet must never land here.
    if re.search(r"\border(s|ed)?\b", flat):
        return False
    if re.search(
        r"\b(tracking|track|parcel|package|invoice|invoices|billing|statement|shipment|shipments|delivery)\b",
        flat,
    ):
        return False
    # "product details / info / information / specs / specifications" → the user
    # wants data about *a* product, not to browse the catalog. Let it fall
    # through to KB / LLM answer path instead of opening the trending flow.
    if re.search(
        r"\bproducts?\s+(details?|info(?:rmation)?|specs?|specification|price|rate|cost)\b",
        flat,
    ):
        return False
    if re.search(
        r"\b(details?|info(?:rmation)?)\s+(of|about|for|regarding)\s+(the\s+|a\s+|my\s+)?products?\b",
        flat,
    ):
        return False
    markers = (
        "trending",
        "trend ",
        "best seller",
        "bestseller",
        "browse product",
        "show product",
        "show me product",
        "give product",
        "give me product",
        "popular product",
        "top product",
        "tranding",
        "mashhoor",
        "popular items",
        "trending product",
        "products dekh",
        "product dekh",
        "product dikha",
        "product dikhao",
        "dikhao product",
        "naye product",
        "new arrivals",
        "hot product",
        "give trending",
        "show trending",
        "products btao",
        "products batao",
        "product btao",
        "product batao",
    )
    # Normalize plural→singular for broader matching
    flat_singular = flat.replace("products", "product")
    return any(m in flat for m in markers) or any(m in flat_singular for m in markers)


def _looks_like_account_question(text: str) -> bool:
    """Invoice / account area — requires verification like order lookups."""
    t = (text or "").strip().lower()
    if len(t) < 6:
        return False
    if _looks_like_order_status_question(text):
        return False
    markers = (
        "invoice",
        "invoices",
        "billing",
        "statement",
        "payment history",
        "my account",
        "account details",
    )
    ru = ("hisab", "invoice", "payment", "account")
    if any(m in t for m in markers):
        return True
    if any(m in t for m in ru) and len(t) >= 8:
        return True
    return False


def _needs_account_verification(flow: Dict[str, Any]) -> bool:
    if _script_verification_bypassed():
        return False
    if bool(flow.get("verified")):
        return False
    # Existing-customer path with seller scope already on file (completed verify earlier) —
    # do not force the script again if the verified flag was lost to a merge bug.
    if (flow.get("customer_kind") == "existing") and _flow_merchant_seller_id(flow):
        return False
    return True


def _reset_bot_flow(lang_code: str) -> Dict[str, Any]:
    return {
        "step": "conversational",
        "intro_shown": True,
        "lang": lang_code,
        "verified": False,
        "seller_id": None,
        "customer_email": None,
        "verified_at": None,
        "verified_customer": None,
        "pending_email": None,
        "pending_mobile": None,
        "pending_order_ref": None,
        "verify_reason": None,
        "customer_kind": None,
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
    """True when a mid-session 'hi' should not trigger resume (early / idle state)."""
    if not flow:
        return True
    step = str(flow.get("step") or "conversational")
    # Browsing trending: treat like idle chat — hello should not force resume vs start fresh.
    if step in ("trending_awaiting_country", "trending_showing_products"):
        return True
    if step == "awaiting_resume_choice":
        return False
    if flow.get("verified"):
        return False
    if step in (
        "existing_awaiting_email",
        "existing_awaiting_verification_code",
        "existing_awaiting_mobile",
        "existing_awaiting_order_id",
        "existing_awaiting_experience",
        "awaiting_agent",
        "new_main_menu",
        "existing_verified_menu",
        "sourcing_collecting_details",
    ):
        return False
    if step == "conversational":
        return True
    if step in ("awaiting_customer_type", "entry"):
        return True
    return False


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


async def _classify_entry_menu_intent_llm(user_message: str) -> str:
    """
    When the new/existing menu text does not match keywords/digits, classify with the LLM.

    Returns one of: new | existing | agent_hours | other
    - agent_hours: asking when support/agents are online, working hours, availability.
    - other: general FAQ / unrelated (route to main AI).
    On failure or missing API key, returns \"other\".
    """
    msg = (user_message or "").strip()
    if not msg or len(msg) > 500:
        return "other"
    key = get_openai_api_key()
    if not key:
        logger.warning("entry_menu intent LLM: no OpenAI API key configured")
        return "other"
    system = (
        "You classify one user message at the Arabia Dropshipping bot ENTRY step "
        "(the bot just showed a welcome menu with topics and options **1** new / **2** existing).\n"
        "Choose exactly ONE label:\n"
        "- new — user indicates they are NEW (first time, sign up, register, typos like neww).\n"
        "- existing — user indicates EXISTING (already have account, login, old customer, "
        "typos like existinf/exsisting).\n"
        "- agent_hours — user asks when human agents/support are AVAILABLE, working hours, "
        "online time, office hours, schedule, kab online, agents available, 24/7 question, etc. "
        "(NOT choosing new vs existing).\n"
        "- other — general questions, shipping, products, unrelated text, or impossible to tell.\n"
        "Output exactly one lowercase word: new OR existing OR agent_hours OR other. No punctuation."
    )
    human = f"User message:\n{msg}"
    try:
        llm = ChatOpenAI(
            model_name=settings.openai_model,
            temperature=0,
            openai_api_key=key,
            max_tokens=12,
        )
        resp = await llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=human)]
        )
        text_out = (getattr(resp, "content", None) or str(resp) or "").strip().lower()
        if re.search(r"\bagent_hours\b", text_out) or (
            re.search(r"\bagent\b", text_out) and re.search(r"\bhours?\b", text_out)
        ):
            return "agent_hours"
        first = (text_out.split() or [""])[0]
        token = re.sub(r"[^a-z]", "", first)
        if token.startswith("exist") or token == "existing":
            return "existing"
        if token.startswith("new"):
            return "new"
        if token == "other":
            return "other"
        return "other"
    except Exception as exc:  # noqa: BLE001
        logger.warning("entry_menu intent LLM classification failed: %s", exc)
        return "other"


def _entry_menu_agent_hours_reply(db: Session, tenant_id: int, lang: str) -> str:
    sched = (
        db.query(TenantSchedule)
        .filter(TenantSchedule.tenant_id == tenant_id)
        .first()
    )
    if not sched:
        body = _t(lang, _AGENT_SCHEDULE_UNKNOWN_MSGS)
    else:
        body = format_tenant_schedule_for_customer(
            lang,
            working_days=sched.working_days,
            start_time=sched.start_time,
            end_time=sched.end_time,
        )
    hint = _t(lang, MSGS["customer_type_menu_reminder"])
    return f"{body}\n\n{hint}".strip()


def _pick(data: Dict[str, Any], *keys: str) -> str:
    """Return the first non-empty string value found under any of the given keys."""
    for k in keys:
        v = data.get(k)
        if v is not None and str(v).strip() and str(v).strip() != "—":
            return str(v).strip()
    return ""


def _extract_order_fields(raw: Dict[str, Any], ref: str) -> Dict[str, Any]:
    """
    Normalize an order payload (from DB order_data JSON or external API) into
    a flat dict with every field the bot might display.
    """
    return {
        "order_number": _pick(raw, "order_number", "order_id", "id") or ref,
        "order_date": _pick(
            raw,
            "order_date",
            "placed_at",
            "ordered_at",
            "created_at",
            "date",
            "booking_date",
            "order_placed_date",
            "invoice_row_date",
        ),
        "status": _pick(raw, "status"),
        "delivery_status": _pick(raw, "delivery_status", "fulfillment_status", "shipping_status"),
        "expected_delivery": _pick(raw, "expected_delivery", "estimated_delivery", "delivery_date", "expected_delivery_date"),
        "tracking_id": _pick(raw, "tracking_id", "tracking_number", "awb_number", "awb"),
        "payment_status": _pick(raw, "payment_status", "invoice_pay_status"),
        "invoice_id": _pick(raw, "invoice_id", "invoice_number", "invoice_ref"),
        "invoice_amount": _pick(raw, "invoice_amount"),
        "return_status": _pick(raw, "return_status"),
        "return_date": _pick(raw, "return_date"),
        "return_charges": _pick(raw, "return_charges"),
        "return_charge_invoice": _pick(raw, "return_charge_invoice"),
        "return_reason": _pick(raw, "return_reason"),
        "cancellation_type": _pick(raw, "cancellation_type"),
        "cancellation_reason": _pick(raw, "cancellation_reason"),
        "total_amount": _pick(
            raw, "total_amount", "amount", "invoice_net_total", "invoice_payable"
        ),
        "currency": _pick(raw, "currency"),
    }


def _flow_merchant_seller_id(flow: Dict[str, Any]) -> Optional[str]:
    raw = flow.get("seller_id")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    vc = flow.get("verified_customer")
    if isinstance(vc, dict):
        return merchant_seller_scope_from_row(vc)
    return None


async def _lookup_order(
    db: Session,
    tenant_id: int,
    order_ref: str,
    store_client: StoreIntegrationClient,
    seller_id: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Returns (order_dict_or_None, source).

    source is one of: \"db\" | \"api\" | \"not_found\" | \"api_error\"
    When the order comes from the API, a secondary call to
    /orders/{order_id}/tracking is attempted to fill in status/tracking id
    so the reply can name the current logistics state without a second DB hit.
    """
    ref = (order_ref or "").strip()
    if not ref:
        return None, "not_found"
    sid = (str(seller_id).strip() if seller_id is not None else "") or None

    row = (
        db.query(Order)
        .filter(Order.tenant_id == tenant_id, Order.order_number == ref)
        .first()
    )
    if row:
        base: Dict[str, Any] = {
            "order_number": row.order_number,
            "status": row.status,
            "total_amount": row.total_amount,
            "currency": row.currency,
        }
        if isinstance(row.order_data, dict):
            base.update(row.order_data)
        return _extract_order_fields(base, ref), "db"

    detail: Optional[Dict[str, Any]] = None
    try:
        detail = await store_client.get_order_by_id(ref, seller_id=sid)
        if not detail:
            detail = await store_client.get_order_by_number(ref, seller_id=sid)
    except Exception:  # noqa: BLE001
        logger.exception("order lookup: /orders/%s failed", ref)
        return None, "api_error"

    if not detail and sid:
        try:
            detail = await store_client.resolve_order_by_reference(ref, sid)
        except Exception:  # noqa: BLE001
            logger.exception("order lookup: resolve_order_by_reference failed for %s", ref)

    if not detail and sid:
        try:
            df, dt = _orders_list_date_window()
            invp = await store_client.get_invoice_by_seller_id(
                sid, date_from=df, date_to=dt, all_invoices=True
            )
            inv_rows: List[Dict[str, Any]] = []
            if isinstance(invp.get("invoices"), list):
                inv_rows = [x for x in invp["invoices"] if isinstance(x, dict)]
            elif isinstance(invp.get("invoice"), dict):
                inv_rows = [invp["invoice"]]
            stub = synthetic_order_stub_from_invoices(inv_rows, ref)
            if stub:
                detail = stub
        except Exception:  # noqa: BLE001
            logger.exception("order lookup: invoice stub path failed for %s", ref)

    if not detail:
        return None, "not_found"

    try:
        oid_track = str(
            (detail.get("id") if isinstance(detail, dict) else None)
            or (detail.get("_id") if isinstance(detail, dict) else None)
            or (detail.get("order_id") if isinstance(detail, dict) else None)
            or ref,
        ).strip()
        tracking = await store_client.get_order_tracking(oid_track, seller_id=sid)
    except Exception:  # noqa: BLE001
        logger.exception("order lookup: /orders/%s/tracking failed (continuing)", ref)
        tracking = None

    if isinstance(tracking, dict):
        merged: Dict[str, Any] = dict(detail)
        for k, v in tracking.items():
            if v is None or v == "":
                continue
            # Prefer live tracking status/id over order payload.
            if k in {"status", "delivery_status", "tracking_id", "tracking_number", "awb", "awb_number"}:
                merged[k] = v
            else:
                merged.setdefault(k, v)
        detail = merged

    return _extract_order_fields(detail, ref), "api"


# Each phrase already contains its auxiliary verb so it can slot into the
# sentence as: "Your order #X was placed on DATE, and {phrase}[, tracking …]".
_STATUS_PHRASES = {
    "english": {
        "in_transit": "is currently in transit",
        "in transit": "is currently in transit",
        "shipped": "has been shipped",
        "dispatched": "has been dispatched",
        "delivered": "has been delivered",
        "returned": "has been returned",
        "return received": "has been returned",
        "return_received": "has been returned",
        "return moving hub to hub": "is currently being returned",
        "return moving": "is currently being returned",
        "return to origin": "is being returned to origin",
        "return_to_origin": "is being returned to origin",
        "returned to origin": "was returned to origin",
        "out for delivery": "is out for delivery",
        "on delivery": "is out for delivery",
        "delivery attempted": "had a delivery attempt",
        "at warehouse": "is at the warehouse",
        "in warehouse": "is at the warehouse",
        "at hub": "is at the hub",
        "booked": "has been booked",
        "booking done": "has been booked",
        "cancelled": "has been cancelled",
        "canceled": "has been cancelled",
        "pending": "is being processed",
        "processing": "is being processed",
        "confirmed": "has been confirmed",
        "failed": "has failed",
    },
    "roman_urdu": {
        "in_transit": "transit mein hai",
        "in transit": "transit mein hai",
        "shipped": "ship ho chuka hai",
        "dispatched": "dispatch ho chuka hai",
        "delivered": "deliver ho chuka hai",
        "returned": "return ho chuka hai",
        "return received": "return ho chuka hai",
        "return_received": "return ho chuka hai",
        "return moving hub to hub": "wapas bhejne ke process mein hai",
        "return moving": "wapas bhejne ke process mein hai",
        "return to origin": "origin ki taraf wapas bheja ja raha hai",
        "return_to_origin": "origin ki taraf wapas bheja ja raha hai",
        "returned to origin": "origin par wapas bhej diya gaya hai",
        "out for delivery": "delivery par nikal chuka hai",
        "on delivery": "delivery par nikal chuka hai",
        "delivery attempted": "delivery attempt ho chuki hai",
        "at warehouse": "warehouse mein hai",
        "in warehouse": "warehouse mein hai",
        "at hub": "hub par hai",
        "booked": "book ho chuka hai",
        "booking done": "book ho chuka hai",
        "cancelled": "cancel ho chuka hai",
        "canceled": "cancel ho chuka hai",
        "pending": "process ho raha hai",
        "processing": "process ho raha hai",
        "confirmed": "confirm ho chuka hai",
        "failed": "fail ho gaya hai",
    },
    "arabic": {
        "in_transit": "قيد التوصيل حالياً",
        "in transit": "قيد التوصيل حالياً",
        "shipped": "تم شحنه",
        "dispatched": "تم إرساله",
        "delivered": "تم توصيله",
        "returned": "تم إرجاعه",
        "return received": "تم إرجاعه",
        "return_received": "تم إرجاعه",
        "return moving hub to hub": "قيد الإرجاع",
        "return moving": "قيد الإرجاع",
        "return to origin": "قيد الإرجاع إلى المصدر",
        "return_to_origin": "قيد الإرجاع إلى المصدر",
        "returned to origin": "تم إرجاعه إلى المصدر",
        "out for delivery": "خرج للتسليم",
        "on delivery": "خرج للتسليم",
        "delivery attempted": "تمت محاولة التسليم",
        "at warehouse": "في المستودع",
        "in warehouse": "في المستودع",
        "at hub": "في المركز اللوجستي",
        "booked": "تم حجزه",
        "booking done": "تم حجزه",
        "cancelled": "تم إلغاؤه",
        "canceled": "تم إلغاؤه",
        "pending": "قيد المعالجة",
        "processing": "قيد المعالجة",
        "confirmed": "تم تأكيده",
        "failed": "فشل",
    },
}


def _humanize_status(raw_status: str, lang: str) -> str:
    """Map an API status string to a user-facing phrase in the given language."""
    key = (raw_status or "").strip().lower()
    if not key:
        return ""
    table = _STATUS_PHRASES.get(lang) or _STATUS_PHRASES["english"]
    if key in table:
        return table[key]
    # Fallback: humanise "return_moving_hub_to_hub" etc. for any unmapped status.
    return (raw_status or "").replace("_", " ").strip().lower()


def _format_order_sentence(lang: str, o: Dict[str, Any]) -> str:
    """
    Build ONE natural sentence describing the order.

    Example (English):
        Your order #157955 was placed on February 10, 2026, and is currently
        being returned with tracking number 6021626316464.

    Falls back gracefully when fields are missing.
    """
    oid = o.get("order_number") or "?"
    order_date = (o.get("order_date") or "").strip()
    status_raw = (o.get("status") or o.get("delivery_status") or "").strip()
    tracking = (o.get("tracking_id") or "").strip()
    cancel_type = (o.get("cancellation_type") or "").lower()
    cancel_reason = (o.get("cancellation_reason") or "").strip()
    ret_reason = (o.get("return_reason") or "").strip()

    status_phrase = _humanize_status(status_raw, lang)
    status_key = (status_raw or "").strip().lower()
    cancelled = status_key in {"cancelled", "canceled"}

    # Per-language connectors / labels used to assemble the sentence.
    if lang == "roman_urdu":
        head = f"Aapka order #{oid}"
        placed_tpl = " {date} ko place hua tha"
        join_status = " aur "
        tracking_tpl = ", tracking number {tracking}"
        reason_tpl = " (wajah: {reason})"
    elif lang == "arabic":
        head = f"طلبك رقم #{oid}"
        placed_tpl = " تم تسجيله في {date}"
        join_status = " و"
        tracking_tpl = " برقم التتبع {tracking}"
        reason_tpl = " (السبب: {reason})"
    else:
        head = f"Your order #{oid}"
        placed_tpl = " was placed on {date}"
        join_status = ", and "
        tracking_tpl = " with tracking number {tracking}"
        reason_tpl = " — reason: {reason}"

    sentence = head
    if order_date:
        sentence += placed_tpl.format(date=order_date)
    if status_phrase:
        sentence += join_status + status_phrase
        if tracking and not cancelled:
            sentence += tracking_tpl.format(tracking=tracking)
    elif tracking:
        sentence += tracking_tpl.format(tracking=tracking)

    reason = cancel_reason if cancelled else (ret_reason if ret_reason else "")
    if reason:
        sentence += reason_tpl.format(reason=reason)

    return sentence.rstrip(",. ") + "."


def _legacy_format_order_details(lang: str, o: Dict[str, Any]) -> str:  # pragma: no cover
    """Detailed multi-line breakdown; kept as an opt-in helper for callers
    that want the long-form report instead of the single-sentence summary."""
    oid = o.get("order_number") or "?"
    status = (o.get("status") or "").lower()
    delivery = (o.get("delivery_status") or "").lower()
    expected = o.get("expected_delivery") or ""
    tracking = o.get("tracking_id") or ""
    payment = (o.get("payment_status") or "").lower()
    invoice = o.get("invoice_id") or ""
    ret_status = (o.get("return_status") or "").lower()
    ret_date = o.get("return_date") or ""
    ret_charges = o.get("return_charges") or ""
    ret_invoice = o.get("return_charge_invoice") or ""
    ret_reason = o.get("return_reason") or ""
    cancel_type = (o.get("cancellation_type") or "").lower()
    cancel_reason = o.get("cancellation_reason") or ""
    currency = o.get("currency") or ""

    # Use effective status: API status takes priority, fall back to delivery_status
    effective = status or delivery or "unknown"

    # --- Status label mapping ---
    STATUS_EN = {
        "in_transit": "is currently in transit",
        "shipped": "has been shipped",
        "delivered": "has been delivered",
        "returned": "was returned",
        "cancelled": "was cancelled",
        "canceled": "was cancelled",
        "pending": "is being processed",
        "processing": "is being processed",
        "confirmed": "has been confirmed",
        "dispatched": "has been dispatched",
        "failed": "has failed",
    }
    STATUS_RU = {
        "in_transit": "transit mein hai",
        "shipped": "ship ho chuka hai",
        "delivered": "deliver ho chuka hai",
        "returned": "return ho chuka hai",
        "cancelled": "cancel ho chuka hai",
        "canceled": "cancel ho chuka hai",
        "pending": "process ho raha hai",
        "processing": "process ho raha hai",
        "confirmed": "confirm ho chuka hai",
        "dispatched": "dispatch ho chuka hai",
        "failed": "fail ho gaya hai",
    }
    STATUS_AR = {
        "in_transit": "قيد التوصيل حاليًا",
        "shipped": "تم شحنه",
        "delivered": "تم توصيله",
        "returned": "تم إرجاعه",
        "cancelled": "تم إلغاؤه",
        "canceled": "تم إلغاؤه",
        "pending": "قيد المعالجة",
        "processing": "قيد المعالجة",
        "confirmed": "تم تأكيده",
        "dispatched": "تم إرساله",
        "failed": "فشل",
    }

    if lang == "roman_urdu":
        parts: list[str] = []
        status_text = STATUS_RU.get(effective, effective)
        parts.append(f"Aapka order #{oid} {status_text}.")

        if expected:
            parts.append(f"Expected delivery: {expected}.")
        if tracking:
            parts.append(f"Tracking number: {tracking}.")
        if payment:
            pay_text = "ho chuki hai" if payment in ("paid", "completed") else payment
            parts.append(f"Payment {pay_text}.")
        if invoice:
            parts.append(f"Yeh invoice {invoice} mein shamil hai.")

        if effective in ("returned",) or ret_status in ("returned",):
            if ret_date:
                parts.append(f"Return date: {ret_date}.")
            if ret_charges:
                rc_text = f"{ret_charges} {currency}".strip()
                parts.append(f"Return charges: {rc_text}.")
            if ret_invoice:
                parts.append(f"Return charges invoice {ret_invoice} mein hain.")
            if ret_reason:
                parts.append(f"Wajah: {ret_reason}.")

        if effective in ("cancelled", "canceled"):
            if cancel_type == "pre_shipment":
                parts.append("Yeh order shipment se pehle cancel hua.")
            elif cancel_type == "post_shipment":
                parts.append("Yeh order ship hone ke baad cancel hua.")
            if cancel_reason:
                parts.append(f"Wajah: {cancel_reason}.")
            if ret_date:
                parts.append(f"Return date: {ret_date}.")
            if ret_charges:
                rc_text = f"{ret_charges} {currency}".strip()
                parts.append(f"Return charges: {rc_text}.")
            if ret_invoice:
                parts.append(f"Return charges invoice {ret_invoice} mein hain.")
            if not ret_charges and cancel_type == "pre_shipment":
                parts.append("Is order par koi charges apply nahi hue.")

        return " ".join(parts)

    if lang == "arabic":
        parts = []
        status_text = STATUS_AR.get(effective, effective)
        parts.append(f"طلبك #{oid} {status_text}.")

        if expected:
            parts.append(f"التسليم المتوقع: {expected}.")
        if tracking:
            parts.append(f"رقم التتبع: {tracking}.")
        if payment:
            pay_text = "تمت" if payment in ("paid", "completed") else payment
            parts.append(f"الدفع: {pay_text}.")
        if invoice:
            parts.append(f"مضمّن في الفاتورة {invoice}.")

        if effective in ("returned",) or ret_status in ("returned",):
            if ret_date:
                parts.append(f"تاريخ الإرجاع: {ret_date}.")
            if ret_charges:
                rc_text = f"{ret_charges} {currency}".strip()
                parts.append(f"رسوم الإرجاع: {rc_text}.")
            if ret_invoice:
                parts.append(f"رسوم الإرجاع في الفاتورة {ret_invoice}.")
            if ret_reason:
                parts.append(f"السبب: {ret_reason}.")

        if effective in ("cancelled", "canceled"):
            if cancel_type == "pre_shipment":
                parts.append("تم إلغاء الطلب قبل الشحن.")
            elif cancel_type == "post_shipment":
                parts.append("تم إلغاء الطلب بعد الشحن.")
            if cancel_reason:
                parts.append(f"السبب: {cancel_reason}.")
            if ret_date:
                parts.append(f"تاريخ الإرجاع: {ret_date}.")
            if ret_charges:
                rc_text = f"{ret_charges} {currency}".strip()
                parts.append(f"رسوم الإرجاع: {rc_text}.")
            if ret_invoice:
                parts.append(f"رسوم الإرجاع في الفاتورة {ret_invoice}.")
            if not ret_charges and cancel_type == "pre_shipment":
                parts.append("لم يتم تطبيق أي رسوم على هذا الطلب.")

        return " ".join(parts)

    # --- English (default) ---
    parts = []
    status_text = STATUS_EN.get(effective, effective)
    parts.append(f"Your order #{oid} {status_text}.")

    if expected:
        parts.append(f"Expected delivery: {expected}.")
    if tracking:
        parts.append(f"Tracking number: {tracking}.")
    if payment:
        pay_text = "has been paid" if payment in ("paid", "completed") else payment
        parts.append(f"Payment {pay_text}.")
    if invoice:
        parts.append(f"This order is reflected in invoice {invoice}.")

    if effective in ("returned",) or ret_status in ("returned",):
        if ret_date:
            parts.append(f"It was returned on {ret_date}.")
        if ret_charges:
            rc_text = f"{ret_charges} {currency}".strip()
            parts.append(f"Return charges of {rc_text} have been applied.")
        if ret_invoice:
            parts.append(f"Return charges are included in invoice {ret_invoice}.")
        if ret_reason:
            parts.append(f"Reason: {ret_reason}.")

    if effective in ("cancelled", "canceled"):
        if cancel_type == "pre_shipment":
            parts.append("It was cancelled before shipping.")
        elif cancel_type == "post_shipment":
            parts.append("It was shipped but later returned and cancelled.")
        if cancel_reason:
            parts.append(f"Reason: {cancel_reason}.")
        if ret_date:
            parts.append(f"It was returned on {ret_date}.")
        if ret_charges:
            rc_text = f"{ret_charges} {currency}".strip()
            parts.append(f"Return charges of {rc_text} were applied.")
        if ret_invoice:
            parts.append(f"Return charges are included in invoice {ret_invoice}.")
        if not ret_charges and cancel_type == "pre_shipment":
            parts.append("No charges were applied.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Invoice + tracking intents and formatters
# ---------------------------------------------------------------------------

_ORDER_INVOICE_MARKERS = (
    "invoice for order",
    "invoice of order",
    "which invoice",
    "order invoice",
    "invoice for this order",
    "order ka invoice",
    "is order ka invoice",
    "order ki invoice",
    "فاتورة الطلب",
    "فاتورة هذا الطلب",
)
_LATEST_INVOICE_MARKERS = (
    "my invoice",
    "my latest invoice",
    "latest invoice",
    "current invoice",
    "recent invoice",
    "last invoice",
    "meri invoice",
    "meri latest invoice",
    "meri recent invoice",
    "آخر فاتورة",
    "فاتورتي",
    "الفاتورة الحالية",
)
_ALL_INVOICES_MARKERS = (
    "all my invoices",
    "all invoices",
    "invoice history",
    "all invoice",
    "how many invoices",
    "total invoices",
    "meri sari invoices",
    "saari invoices",
    "sari invoice",
    "kitni invoices",
    "kitne invoices",
    "كل فواتيري",
    "جميع الفواتير",
    "كم فاتورة",
)
_TRACKING_INTENT_MARKERS = (
    "track",
    "tracking",
    "شحنة",
    "تتبع",
    "tracking number",
    "tracking id",
)


def _looks_like_invoice_for_order(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if any(m in t for m in _ORDER_INVOICE_MARKERS):
        return True
    # Roman Urdu / short follow-ups right after order context (not caught by English phrases).
    ru_invoice_followups = (
        "against invoice",
        "iske against",
        "iskay against",
        "is kay against",
        "is order ka invoice",
        "us order ka invoice",
        "is ka invoice",
        "us ka invoice",
        "order ka invoice bata",
        "order ki invoice bata",
        "invoice batao",
        "invoice btao",
        "invoice bataye",
        "invoice detail",
        "invoice details",
        "invoice dikha",
        "invoice dekha",
        "fatura",
    )
    if any(m in t for m in ru_invoice_followups):
        return True
    if "invoice" in t and any(
        w in t for w in ("bata", "btao", "batay", "dekha", "dikha", "against", "ke liye", "keliye")
    ):
        return True
    return False


def _looks_like_latest_invoice(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if _looks_like_invoice_for_order(text):
        return False
    if _looks_like_all_invoices(text):
        return False
    return any(m in t for m in _LATEST_INVOICE_MARKERS)


def _looks_like_all_invoices(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    return any(m in t for m in _ALL_INVOICES_MARKERS)


# Typical Arabia tracking IDs: PT + digits, or long digit-only refs.
_TRACKING_ID_RE = re.compile(
    r"\b((?:PT|AWB|PK|UAE|KSA|SP|SA|AE)[A-Z0-9]{4,})\b",
    re.IGNORECASE,
)


def _extract_tracking_id_from_message(text: str) -> str:
    """Pull out an explicit tracking reference (e.g. PT25252071) if present."""
    if not text:
        return ""
    m = _TRACKING_ID_RE.search(text)
    if m:
        return m.group(1).strip()
    # Fallback: "tracking number 11770000002800" → the trailing digit run.
    t = text.lower()
    if "tracking" in t:
        m2 = re.search(r"\btracking(?:\s+(?:number|no|id|#))?\s*[:#]?\s*([A-Z0-9\-]{6,})", text, re.IGNORECASE)
        if m2:
            return m2.group(1).strip()
    return ""


def _looks_like_tracking_by_id(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    has_intent = any(m in t for m in _TRACKING_INTENT_MARKERS)
    return bool(has_intent and _extract_tracking_id_from_message(text))


def _extract_invoice(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap either `{invoice: {...}}` or a plain invoice dict."""
    if not isinstance(payload, dict):
        return {}
    inner = payload.get("invoice")
    if isinstance(inner, dict):
        return inner
    return payload


def _format_invoice_sentence(
    lang: str, inv: Dict[str, Any], *, for_order: Optional[str] = None
) -> str:
    """Build one natural sentence describing an invoice.

    for_order: when provided the sentence is framed as "Order #X is in the
    invoice dated DATE ..." otherwise "Your latest invoice dated DATE ...".
    """
    date = _pick(inv, "date")
    payable = _pick(inv, "net_payable", "payable")
    pay_status = _pick(inv, "pay_status")
    items = _pick(inv, "no_of_items")
    delivered = _pick(inv, "d_pkgs")
    returned = _pick(inv, "r_pkgs")
    penalties = _pick(inv, "penalties")
    orders_field = inv.get("order_ids")
    if isinstance(orders_field, list):
        order_count = len([x for x in orders_field if x])
    else:
        order_count = 0

    paid = pay_status.strip().lower() in ("yes", "paid", "true", "1")

    if lang == "roman_urdu":
        head = (
            (f"Aapka order #{for_order} {date} wali invoice mein hai" if date
             else f"Aapka order #{for_order} ek invoice mein hai")
            if for_order
            else (f"Aapki latest invoice {date} ki hai" if date else "Aapki latest invoice tayar hai")
        )
        bits: List[str] = []
        if items:
            bits.append(f"{items} items")
        if delivered:
            bits.append(f"{delivered} delivered")
        if returned:
            bits.append(f"{returned} returned")
        tail: List[str] = []
        if bits:
            tail.append("(" + ", ".join(bits) + ")")
        if payable:
            status_word = "paid ho chuki" if paid else "abhi unpaid"
            tail.append(f"payable {payable} AED, {status_word}")
        if penalties and penalties not in ("0", "0.00", "0.0"):
            tail.append(f"penalties {penalties} AED")
        if order_count and not for_order:
            tail.append(f"{order_count} orders shamil hain")
        out = head + ((" " + ", ".join(tail)) if tail else "")
        return out.rstrip(",. ") + "."

    if lang == "arabic":
        head = (
            (f"طلبك رقم #{for_order} ضمن فاتورة بتاريخ {date}" if date
             else f"طلبك رقم #{for_order} ضمن فاتورتك")
            if for_order
            else (f"أحدث فاتورة لك بتاريخ {date}" if date else "إليك أحدث فاتورة لك")
        )
        bits = []
        if items:
            bits.append(f"عدد العناصر: {items}")
        if delivered:
            bits.append(f"تم توصيل {delivered}")
        if returned:
            bits.append(f"تم إرجاع {returned}")
        tail = []
        if bits:
            tail.append("(" + "، ".join(bits) + ")")
        if payable:
            status_word = "تم الدفع" if paid else "غير مدفوعة حالياً"
            tail.append(f"المبلغ المستحق {payable} درهم، {status_word}")
        if penalties and penalties not in ("0", "0.00", "0.0"):
            tail.append(f"الغرامات: {penalties} درهم")
        if order_count and not for_order:
            tail.append(f"تشمل {order_count} طلبات")
        out = head + ((" " + "، ".join(tail)) if tail else "")
        return out.rstrip(",. ") + "."

    # English (default)
    head = (
        (f"Your order #{for_order} is in the invoice dated {date}" if date
         else f"Your order #{for_order} is on one of your invoices")
        if for_order
        else (f"Your latest invoice is dated {date}" if date else "Here is your latest invoice")
    )
    bits = []
    if items:
        bits.append(f"{items} items")
    if delivered:
        bits.append(f"{delivered} delivered")
    if returned:
        bits.append(f"{returned} returned")
    tail = []
    if bits:
        tail.append("(" + ", ".join(bits) + ")")
    if payable:
        status_word = "paid" if paid else "currently unpaid"
        tail.append(f"payable {payable} AED, {status_word}")
    if penalties and penalties not in ("0", "0.00", "0.0"):
        tail.append(f"penalties {penalties} AED")
    if order_count and not for_order:
        tail.append(f"covering {order_count} orders")
    out = head + ((" " + ", ".join(tail)) if tail else "")
    return out.rstrip(",. ") + "."


def _format_all_invoices_sentence(lang: str, payload: Dict[str, Any]) -> str:
    """Summary line for `all=1` invoices listing."""
    total = payload.get("total")
    invs = payload.get("invoices") if isinstance(payload.get("invoices"), list) else []
    count = total if isinstance(total, int) else len(invs)
    latest: Dict[str, Any] = invs[0] if invs and isinstance(invs[0], dict) else {}
    latest_inv = _extract_invoice(latest) if isinstance(latest, dict) else {}
    latest_date = _pick(latest_inv, "date") if latest_inv else ""
    if lang == "roman_urdu":
        base = f"Aapke account par kul {count} invoices hain" if count else "Abhi aapke account par koi invoice nahi hai"
        if latest_date:
            base += f"; sabse recent {latest_date} ki hai"
        return base.rstrip(",. ") + "."
    if lang == "arabic":
        base = f"لديك إجمالي {count} فاتورة على حسابك" if count else "لا توجد فواتير على حسابك حالياً"
        if latest_date:
            base += f"؛ آخرها بتاريخ {latest_date}"
        return base.rstrip(",. ") + "."
    base = f"You have {count} invoices on your account in total" if count else "There are no invoices on your account right now"
    if latest_date:
        base += f"; the most recent is dated {latest_date}"
    return base.rstrip(",. ") + "."


def _format_tracking_sentence(lang: str, tr: Dict[str, Any]) -> str:
    """Render a /tracking/{id} response as a single sentence."""
    tid = _pick(tr, "shipped_ref", "tracking_number", "tracking_id") or _pick(tr, "id")
    status = _pick(tr, "tracking_result", "status")
    phrase = _humanize_status(status, lang) if status else ""
    if lang == "roman_urdu":
        head = f"Tracking number {tid}" if tid else "Yeh tracking number"
        tail = f" {phrase}" if phrase else (f" ki status: {status}" if status else " ki status abhi available nahi hai")
        return (head + " abhi" + (tail if phrase else tail)).rstrip(",. ") + "."
    if lang == "arabic":
        head = f"رقم التتبع {tid}" if tid else "هذا الشحنة"
        tail = f" {phrase}" if phrase else (f" الحالة: {status}" if status else " الحالة غير متوفرة حالياً")
        return (head + tail).rstrip(",. ") + "."
    head = f"Tracking {tid}" if tid else "That tracking reference"
    tail = f" {phrase}" if phrase else (f" — status: {status}" if status else " is not currently available")
    return (head + tail).rstrip(",. ") + "."


# ---------------------------------------------------------------------------
# invoice-by-id, invoices-in-period, orders-in-period
# ---------------------------------------------------------------------------

_INVOICE_ID_RE = re.compile(
    r"invoice(?:\s+(?:id|number|no\.?))?\s*[:#]?\s*(\d{1,12})\b",
    re.IGNORECASE,
)

def _extract_invoice_id(text: str) -> str:
    m = _INVOICE_ID_RE.search(text or "")
    return m.group(1).strip() if m else ""


def _looks_like_invoice_by_id(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if _looks_like_invoice_for_order(text):
        return False
    if "order" in t:
        # Leave order-centric queries for invoice-for-order / order-status.
        return False
    if _parse_date_range(text):
        return False
    return bool(_extract_invoice_id(text))


def _looks_like_invoices_in_period(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if _looks_like_invoice_for_order(text):
        return False
    has_invoice_word = ("invoice" in t) or ("فاتور" in t)
    if not has_invoice_word:
        return False
    return _parse_date_range(text) is not None


_CANT_FIND_ORDER_MARKERS = (
    "don't have",
    "dont have",
    "do not have",
    "can't find",
    "cant find",
    "cannot find",
    "don't know",
    "dont know",
    "do not know",
    "not sure",
    "forgot",
    "lost it",
    "lost my order",
    "i don't",
    "i dont",
    "no email",
    "no order number",
    "no order id",
    "nahi pata",
    "nahi mil raha",
    "nahi mil rahi",
    "bhool gaya",
    "bhool gayi",
    "yaad nahi",
    "pata nahi",
    "mujhe nahi pata",
    "لا أعرف",
    "لا اعرف",
    "لا أتذكر",
    "لا اتذكر",
    "ليس لدي",
    "ما عندي",
)


def _wants_cannot_find_order_help(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if _is_likely_email(t) or _is_likely_order_id_only(t):
        return False
    return any(m in t for m in _CANT_FIND_ORDER_MARKERS)


def _looks_like_orders_in_period(text: str) -> bool:
    return looks_like_orders_in_period_message(text)


def _wants_orders_csv_file(text: str) -> bool:
    t = (text or "").lower()
    if "csv" in t or "spreadsheet" in t:
        return True
    if "export" in t and "order" in t:
        return True
    if "download" in t and "order" in t:
        return True
    if "excel" in t and ("file" in t or "sheet" in t):
        return True
    return False


def _safe_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _sum_profit(orders: List[Dict[str, Any]]) -> int:
    return sum(_safe_int(o.get("profit")) for o in orders if isinstance(o, dict))


def _orders_period_row(o: Dict[str, Any]) -> str:
    oid = _pick(o, "id", "order_id", "order_number") or "?"
    date_str = _pick(o, "createdon", "order_date", "created_at") or ""
    date_short = date_str.split(" ")[0] if date_str else ""
    details = _pick(o, "details", "product_summary")
    if details and len(details) > 60:
        details = details[:57].rstrip() + "…"
    profit = _pick(o, "profit")
    amount = _pick(o, "shipping_charges")
    head_bits: List[str] = [f"#{oid}"]
    if date_short:
        head_bits.append(f"({date_short})")
    head = " ".join(head_bits)
    tail_bits: List[str] = []
    if details:
        tail_bits.append(details)
    money_bits: List[str] = []
    if amount:
        money_bits.append(f"{amount} AED shipping")
    if profit:
        money_bits.append(f"{profit} AED profit")
    if money_bits:
        tail_bits.append(", ".join(money_bits))
    if tail_bits:
        return f"{head} — " + ", ".join(tail_bits)
    return head


def _format_orders_in_period(
    lang: str, orders: List[Dict[str, Any]], label: str, max_rows: int = 5
) -> str:
    """Header sentence + up to `max_rows` compact rows for an orders listing."""
    count = len(orders)
    profit = _sum_profit(orders)
    head: str
    if count == 0:
        if lang == "roman_urdu":
            return f"{label} mein koi order nahi mila."
        if lang == "arabic":
            return f"لا توجد طلبات خلال {label}."
        return f"You had no orders in {label}."

    if lang == "roman_urdu":
        head = f"{label} mein aapke {count} order(s) hain"
        if profit:
            head += f", total profit {profit} AED"
        head += "."
    elif lang == "arabic":
        head = f"لديك {count} طلب خلال {label}"
        if profit:
            head += f"، إجمالي الأرباح {profit} درهم"
        head += "."
    else:
        head = f"You have {count} order{'s' if count != 1 else ''} in {label}"
        if profit:
            head += f", total profit {profit} AED"
        head += "."

    rows = [_orders_period_row(o) for o in orders[:max_rows]]
    tail = ""
    if count > max_rows:
        remainder = count - max_rows
        if lang == "roman_urdu":
            tail = f"\n+ {remainder} aur — date range ya month badalne ke liye dobara pooch lein."
        elif lang == "arabic":
            tail = f"\n+ {remainder} المزيد — يمكنك تضييق النطاق الزمني لعرض المزيد."
        else:
            tail = f"\n+ {remainder} more — narrow the date range to see others."
    return head + "\n" + "\n".join(f"• {row}" for row in rows) + tail


def _format_invoices_in_period(
    lang: str, payload: Dict[str, Any], label: str
) -> str:
    invs = payload.get("invoices") if isinstance(payload.get("invoices"), list) else []
    count = len(invs)
    if count == 0 and isinstance(payload.get("invoice"), dict):
        invs = [payload]
        count = 1
    if count == 0:
        if lang == "roman_urdu":
            return f"{label} mein koi invoice nahi mila."
        if lang == "arabic":
            return f"لا توجد فواتير خلال {label}."
        return f"You had no invoices in {label}."
    latest_raw = invs[0] if isinstance(invs[0], dict) else {}
    latest = _extract_invoice(latest_raw) if latest_raw else {}
    latest_date = _pick(latest, "date") if latest else ""
    if lang == "roman_urdu":
        out = f"{label} mein aapke {count} invoice(s) hain"
        if latest_date:
            out += f"; sabse recent {latest_date} ki hai"
        return out.rstrip(",. ") + "."
    if lang == "arabic":
        out = f"لديك {count} فاتورة خلال {label}"
        if latest_date:
            out += f"؛ آخرها بتاريخ {latest_date}"
        return out.rstrip(",. ") + "."
    out = f"You have {count} invoice{'s' if count != 1 else ''} in {label}"
    if latest_date:
        out += f"; the most recent is dated {latest_date}"
    return out.rstrip(",. ") + "."


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
    whatsapp_image_outbound: Optional[List[Dict[str, str]]] = None
    """Each item: {"image_url": str, "caption": str} for Meta image messages (WhatsApp only)."""
    whatsapp_document_outbound: Optional[List[Dict[str, Any]]] = None
    """Each item: ``content_bytes`` (preferred, uploaded to Meta) or ``document_url`` + ``filename`` + optional ``caption``."""
    whatsapp_text_after_images: Optional[Union[str, List[str]]] = None
    """Follow-up text(s) after image(s) on WhatsApp. Pass a list to emit each
    string as its own message (e.g. list + footer first, then a separate
    \"you might also want to ask…\" suggestion bubble)."""
    suppress_kb_wrap: bool = False
    """If True, the orchestrator MUST NOT append the kb_wrap footer even when
    ``skip_store_api and bot.last_reply_used_kb``. Used by the trending flow's
    fallback path so bail-to-LLM replies don't accidentally leak website /
    support boilerplate while we're still inside a trending conversation."""


def _any_agent_available(db: Session, tenant_id: int, team: Optional[str] = None) -> bool:
    """Lazy wrapper to avoid circular import at module load time."""
    from services.agent_routing_service.api import any_agent_available  # noqa: PLC0415
    return any_agent_available(db, tenant_id, team=team)


def _build_handoff_unavailable_reply(db: Session, tenant_id: int, lang: str) -> str:
    """
    Return the fully-formatted handoff_unavailable message with an optional schedule line.
    Used when we know up-front that no agents are online so we can skip the 'connecting…' loop.
    """
    template = _t(lang, MSGS["handoff_unavailable"])
    schedule_line = ""
    sched = (
        db.query(TenantSchedule)
        .filter(TenantSchedule.tenant_id == tenant_id)
        .first()
    )
    if sched and sched.working_days and sched.start_time and sched.end_time:
        schedule_line = format_tenant_schedule_line_for_handoff(
            lang, sched.working_days, sched.start_time, sched.end_time
        )
    try:
        return template.format(schedule=schedule_line)
    except (KeyError, IndexError):
        return template.replace("{schedule}", schedule_line)


async def process_customer_bot_message(
    *,
    db: Session,
    conversation: Optional[Conversation],
    user_message: str,
    tenant_id: int,
    orchestrator: AIOrchestrator,
    phone: Optional[str] = None,
    channel: str = "web",
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
            whatsapp_image_outbound=None,
            whatsapp_document_outbound=None,
            whatsapp_text_after_images=None,
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
            whatsapp_image_outbound=None,
            whatsapp_document_outbound=None,
            whatsapp_text_after_images=None,
        )

    meta = _normalize_meta(conversation)
    suppress_escalation_after_agent_close = bool(
        meta.get("awaiting_first_customer_after_agent_close")
    )
    flow = _get_flow(meta)
    meta, flow = _apply_inactivity_bot_reset(db, conversation, meta, flow)
    flow = _migrate_legacy_bot_flow(flow)
    flow, verification_expired_this_turn = _apply_verification_expiry(flow)

    mem_id = normalize_memory_scope_id(phone, conversation)
    if mem_id and not (flow or {}).get("customer_kind"):
        _ck_mem = ConversationMemory.get_bot_customer_kind(mem_id)
        if _ck_mem in ("new", "existing"):
            flow = {**(flow or {}), "customer_kind": _ck_mem}

    lang = await orchestrator.detect_language(user_message)
    if not (user_message or "").strip():
        lang = "roman_urdu"
    # Sticky language for short/numeric inputs (e.g. menu digits) — but never
    # override on reset commands; those should detect language fresh.
    _stripped_msg = (user_message or "").strip()
    if not (is_slash_reset_command(_stripped_msg) or wants_bot_flow_reset(_stripped_msg) or _looks_like_greeting(_stripped_msg)):
        sticky = flow.get("lang")
        if isinstance(sticky, str) and sticky.strip():
            t0 = (user_message or "").strip()
            if t0 and (
                len(t0) <= 8
                or bool(re.fullmatch(r"[\d\-\s#]+", t0))
            ):
                lang = sticky
    step = flow.get("step") or "conversational"
    flow_lang = lang
    _um_early = (user_message or "").strip()
    if mem_id and _um_early:
        _memory_apply_entities(mem_id, _um_early)

    store_client = StoreIntegrationClient()
    escalate_for_ai_turn = (
        False
        if suppress_escalation_after_agent_close
        else await orchestrator.should_escalate(user_message)
    )

    def save(
        f: Dict[str, Any],
        reply: str,
        team: Optional[str] = None,
        esc: bool = False,
        skip_api: Optional[bool] = None,
        wa_images: Optional[List[Dict[str, str]]] = None,
        wa_text_after: Optional[Union[str, List[str]]] = None,
        wa_documents: Optional[List[Dict[str, Any]]] = None,
    ):
        f["lang"] = flow_lang
        if skip_api is None:
            skip_api = _default_skip_store_api(f)
        return BotFlowResult(
            reply_text=reply,
            merge_metadata=_merge_flow(meta, f),
            use_ai=False,
            ai_user_message=user_message,
            skip_store_api=bool(skip_api),
            assign_team=team,
            escalate=esc,
            handled=True,
            whatsapp_image_outbound=wa_images,
            whatsapp_document_outbound=wa_documents,
            whatsapp_text_after_images=wa_text_after,
        )

    def ai_forward(
        msg: str,
        f: Dict[str, Any],
        skip_api: bool,
        *,
        suppress_kb_wrap: bool = False,
    ):
        deterministic = _deterministic_kb_answer(msg, flow_lang)
        if deterministic:
            if suppress_kb_wrap:
                return save(f, deterministic, skip_api=True)
            return save(
                f,
                format_kb_reply(flow_lang, deterministic),
                skip_api=True,
            )
        logger.debug(
            "customer_bot_flow ai_forward skip_store_api=%s suppress_kb_wrap=%s preview=%s",
            skip_api,
            suppress_kb_wrap,
            (msg or "")[:160].replace("\n", " "),
        )
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
            whatsapp_image_outbound=None,
            whatsapp_document_outbound=None,
            whatsapp_text_after_images=None,
            suppress_kb_wrap=suppress_kb_wrap,
        )

    if (
        channel == "whatsapp"
        and mem_id
        and flow.get("verified")
        and _wants_orders_csv_file(user_message)
    ):
        sid_csv = _flow_merchant_seller_id(flow)
        if sid_csv:
            win = ConversationMemory.get_orders_export_window(mem_id)
            if not win:
                pr = _parse_date_range(user_message)
                if pr:
                    win = {
                        "date_from": pr.get("date_from"),
                        "date_to": pr.get("date_to"),
                        "label": pr.get("label"),
                    }
            if win and win.get("date_from") and win.get("date_to"):
                df = str(win["date_from"])[:10]
                dt = str(win["date_to"])[:10]
                try:
                    from services.orders_export_service.exporter import build_orders_csv_export_bytes

                    body, n, trunc = await build_orders_csv_export_bytes(
                        store_client, str(sid_csv), df, dt
                    )
                    if n <= 0:
                        return save(
                            {**flow, "step": "conversational"},
                            "I could not find any orders in that date range to export.",
                        )
                    max_wa = 100 * 1024 * 1024
                    if len(body) > max_wa:
                        return save(
                            {**flow, "step": "conversational"},
                            "The export is too large to send on WhatsApp (over 100 MB). Please ask support for a split export or a shorter date range.",
                        )
                    fname = f"orders_{sid_csv}_{df}_to_{dt}.csv".replace(" ", "_")[:200]
                    cap = f"Orders export ({n} orders)"
                    if trunc:
                        cap += " (capped at 5000 rows)"
                    reply = (
                        "I have prepared a CSV with your orders. Tap the file below to open it in WhatsApp."
                    )
                    if flow_lang == "roman_urdu":
                        reply = "Main ne CSV file bana di hai. Neeche file par tap kar ke WhatsApp mein khol lein."
                    elif flow_lang == "arabic":
                        reply = "جهزت لك ملف CSV. اضغط على الملف أدناه لفتحه في واتساب."
                    doc_item: Dict[str, Any] = {
                        "content_bytes": body,
                        "filename": fname,
                        "caption": cap,
                        "mime_type": "text/csv",
                    }
                    try:
                        from services.media_storage.r2 import is_r2_configured, presign_get, put_bytes
                        from services.orders_export_service.csv_builder import object_key_for_orders_csv

                        if is_r2_configured():
                            key = object_key_for_orders_csv(str(sid_csv))
                            put_bytes(key, body, "text/csv")
                            doc_item["document_url"] = presign_get(key, 86400)
                    except Exception:
                        logger.warning("Optional R2 presign for CSV fallback skipped", exc_info=True)
                    return save(
                        {**flow, "step": "conversational"},
                        reply,
                        wa_documents=[doc_item],
                    )
                except Exception:
                    logger.exception("WhatsApp orders CSV export failed")
                    return save(
                        {**flow, "step": "conversational"},
                        "Sorry, I could not generate the file. Please try again in a moment.",
                    )

    async def submit_existing_email(flow_in: Dict[str, Any], email_in: str) -> BotFlowResult:
        """Send OTP (or jump to mobile) after the customer supplies a registration email."""
        email_norm = (email_in or "").strip().lower()
        if not _is_likely_email(email_norm):
            return save(
                {**flow_in, "step": "existing_awaiting_email", "customer_kind": "existing"},
                _t(flow_lang, MSGS["email_invalid"]),
            )
        if bool(getattr(settings, "customer_bot_skip_email_otp", False)):
            logger.info(
                "Verification flow: OTP bypassed (CUSTOMER_BOT_SKIP_EMAIL_OTP=true); "
                "jumping straight to mobile for %s",
                email_norm,
            )
            f = {
                **flow_in,
                "pending_email": email_norm,
                "verified": False,
                "step": "existing_awaiting_mobile",
                "customer_kind": "existing",
                "lang": flow_lang,
            }
            return save(f, _t(flow_lang, MSGS["ask_mobile"]))
        logger.info("Verification flow: sending code to %s", email_norm)
        sent = await store_client.send_verification_code(email_norm)
        logger.info(
            "Verification flow: send_verification_code result for %s = %s",
            email_norm,
            sent,
        )
        if not sent:
            return save(flow_in, _t(flow_lang, MSGS["verify_send_error"]))
        f = {
            **flow_in,
            "pending_email": email_norm,
            "verified": False,
            "step": "existing_awaiting_verification_code",
            "customer_kind": "existing",
            "lang": flow_lang,
        }
        return save(f, _t(flow_lang, MSGS["code_sent"]).format(email=email_norm))

    def _maybe_escape_trending_for_order_intent(
        msg_text: str,
    ) -> Optional[BotFlowResult]:
        """Break out of the trending flow when the user clearly asks about an order.

        Returns ``None`` when the message is NOT an order/account ask — the
        caller should continue with its normal trending dispatch in that case.

        When it IS an order ask (e.g. "i want order details", "where is my
        order", or a bare order id) we:
          1. clear trending state (``_conversation_bail_from_trending``),
          2. pre-stash ``pending_order_ref`` if the message carried an id,
          3. route to ``existing_awaiting_email`` with ``verify_reason="order"``
             so the next turn continues the existing-customer identity path —
             unless the customer is already verified, in which case we jump
             straight to an order lookup or the ``existing_awaiting_order_id``
             prompt. This mirrors the same branch used by the conversational
             handler so behavior is consistent regardless of where the user
             triggered the escape from.
        """
        if not (
            _looks_like_order_status_question(msg_text)
            or _is_likely_order_id_only(msg_text)
            or _looks_like_account_question(msg_text)
        ):
            return None
        base = _conversation_bail_from_trending(flow, flow_lang)
        pre_ref = ""
        if _is_likely_order_id_only(msg_text):
            pre_ref = re.sub(r"[^\d\-#]", "", (msg_text or "").strip()) or (msg_text or "").strip()
        else:
            pre_ref = (_extract_order_id_from_message(msg_text, phone) or "").strip()
        if base.get("verified"):
            base["step"] = "existing_awaiting_order_id"
            base["pending_order_ref"] = None
            prompt_key = "ask_order"
            return save(base, _t(flow_lang, MSGS[prompt_key]))
        reason = "order" if _looks_like_order_status_question(msg_text) or _is_likely_order_id_only(msg_text) else "account"
        intro_key = "order_verify_intro" if reason == "order" else "account_verify_intro"
        f2, msg2 = _existing_identity_entry(
            base,
            flow_lang,
            verify_reason=reason,
            pending_order_ref=pre_ref or None,
            intro_key=intro_key,
        )
        return save(f2, msg2)

    def _show_trending_for_country(
        cc: str,
        base_flow: Dict[str, Any],
        msg_text: str,
        *,
        mode: str = "trending",
    ) -> BotFlowResult:
        """Fetch and display trending/non-trending products for *cc*.

        ``mode`` selects the data source and the template set:
            - ``"trending"`` → :func:`list_active_trending_for_country` + ``trending_*`` copy.
            - ``"non_trending"`` → :func:`list_active_non_trending_for_country`
              + ``non_trending_*`` copy.
        """
        wanted_category = _parse_trending_category(msg_text)
        if mode == "non_trending":
            items_all = list_active_non_trending_for_country(db, tenant_id, cc)
        else:
            items_all = list_active_trending_for_country(db, tenant_id, cc)
        visible = _trending_visible_list(items_all, wanted_category)
        offset = 0
        page = visible[offset : offset + TRENDING_PAGE_SIZE]
        if not page:
            nf = {**base_flow, "step": "trending_awaiting_country", "lang": flow_lang}
            for k in TRENDING_STATE_KEYS:
                nf.pop(k, None)
            nf["trending_mode"] = mode
            if wanted_category:
                no_key = _trending_tpl(mode, "trending_no_products_category")
                no_msg = _t(flow_lang, MSGS[no_key]).format(
                    country=_trending_footer_country_label(cc),
                    category=wanted_category,
                )
            else:
                no_key = _trending_tpl(mode, "trending_no_products")
                no_msg = _t(flow_lang, MSGS[no_key]).format(
                    country=_trending_footer_country_label(cc)
                )
            retry = _t(flow_lang, MSGS["trending_country_retry"])
            # Offer a few quick next-step suggestions so the empty-catalogue
            # fallback still feels conversational (matches the LLM-runner UX
            # where every turn ends with a short suggestion bubble).
            followup_suggestions = _empty_catalog_followups(cc, mode, flow_lang)
            followup_text = (
                "\n".join(f"• {s}" for s in followup_suggestions)
                if followup_suggestions
                else ""
            )
            ch = (channel or "").strip().lower()
            if ch == "whatsapp" and followup_text:
                return save(
                    nf,
                    f"{no_msg}\n\n{retry}",
                    wa_text_after=followup_text,
                )
            full = f"{no_msg}\n\n{retry}"
            if followup_text:
                full = f"{full}\n\n{followup_text}"
            return save(nf, full)
        has_more = offset + len(page) < len(visible)
        fk, needs_c = _trending_footer_template_key(
            first_batch=True, has_more=has_more, mode=mode,
        )
        footer = (
            _t(flow_lang, MSGS[fk]).format(country=_trending_footer_country_label(cc))
            if needs_c
            else _t(flow_lang, MSGS[fk])
        )
        nf = {
            **base_flow,
            "step": "trending_showing_products",
            "lang": flow_lang,
            "trending_country": cc,
            "trending_category": wanted_category,
            "trending_products_all": items_all,
            "trending_products_cache": page,
            "trending_offset": offset,
            "trending_mode": mode,
        }
        body = _trending_inbox_and_web_body(
            flow_lang, cc, page,
            category=wanted_category, start_rank=1, is_more_batch=False,
            mode=mode,
        )
        base_reply = f"{body}\n\n{footer}".strip()
        followup = _trending_followup_block(flow_lang, cc, mode=mode).lstrip()
        full_reply = f"{base_reply}\n\n{followup}".strip() if followup else base_reply
        wa_imgs: Optional[List[Dict[str, str]]] = None
        wa_aft: Optional[Union[str, List[str]]] = None
        _ch = (channel or "web").strip().lower()
        logger.info(
            "trending show: mode=%s country=%s total_rows=%d visible=%d page_size=%d",
            mode, cc, len(items_all), len(visible), len(page),
        )
        if _ch == "whatsapp":
            wa_l: List[Dict[str, str]] = []
            no_u: List[str] = []
            for i, it in enumerate(page):
                row_imgs = _wa_images_for_trending_row(it, rank=offset + i + 1)
                logger.info(
                    "trending WA images: country=%s product=%s images=%d first_url=%s",
                    cc,
                    (it.get("product_name") or "")[:40],
                    len(row_imgs),
                    (row_imgs[0]["image_url"][:120] if row_imgs else "(none)"),
                )
                if row_imgs:
                    wa_l.extend(row_imgs)
                else:
                    cap = _wa_caption_for_trending_row(it, rank=offset + i + 1)
                    no_u.append(f"{cap}\n(no image URL — open chat on web for full list)")
            if wa_l:
                wa_imgs = wa_l
                # WhatsApp: images first, then list+footer as one bubble,
                # then the "you might also want to ask" block as a second
                # bubble so the user sees them as distinct messages.
                first_bubble = (
                    "\n\n".join([*no_u, base_reply]).strip() if no_u else base_reply
                )
                wa_aft = [first_bubble, followup] if followup else [first_bubble]
        return save(nf, full_reply, wa_images=wa_imgs, wa_text_after=wa_aft)

    async def _try_trending_llm(entry_intent: Optional[str] = None) -> Optional[BotFlowResult]:
        """Delegate this turn to the LLM-driven trending runner, when enabled.

        Returns ``None`` if the flag is off, the runner fails, or the current
        user is not in the allowlist — in which case the caller must continue
        with the deterministic path. On success, returns a ready-to-send
        ``BotFlowResult`` mirroring the legacy WhatsApp-split layout.

        ``entry_intent`` is a soft hint ("trending" or "non_trending") that
        callers set when they've already classified the turn as a trending
        entry request; it seeds the memory so the runner doesn't have to
        re-derive it from the raw message.
        """

        effective = _trending_llm_effective_mode(phone)
        if effective not in {"shadow", "on"}:
            return None

        # Build a compact conversation-history block so the LLM has context.
        # IMPORTANT: only include the customer's own recent messages — never
        # prior bot replies. Including bot replies in the history causes the
        # LLM to mimic its own past kb_wrap footers (website URLs, "type
        # support" etc.) into the trending runner's output, which is wrong.
        history_block = ""
        try:
            if conversation is not None and getattr(conversation, "id", None):
                rows = (
                    db.query(Message)
                    .filter(
                        Message.conversation_id == conversation.id,
                        Message.sender_type == "customer",
                    )
                    .order_by(desc(Message.id))
                    .limit(4)
                    .all()
                )
                rows.reverse()
                lines: List[str] = []
                for m in rows:
                    body = (m.content or "").strip().replace("\n", " ")
                    if len(body) > 200:
                        body = body[:197] + "…"
                    if body:
                        lines.append(f"Customer: {body}")
                history_block = "\n".join(lines)
        except Exception:  # pragma: no cover — history is best-effort
            logger.exception("trending_llm: loading history failed")

        seed_flow = dict(flow)
        if entry_intent in {"trending", "non_trending"}:
            seed_flow["trending_mode"] = entry_intent
            # Entry requests always start from a clean list; don't leak
            # shown_ids from a previous session.
            seed_flow["trending_shown_ids"] = []

        try:
            llm_result = await run_trending_llm(
                user_message=text,
                channel=ch,
                language=flow_lang,
                flow=seed_flow,
                db=db,
                tenant_id=tenant_id,
                conversation_history_block=history_block,
            )
        except Exception:
            logger.exception("trending_llm: runner crashed; falling back")
            return None

        if not llm_result.ok:
            logger.info("trending_llm: runner ok=False reason=%s — falling back",
                        llm_result.failure_reason)
            return None

        # Shadow mode: log what the LLM would have said but keep the legacy
        # reply the caller is about to build. Returning ``None`` triggers
        # the fallback path.
        if effective == "shadow":
            logger.info(
                "trending_llm_shadow: state=%s esc=%s chars=%d images=%d",
                llm_result.state,
                llm_result.escalate,
                len(llm_result.reply_text),
                len(llm_result.image_urls),
            )
            return None

        return _build_botflowresult_from_llm(llm_result)

    def _build_botflowresult_from_llm(llm_result: TrendingLLMResult) -> BotFlowResult:
        """Turn a ``TrendingLLMResult`` into the flow's BotFlowResult contract."""

        mem_patch = memory_to_flow_patch(llm_result.memory)
        nf = {**flow, "lang": flow_lang}

        if llm_result.state == "trending_awaiting_country":
            nf["step"] = "trending_awaiting_country"
        elif llm_result.state == "trending_active":
            nf["step"] = "trending_showing_products"
        else:
            # state == "done" — leave the trending flow.
            nf["step"] = "conversational"
            nf["intro_shown"] = bool(flow.get("intro_shown") or True)
            # Wipe trending-specific keys so the next turn starts clean.
            for k in TRENDING_STATE_KEYS:
                nf.pop(k, None)
            nf["trending_shown_ids"] = []

        # For active / awaiting states, persist the compact memory.
        if llm_result.state in {"trending_active", "trending_awaiting_country"}:
            nf.update(mem_patch)
            # Keep legacy mirrors (country/mode) in sync so downstream
            # helpers that still read them behave correctly.
            if mem_patch.get("trending_country"):
                nf["trending_country"] = mem_patch["trending_country"]
            nf["trending_mode"] = mem_patch.get("trending_mode") or "trending"

        # Compose the outgoing reply block. On web/portal we inline the
        # suggestions; on WhatsApp we split them into a second bubble so
        # the images → list → suggestions order stays readable.
        reply_text = llm_result.reply_text.strip()
        followup_text = ""
        if llm_result.suggested_followups:
            followup_lines = [f"• {line}" for line in llm_result.suggested_followups]
            followup_text = "\n".join(followup_lines)

        full_reply = (
            f"{reply_text}\n\n{followup_text}".strip() if followup_text else reply_text
        )

        wa_imgs: Optional[List[Dict[str, str]]] = None
        wa_after: Optional[Union[str, List[str]]] = None
        if ch == "whatsapp" and llm_result.shown_products:
            wa_l: List[Dict[str, str]] = []
            for i, it in enumerate(llm_result.shown_products):
                row_imgs = _wa_images_for_trending_row(it, rank=i + 1)
                if row_imgs:
                    wa_l.extend(row_imgs)
            if wa_l:
                wa_imgs = wa_l
                wa_after = [reply_text, followup_text] if followup_text else [reply_text]

        esc_llm = bool(llm_result.escalate) and not suppress_escalation_after_agent_close
        team = TEAM_NEW_CUSTOMER if esc_llm else None
        return save(
            nf,
            full_reply,
            team=team,
            esc=esc_llm,
            wa_images=wa_imgs,
            wa_text_after=wa_after,
        )

    ch = (channel or "web").strip().lower()
    text = (user_message or "").strip()

    if is_slash_reset_command(text):
        if mem_id:
            ConversationMemory.clear_all(mem_id)
        nf = _reset_bot_flow(flow_lang)
        return save(nf, _t(flow_lang, MSGS["greeting"]), skip_api=False)

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
            return save(restored, _t(flow_lang, _RESUME_CONTINUED_MSGS))
        if choice == "fresh":
            nf = _reset_bot_flow(flow_lang)
            return save(nf, _t(flow_lang, MSGS["greeting"]), skip_api=False)
        return save(flow, _t(flow_lang, _RESUME_CHOICE_MSGS))

    # Clear stale WhatsApp/web bot state (e.g. old "verified" session) — before handoff
    if wants_bot_flow_reset(text):
        if mem_id:
            ConversationMemory.clear_all(mem_id)
        nf = _reset_bot_flow(flow_lang)
        return save(nf, _t(flow_lang, MSGS["greeting"]), skip_api=False)

    # Global handoff: any step (incl. verification) when user asks for a human agent.
    # Suppressed on the first turn after an agent closes the chat so the bot can respond
    # before potentially re-routing again on the next turn.
    if wants_human_agent(text) and not suppress_escalation_after_agent_close:
        exp_team = flow.get("experience_team")
        if flow.get("verified"):
            team = exp_team or TEAM_BEGINNER
        else:
            team = TEAM_NEW_CUSTOMER
        # Check agent availability BEFORE saying "connecting" so we never enter
        # the awaiting_agent retry loop when no one is online.
        if not _any_agent_available(db, tenant_id, team=team):
            nf = {**flow, "step": "conversational", "intro_shown": True, "lang": flow_lang}
            return save(nf, _build_handoff_unavailable_reply(db, tenant_id, flow_lang), skip_api=True)
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

    # Sets step awaiting_resume_choice; reply uses _RESUME_CHOICE_MSGS.
    if not _flow_is_tabula_rasa(flow) and _looks_like_greeting(text):
        snap = {k: v for k, v in flow.items() if k != "resume_snapshot"}
        wb: Dict[str, Any] = {
            "step": "awaiting_resume_choice",
            "intro_shown": True,
            "lang": flow_lang,
            "resume_snapshot": snap,
        }
        return save(wb, _t(flow_lang, _RESUME_CHOICE_MSGS))

    # --- New / Existing customer selection ---
    if step == "awaiting_customer_type":
        if mem_id:
            _memory_store_pending_entry_menu(mem_id, text)
        choice = _parse_choice(
            text,
            {
                "1": "new", "new": "new", "new customer": "new", "n": "new",
                "first time": "new", "naya": "new", "naya customer": "new",
                "naya hun": "new", "pehli baar": "new", "pehli dafa": "new",
                "sign up": "new", "register": "new",
                "2": "existing", "existing": "existing", "old": "existing",
                "existing customer": "existing", "e": "existing",
                "old customer": "existing", "purana": "existing",
                "purana customer": "existing", "already": "existing",
                "already registered": "existing", "already have account": "existing",
                "sign in": "existing", "login": "existing", "log in": "existing",
                "returning": "existing", "returning customer": "existing",
                "pehle se hun": "existing", "account hai": "existing",
            },
        )
        if choice == "new":
            if mem_id:
                ConversationMemory.store_bot_customer_kind(mem_id, "new")
            nf = {
                **flow,
                "step": "conversational",
                "customer_kind": "new",
                "intro_shown": True,
                "lang": flow_lang,
            }
            pref = _memory_pending_ai_prefix(mem_id) if mem_id else ""
            if pref:
                if mem_id:
                    ConversationMemory.clear_pending_intent(
                        mem_id, promote_from_queue=True
                    )
                return ai_forward(pref + text, nf, skip_api=True)
            return save(nf, _t(flow_lang, MSGS["new_customer_welcome"]))
        if choice == "existing":
            if mem_id:
                ConversationMemory.store_bot_customer_kind(mem_id, "existing")
            f_ex, msg_ex = _existing_identity_entry(
                flow,
                flow_lang,
                verify_reason=None,
                pending_order_ref=None,
                intro_key="ask_email",
            )
            return save(f_ex, msg_ex)
        # Trending / sourcing before the entry LLM so phrases like "Give me trending products"
        # are never treated as an unclear 1/2 menu reply.
        if _wants_non_trending_products(text):
            llm_res = await _try_trending_llm(entry_intent="non_trending")
            if llm_res is not None:
                return llm_res
            inline_cc = _parse_trending_country_reply(text)
            base = {
                **flow,
                "customer_kind": flow.get("customer_kind") or "new",
                "intro_shown": True,
                "lang": flow_lang,
            }
            for k in TRENDING_STATE_KEYS:
                base.pop(k, None)
            base["trending_mode"] = "non_trending"
            if inline_cc:
                return _show_trending_for_country(inline_cc, base, text, mode="non_trending")
            base["step"] = "trending_awaiting_country"
            return save(base, _t(flow_lang, MSGS["trending_ask_country"]))
        if _wants_trending_products(text):
            llm_res = await _try_trending_llm(entry_intent="trending")
            if llm_res is not None:
                return llm_res
            inline_cc = _parse_trending_country_reply(text)
            base = {
                **flow,
                "customer_kind": flow.get("customer_kind") or "new",
                "intro_shown": True,
                "lang": flow_lang,
            }
            for k in TRENDING_STATE_KEYS:
                base.pop(k, None)
            base["trending_mode"] = "trending"
            if inline_cc:
                return _show_trending_for_country(inline_cc, base, text)
            base["step"] = "trending_awaiting_country"
            return save(base, _t(flow_lang, MSGS["trending_ask_country"]))
        if _wants_product_sourcing(text):
            product_hint = _extract_sourcing_product_name(text)
            has_bulk = bool(
                re.search(
                    r"\b\d{2,}\s*(?:piece|pieces|pcs|unit|units|qty)\b",
                    text.lower(),
                )
            )
            if has_bulk:
                nf = {
                    **flow,
                    "step": "awaiting_agent",
                    "customer_kind": "new",
                    "intro_shown": True,
                    "pending_handoff_team": TEAM_NEW_CUSTOMER,
                    "sourcing_product_name": product_hint,
                    "lang": flow_lang,
                }
                return save(
                    nf,
                    _t(flow_lang, MSGS["sourcing_bulk_handoff"]),
                    team=TEAM_NEW_CUSTOMER,
                    esc=True,
                )
            nf = {
                **flow,
                "step": "sourcing_collecting_details",
                "customer_kind": "new",
                "intro_shown": True,
                "sourcing_product_name": product_hint,
                "lang": flow_lang,
            }
            if product_hint:
                return save(
                    nf,
                    _t(flow_lang, MSGS["sourcing_with_product"]).format(product=product_hint),
                )
            return save(nf, _t(flow_lang, MSGS["sourcing_collect_details"]))
        # Simple acknowledgments (okay, good, fine, hmm, etc.) — just re-prompt the menu
        _ack_words = {
            "ok", "okay", "okey", "oki", "oki doki", "k",
            "good", "fine", "nice", "great", "cool", "alright", "right",
            "yes", "yeah", "yep", "yea", "yah", "haan", "han", "ji",
            "hmm", "hm", "hmmmm", "achha", "acha", "accha", "theek",
            "theek hai", "thik", "thik hai", "sahi", "sahi hai",
            "thanks", "thank you", "shukriya", "shukria",
            "no", "nahi", "nhi", "na",
        }
        if text.strip().lower() in _ack_words:
            return save(flow, _t(flow_lang, MSGS["customer_type_unclear"]))

        # Typo / FAQ on the 1–2 menu: LLM classifies new vs existing vs agent hours vs other.
        entry_intent = await _classify_entry_menu_intent_llm(text)
        if entry_intent == "agent_hours":
            sched_body = _entry_menu_agent_hours_reply(db, tenant_id, flow_lang)
            return save(flow, format_kb_reply(flow_lang, sched_body), skip_api=True)
        if entry_intent == "new":
            if mem_id:
                ConversationMemory.store_bot_customer_kind(mem_id, "new")
            nf = {
                **flow,
                "step": "conversational",
                "customer_kind": "new",
                "intro_shown": True,
                "lang": flow_lang,
            }
            pref = _memory_pending_ai_prefix(mem_id) if mem_id else ""
            if pref:
                if mem_id:
                    ConversationMemory.clear_pending_intent(
                        mem_id, promote_from_queue=True
                    )
                return ai_forward(pref + text, nf, skip_api=True)
            return save(nf, _t(flow_lang, MSGS["new_customer_welcome"]))
        if entry_intent == "existing":
            if mem_id:
                ConversationMemory.store_bot_customer_kind(mem_id, "existing")
            f_ex2, msg_ex2 = _existing_identity_entry(
                flow,
                flow_lang,
                verify_reason=None,
                pending_order_ref=None,
                intro_key="ask_email",
            )
            return save(f_ex2, msg_ex2)
        # Short menu-ish input but classifier could not decide — ask again (avoid empty LLM reply / fallback).
        if entry_intent == "other" and len(text.strip()) <= 48 and not _looks_like_free_text_question(text):
            if mem_id and ConversationMemory.get_pending_intent(mem_id):
                return save(flow, _t(flow_lang, MSGS["customer_type_menu_reminder"]))
            return save(flow, _t(flow_lang, MSGS["customer_type_unclear"]))

        # Free-text that isn't a choice → treat as new customer and answer directly
        nf = {
            **flow,
            "step": "conversational",
            "customer_kind": "new",
            "intro_shown": True,
            "lang": flow_lang,
        }
        if mem_id:
            ConversationMemory.store_bot_customer_kind(mem_id, "new")
        pref = _memory_pending_ai_prefix(mem_id) if mem_id else ""
        if pref:
            if mem_id:
                ConversationMemory.clear_pending_intent(mem_id, promote_from_queue=True)
            return ai_forward(pref + text, nf, skip_api=True)
        return ai_forward(text, nf, skip_api=True)

    if step == "trending_awaiting_country":
        # Order / account intent always beats trending — even mid-country-pick.
        # Bypass the LLM runner entirely for these since any "trending" reply
        # would be nonsensical for "give me order details" style messages.
        order_escape = _maybe_escape_trending_for_order_intent(text)
        if order_escape is not None:
            return order_escape
        llm_res = await _try_trending_llm()
        if llm_res is not None:
            return llm_res
        if _looks_like_greeting(text):
            nf, greet_reply = _exit_trending_for_greeting(flow, flow_lang)
            return save(nf, greet_reply, skip_api=False)
        if _is_natural_language(text) and _parse_trending_country_reply(text) is None:
            nf = _bail_to_conversational(flow, flow_lang)
            return ai_forward(
                text,
                nf,
                skip_api=_default_skip_store_api(nf),
                suppress_kb_wrap=True,
            )
        cc = _parse_trending_country_reply(text)
        if not cc:
            return save(flow, _t(flow_lang, MSGS["trending_country_retry"]))
        return _show_trending_for_country(cc, flow, text, mode=_trending_mode(flow))

    if step == "trending_showing_products":
        order_escape = _maybe_escape_trending_for_order_intent(text)
        if order_escape is not None:
            return order_escape
        llm_res = await _try_trending_llm()
        if llm_res is not None:
            return llm_res
        cache_raw = flow.get("trending_products_cache")
        cache: List[Dict[str, Any]] = cache_raw if isinstance(cache_raw, list) else []
        all_raw = flow.get("trending_products_all")
        all_items: List[Dict[str, Any]] = all_raw if isinstance(all_raw, list) else cache
        cc = str(flow.get("trending_country") or "").strip().upper()
        flow_cat = flow.get("trending_category")
        visible = _trending_visible_list(all_items, flow_cat)
        wanted_category = _parse_trending_category(text)
        mode = _trending_mode(flow)
        if _looks_like_greeting(text):
            nf, greet_reply = _exit_trending_for_greeting(flow, flow_lang)
            return save(nf, greet_reply, skip_api=False)
        if not cache:
            nf = _conversation_bail_from_trending(flow, flow_lang)
            hint = (
                "[Context: Trending product list was not available in session. "
                "Help them choose a country for trending products or answer their message naturally. "
                'Do not end with a website URL, "type support", or any boilerplate sign-off.]\n'
            )
            return ai_forward(
                hint + text,
                nf,
                skip_api=_default_skip_store_api(nf),
                suppress_kb_wrap=True,
            )

        if _wants_trending_more(text):
            off_raw = flow.get("trending_offset")
            try:
                offset = int(off_raw) if off_raw is not None else 0
            except (TypeError, ValueError):
                offset = 0
            new_offset = offset + TRENDING_PAGE_SIZE
            if new_offset >= len(visible):
                no_more_key = _trending_tpl(mode, "trending_no_more_pages")
                return save(
                    flow,
                    _t(flow_lang, MSGS[no_more_key]).format(
                        country=_trending_footer_country_label(cc)
                    ),
                )
            page = visible[new_offset : new_offset + TRENDING_PAGE_SIZE]
            has_more = new_offset + len(page) < len(visible)
            fk, needs_c = _trending_footer_template_key(
                first_batch=False, has_more=has_more, mode=mode,
            )
            footer = (
                _t(flow_lang, MSGS[fk]).format(country=_trending_footer_country_label(cc))
                if needs_c
                else _t(flow_lang, MSGS[fk])
            )
            nf = {
                **flow,
                "step": "trending_showing_products",
                "lang": flow_lang,
                "trending_products_cache": page,
                "trending_offset": new_offset,
                "trending_mode": mode,
            }
            body = _trending_inbox_and_web_body(
                flow_lang,
                cc,
                page,
                category=flow_cat if isinstance(flow_cat, str) and flow_cat.strip() else None,
                start_rank=new_offset + 1,
                is_more_batch=True,
                mode=mode,
            )
            base_reply2 = f"{body}\n\n{footer}".strip()
            followup2 = _trending_followup_block(flow_lang, cc, mode=mode).lstrip()
            full_reply = f"{base_reply2}\n\n{followup2}".strip() if followup2 else base_reply2
            if ch == "whatsapp":
                wa_list2: List[Dict[str, str]] = []
                no_url2: List[str] = []
                for i, it in enumerate(page):
                    row_imgs = _wa_images_for_trending_row(it, rank=new_offset + i + 1)
                    logger.info(
                        "trending WA images (more): country=%s product=%s images=%d",
                        cc,
                        (it.get("product_name") or "")[:40],
                        len(row_imgs),
                    )
                    if row_imgs:
                        wa_list2.extend(row_imgs)
                    else:
                        cap = _wa_caption_for_trending_row(it, rank=new_offset + i + 1)
                        no_url2.append(f"{cap}\n(no image URL — open chat on web for full list)")
                if wa_list2:
                    first_bubble2 = (
                        "\n\n".join([*no_url2, base_reply2]).strip() if no_url2 else base_reply2
                    )
                    wa_after2: Union[str, List[str]] = (
                        [first_bubble2, followup2] if followup2 else [first_bubble2]
                    )
                    return save(nf, full_reply, wa_images=wa_list2, wa_text_after=wa_after2)
            return save(nf, full_reply)

        if _wants_non_trending_products(text):
            inline_cc = _parse_trending_country_reply(text)
            base = {**flow, "lang": flow_lang}
            for k in TRENDING_STATE_KEYS:
                base.pop(k, None)
            base["trending_mode"] = "non_trending"
            if inline_cc:
                return _show_trending_for_country(inline_cc, base, text, mode="non_trending")
            base["step"] = "trending_awaiting_country"
            return save(base, _t(flow_lang, MSGS["trending_ask_country"]))
        if _wants_trending_products(text):
            inline_cc = _parse_trending_country_reply(text)
            base = {**flow, "lang": flow_lang}
            for k in TRENDING_STATE_KEYS:
                base.pop(k, None)
            base["trending_mode"] = "trending"
            if inline_cc:
                return _show_trending_for_country(inline_cc, base, text, mode="trending")
            base["step"] = "trending_awaiting_country"
            return save(base, _t(flow_lang, MSGS["trending_ask_country"]))

        if wanted_category:
            next_visible = _filter_trending_items_by_category(all_items, wanted_category)
            if not next_visible:
                no_cat_key = _trending_tpl(mode, "trending_no_products_category")
                return save(
                    flow,
                    _t(flow_lang, MSGS[no_cat_key]).format(
                        country=_trending_footer_country_label(cc),
                        category=wanted_category,
                    ),
                )
            offset = 0
            page = next_visible[offset : offset + TRENDING_PAGE_SIZE]
            has_more = offset + len(page) < len(next_visible)
            fk, needs_c = _trending_footer_template_key(
                first_batch=True, has_more=has_more, mode=mode,
            )
            footer = (
                _t(flow_lang, MSGS[fk]).format(country=_trending_footer_country_label(cc))
                if needs_c
                else _t(flow_lang, MSGS[fk])
            )
            nf = {
                **flow,
                "step": "trending_showing_products",
                "lang": flow_lang,
                "trending_category": wanted_category,
                "trending_products_cache": page,
                "trending_products_all": all_items,
                "trending_offset": offset,
                "trending_mode": mode,
            }
            body = _trending_inbox_and_web_body(
                flow_lang,
                cc,
                page,
                category=wanted_category,
                start_rank=1,
                is_more_batch=False,
                mode=mode,
            )
            base_reply_c = f"{body}\n\n{footer}".strip()
            followup_c = _trending_followup_block(flow_lang, cc, mode=mode).lstrip()
            full_reply = f"{base_reply_c}\n\n{followup_c}".strip() if followup_c else base_reply_c
            if ch == "whatsapp":
                wa_list: List[Dict[str, str]] = []
                no_url_lines: List[str] = []
                for i, it in enumerate(page):
                    row_imgs = _wa_images_for_trending_row(it, rank=offset + i + 1)
                    logger.info(
                        "trending WA images (category=%s): country=%s product=%s images=%d",
                        wanted_category,
                        cc,
                        (it.get("product_name") or "")[:40],
                        len(row_imgs),
                    )
                    if row_imgs:
                        wa_list.extend(row_imgs)
                    else:
                        cap = _wa_caption_for_trending_row(it, rank=offset + i + 1)
                        no_url_lines.append(f"{cap}\n(no image URL — open chat on web for full list)")
                if wa_list:
                    first_bubble_c = (
                        "\n\n".join([*no_url_lines, base_reply_c]).strip()
                        if no_url_lines else base_reply_c
                    )
                    wa_after: Union[str, List[str]] = (
                        [first_bubble_c, followup_c] if followup_c else [first_bubble_c]
                    )
                    return save(nf, full_reply, wa_images=wa_list, wa_text_after=wa_after)
            return save(nf, full_reply)

        picked = _select_trending_product_from_list(visible, text)
        if picked:
            fresh: Optional[Dict[str, Any]] = None
            pid = picked.get("id")
            if pid is not None:
                try:
                    fresh = get_trending_product_by_id(db, tenant_id, int(pid))
                except (TypeError, ValueError):
                    fresh = None
            p = fresh or picked
            nm = str(p.get("product_name") or "").strip() or "this product"
            desc = str(p.get("description") or "").strip()
            price_line = _trending_price_bit(p) or ""
            nf = {
                **flow,
                "step": "trending_showing_products",
                "lang": flow_lang,
                "trending_mode": mode,
            }
            if desc:
                detail_msg = _t(flow_lang, MSGS["trending_product_detail_ok"]).format(
                    name=nm,
                    price_line=price_line or "—",
                    description=desc,
                )
            else:
                detail_msg = _t(flow_lang, MSGS["trending_product_detail_missing"]).format(name=nm)
            detail_msg = _append_trending_followup_suggestions(flow_lang, cc, detail_msg, mode=mode)
            # Product-detail replies are text-only. Images were already sent
            # with the trending list, so re-sending them when the user asks
            # "tell me more about this" would be noisy/redundant.
            return save(nf, detail_msg)

        # Anything else (thanks, acknowledgments in any language, questions, noise):
        # leave trending and let the LLM interpret — no hardcoded phrase lists.
        logger.info("trending_showing_products: bail to LLM (non-pagination, non-pick): %r", (text or "")[:80])
        off_hint = flow.get("trending_offset")
        try:
            off_i = int(off_hint) if off_hint is not None else 0
        except (TypeError, ValueError):
            off_i = 0
        names = ", ".join(
            f"{off_i + i + 1}: {str(x.get('product_name') or '').strip()}"
            for i, x in enumerate(cache[:TRENDING_PAGE_SIZE])
            if (x.get("product_name") or "").strip()
        )
        region = _trending_footer_country_label(cc) if cc else "their region"
        nf = _conversation_bail_from_trending(flow, flow_lang)
        hint_parts = [
            f"[User was viewing trending products for {region}.",
            f'They wrote: "{text}".',
            "Respond naturally in the chat language (thanks, short replies, Arabic/Urdu/Roman Urdu, or new questions are all fine).",
            'Do not say their message failed to match a trending product or ask them to pick only from the list unless they clearly need that.',
        ]
        if names:
            hint_parts.append(f"Last page shown (list numbers for reference): {names}.")
        hint_parts.append('They can ask by number, general questions about Arabia Dropshipping, or acknowledgments.]')
        hint_parts.append('Do not end with a website URL, "type support", or any boilerplate sign-off.')
        hint = " ".join(hint_parts) + "\n"
        # suppress_kb_wrap: the LLM runner already had a turn and declined.
        # We still let LangChain craft a natural reply, but we must not tack
        # on the kb_wrap website / support footer inside the trending flow.
        return ai_forward(
            hint + text,
            nf,
            skip_api=_default_skip_store_api(nf),
            suppress_kb_wrap=True,
        )

    if step == "sourcing_collecting_details":
        # Customer is providing product details for sourcing — collect and hand off
        # Any message here is treated as additional details; hand off to agent
        sourcing_info = flow.get("sourcing_product_name") or ""
        team = TEAM_NEW_CUSTOMER
        if flow.get("verified"):
            team = flow.get("experience_team") or TEAM_BEGINNER

        # Check if this is a bulk quantity message
        has_bulk = bool(re.search(r"\b\d{2,}\s*(?:piece|pieces|pcs|unit|units|qty)\b", text.lower()))
        if has_bulk:
            template_key = "sourcing_bulk_handoff"
        else:
            template_key = "sourcing_handoff"

        nf = {
            **flow,
            "step": "awaiting_agent",
            "intro_shown": True,
            "pending_handoff_team": team,
            "lang": flow_lang,
        }
        return save(
            nf,
            _t(flow_lang, MSGS[template_key]),
            team=team,
            esc=True,
        )

    if step == "existing_awaiting_email":
        if _wants_new_customer_path(text):
            nf = {**_bail_to_conversational(flow, flow_lang), "customer_kind": "new"}
            return save(nf, _t(flow_lang, MSGS["new_customer_welcome"]))

        if _script_verification_bypassed():
            f_b, msg_b = _existing_identity_entry(
                flow,
                flow_lang,
                verify_reason=flow.get("verify_reason"),
                pending_order_ref=flow.get("pending_order_ref"),
                intro_key="ask_email",
            )
            return save(f_b, msg_b)

        # 1) Short-circuit: if the user just shares an order id, look it up
        #    without requiring email verification. Possession of the order id
        #    is itself proof enough for a single-order lookup.
        maybe_ref = ""
        if _is_likely_order_id_only(text):
            maybe_ref = re.sub(r"[^\d\-#]", "", (text or "").strip()) or (text or "").strip()
        else:
            maybe_ref = (_extract_order_id_from_message(text, phone) or "").strip()
        if maybe_ref:
            order, src = await _lookup_order(
                db, tenant_id, maybe_ref, store_client,
                seller_id=_flow_merchant_seller_id(flow),
            )
            if order:
                f = {**flow, "step": "conversational", "lang": flow_lang, "pending_order_ref": None}
                return save(f, _format_order_sentence(flow_lang, order))
            if src == "api_error":
                return save(flow, _t(flow_lang, MSGS["order_lookup_error"]))
            # Not found → keep them in the email step; show not-found and
            # re-prompt with a one-liner so the convo stays on rails.
            not_found = _t(flow_lang, MSGS["order_not_found"])
            ask_email = _t(flow_lang, MSGS["ask_email"])
            return save(flow, f"{not_found}\n\n{ask_email}")

        # 2) "I don't have either / can't find" → gentle help message.
        if _wants_cannot_find_order_help(text):
            return save(flow, _t(flow_lang, MSGS["cannot_find_order_help"]))

        if _is_natural_language(text) and not _is_likely_email(text):
            nf = _bail_to_conversational(flow, flow_lang)
            return ai_forward(text, nf, skip_api=True)
        email = (text or "").strip().lower()
        if not _is_likely_email(email):
            return save(flow, _t(flow_lang, MSGS["email_invalid"]))
        return await submit_existing_email(flow, email)

    if step == "existing_awaiting_verification_code":
        if _script_verification_bypassed():
            f_b, msg_b = _existing_identity_entry(
                flow,
                flow_lang,
                verify_reason=flow.get("verify_reason"),
                pending_order_ref=flow.get("pending_order_ref"),
                intro_key="ask_email",
            )
            return save(f_b, msg_b)
        if _wants_new_customer_path(text):
            nf = {**_bail_to_conversational(flow, flow_lang), "customer_kind": "new"}
            return save(nf, _t(flow_lang, MSGS["new_customer_welcome"]))
        if _is_natural_language(text):
            nf = _bail_to_conversational(flow, flow_lang)
            return ai_forward(text, nf, skip_api=True)
        code = (text or "").strip()
        pending_email = (flow.get("pending_email") or "").strip().lower()
        if not pending_email:
            f = {
                **flow,
                "step": "existing_awaiting_email",
                "lang": flow_lang,
            }
            return save(f, _t(flow_lang, MSGS["ask_email"]))
        low = code.lower()
        if low in ("resend", "resend code", "code resend"):
            logger.info("Verification flow: resending code to %s", pending_email)
            sent = await store_client.send_verification_code(pending_email)
            logger.info(
                "Verification flow: resend send_verification_code result for %s = %s",
                pending_email,
                sent,
            )
            if not sent:
                return save(flow, _t(flow_lang, MSGS["verify_send_error"]))
            return save(flow, _t(flow_lang, MSGS["code_sent"]).format(email=pending_email))
        if len(code) < 4:
            return save(flow, _t(flow_lang, MSGS["verify"]).format(email=pending_email))
        logger.info("Verification flow: verifying code for %s", pending_email)
        verified = await store_client.verify_code(pending_email, code)
        logger.info("Verification flow: verify_code result for %s = %s", pending_email, verified)
        if not verified:
            return save(flow, _t(flow_lang, MSGS["verify_invalid_code"]))
        f = {
            **flow,
            "verified": False,
            "step": "existing_awaiting_mobile",
            "lang": flow_lang,
        }
        return save(f, _t(flow_lang, MSGS["email_verified_success"]))

    if step == "existing_awaiting_mobile":
        if _script_verification_bypassed():
            f_b, msg_b = _existing_identity_entry(
                flow,
                flow_lang,
                verify_reason=flow.get("verify_reason"),
                pending_order_ref=flow.get("pending_order_ref"),
                intro_key="ask_email",
            )
            return save(f_b, msg_b)
        if _wants_new_customer_path(text):
            nf = {**_bail_to_conversational(flow, flow_lang), "customer_kind": "new"}
            return save(nf, _t(flow_lang, MSGS["new_customer_welcome"]))
        if _is_natural_language(text):
            nf = _bail_to_conversational(flow, flow_lang)
            return ai_forward(text, nf, skip_api=True)
        pending_email = (flow.get("pending_email") or "").strip().lower()
        mobile_raw = (text or "").strip()
        if not pending_email:
            f = {
                **flow,
                "step": "existing_awaiting_email",
                "lang": flow_lang,
            }
            return save(f, _t(flow_lang, MSGS["ask_email"]))
        if len(mobile_raw) < 7:
            return save(flow, _t(flow_lang, MSGS["ask_mobile"]))
        mobile = _normalize_phone(mobile_raw)
        if mobile is None:
            return save(flow, _t(flow_lang, MSGS["mobile_unsupported_country"]))
        customer = await store_client.get_customer_by_email_mobile_first_hit(
            pending_email, mobile_raw
        )
        if not customer:
            return save(flow, _t(flow_lang, MSGS["customer_not_found_after_verify"]))
        verified_at = _verified_at_iso()
        reason = flow.get("verify_reason")
        oref_raw = flow.get("pending_order_ref")
        oref = (str(oref_raw).strip() if oref_raw else "") or ""

        merchant_sid = merchant_seller_scope_from_row(customer)
        base_f: Dict[str, Any] = {
            **flow,
            "verified": True,
            "step": "conversational",
            "customer_kind": "existing",
            "verified_customer": customer,
            "seller_id": merchant_sid,
            "customer_email": pending_email,
            "verified_at": verified_at,
            "pending_mobile": mobile,
            "pending_email": None,
            "verify_reason": None,
            "pending_order_ref": None,
            "lang": flow_lang,
        }
        if mem_id and merchant_sid:
            ConversationMemory.store_verification(mem_id, merchant_sid)

        resume_q = ""
        if mem_id:
            _pinfo = ConversationMemory.get_pending_intent(mem_id)
            if _pinfo:
                resume_q = (str(_pinfo.get("original_question") or "")).strip()

        if not oref and resume_q:
            if mem_id:
                ConversationMemory.clear_pending_intent(mem_id, promote_from_queue=False)
            return ai_forward("[Customer question] " + resume_q, base_f, skip_api=False)

        # Build a personalised success line that includes the store/customer name.
        cust_name = (
            (customer or {}).get("name")
            or (customer or {}).get("store_name")
            or (customer or {}).get("full_name")
            or (customer or {}).get("first_name")
        )
        if cust_name and str(cust_name).strip():
            cust_name = str(cust_name).strip()
            if flow_lang == "arabic":
                intro_line = f"✅ تم التحقق! أهلاً بعودتك {cust_name}."
            elif flow_lang == "roman_urdu":
                intro_line = f"✅ Verified! Khush Amdeed {cust_name}."
            else:
                intro_line = f"✅ Verified! Welcome back {cust_name}."
        else:
            intro_line = _t(flow_lang, MSGS["verification_success"])

        if flow_lang == "arabic":
            welcome_line = "كيف يمكنني مساعدتك اليوم؟ يمكنك السؤال عن طلباتك أو فواتيرك أو تتبع الشحنة."
        elif flow_lang == "roman_urdu":
            welcome_line = "Aaj kaise madad karoon? Aap apne orders, invoices, ya tracking ke baare mein pooch sakte hain."
        else:
            welcome_line = "How can I help you today? You can ask about your orders, invoices, or tracking."

        parts: list[str] = [intro_line, welcome_line]

        if oref:
            if mem_id:
                ConversationMemory.clear_pending_intent(mem_id, promote_from_queue=False)
            order, src = await _lookup_order(
                db, tenant_id, oref, store_client,
                seller_id=base_f.get("seller_id"),
            )
            if order:
                parts = [intro_line, _format_order_sentence(flow_lang, order), _t(flow_lang, MSGS["verified_followup"])]
                return save(base_f, "\n\n".join(parts))
            if src == "api_error":
                parts = [intro_line, _t(flow_lang, MSGS["order_lookup_error"]), _t(flow_lang, MSGS["verified_followup"])]
                return save(base_f, "\n\n".join(parts))
            parts = [intro_line, _t(flow_lang, MSGS["order_not_found"]), _t(flow_lang, MSGS["ask_order"])]
            oid_flow = {**base_f, "step": "existing_awaiting_order_id"}
            return save(oid_flow, "\n\n".join(parts))

        if reason == "order":
            parts = [intro_line, _t(flow_lang, MSGS["ask_order"])]
            oid_flow = {**base_f, "step": "existing_awaiting_order_id"}
            return save(oid_flow, "\n\n".join(parts))

        return save(base_f, "\n\n".join(parts))

    if step == "existing_awaiting_order_id":
        raw = (text or "").strip()
        ref = raw if _is_likely_order_id_only(raw) else (_extract_order_id_from_message(raw, phone) or raw)
        order, src = await _lookup_order(
            db, tenant_id, ref, store_client,
            seller_id=_flow_merchant_seller_id(flow),
        )
        if order:
            f = {**flow, "step": "conversational", "lang": flow_lang}
            return save(f, _format_order_sentence(flow_lang, order))
        f = {**flow, "step": "existing_awaiting_order_id", "lang": flow_lang}
        if src == "api_error":
            return save(f, _t(flow_lang, MSGS["order_lookup_error"]))
        return save(f, _t(flow_lang, MSGS["order_not_found"]))

    if step == "existing_awaiting_experience":
        routed = TEAM_BEGINNER
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

    if step == "conversational":
        kind = flow.get("customer_kind")
        if kind == "new" and _wants_existing_customer_path(text):
            flow = {**flow, "customer_kind": "existing"}
            kind = "existing"
            if mem_id:
                ConversationMemory.store_bot_customer_kind(mem_id, "existing")

        if not flow.get("verified"):
            if _script_verification_bypassed() and _extract_standalone_email(text):
                flow = {**flow, "customer_kind": "existing"}
                kind = "existing"
                if mem_id:
                    ConversationMemory.store_bot_customer_kind(mem_id, "existing")
                f_em_b, msg_em_b = _existing_identity_entry(
                    flow,
                    flow_lang,
                    verify_reason=None,
                    pending_order_ref=None,
                    intro_key="ask_email",
                )
                return save(f_em_b, msg_em_b)
            em_only = _extract_standalone_email(text)
            if em_only and not _script_verification_bypassed():
                flow = {**flow, "customer_kind": "existing"}
                kind = "existing"
                if mem_id:
                    ConversationMemory.store_bot_customer_kind(mem_id, "existing")
                return await submit_existing_email(flow, em_only)

            if _script_verification_bypassed() and (
                _looks_like_order_status_question(text)
                or _looks_like_account_question(text)
                or _is_likely_order_id_only(text)
            ):
                pre_ref = ""
                if _is_likely_order_id_only(text):
                    pre_ref = re.sub(r"[^\d\-#]", "", (text or "").strip()) or (text or "").strip()
                else:
                    pre_ref = (_extract_order_id_from_message(text, phone) or "").strip()
                if pre_ref:
                    order, src = await _lookup_order(
                        db, tenant_id, pre_ref, store_client,
                        seller_id=_flow_merchant_seller_id(flow),
                    )
                    if order:
                        f_ok = {
                            **flow,
                            "customer_kind": "existing",
                            "step": "conversational",
                            "lang": flow_lang,
                        }
                        return save(f_ok, _format_order_sentence(flow_lang, order))
                    if src == "api_error":
                        return save(
                            {**flow, "customer_kind": "existing"},
                            _t(flow_lang, MSGS["order_lookup_error"]),
                        )
                    retry_msg = (
                        _t(flow_lang, MSGS["order_not_found"])
                        + "\n\n"
                        + _t(flow_lang, MSGS["order_verify_bypass_intro"])
                    )
                    return save(
                        {
                            **flow,
                            "customer_kind": "existing",
                            "step": "existing_awaiting_order_id",
                            "intro_shown": True,
                        },
                        retry_msg,
                    )
                f_ob, msg_ob = _existing_identity_entry(
                    {**flow, "customer_kind": "existing"},
                    flow_lang,
                    verify_reason="order",
                    pending_order_ref=None,
                    intro_key="order_verify_intro",
                )
                return save(f_ob, msg_ob)

        # Verified customers: route order/tracking/invoice queries through the
        # LLM with full store-API context instead of deterministic handlers.
        # The ai_forward(skip_api=False) path triggers fetch_customer_context()
        # which fetches orders, tracking, invoices, and FAQs — the LLM then
        # formulates a natural-language answer.
        if flow.get("verified") and (
            _looks_like_order_status_question(text)
            or _is_likely_order_id_only(text)
            or _looks_like_tracking_by_id(text)
            or _looks_like_invoice_by_id(text)
            or _looks_like_invoice_for_order(text)
            or _looks_like_invoices_in_period(text)
            or _looks_like_latest_invoice(text)
            or _looks_like_all_invoices(text)
            or _looks_like_orders_in_period(text)
        ):
            return ai_forward(
                "[Customer question] " + text,
                {**flow, "step": "conversational"},
                skip_api=False,
            )

        if _wants_non_trending_products(text):
            llm_res = await _try_trending_llm(entry_intent="non_trending")
            if llm_res is not None:
                return llm_res
            inline_cc = _parse_trending_country_reply(text)
            base = {
                **flow,
                "intro_shown": bool(flow.get("intro_shown")),
                "lang": flow_lang,
            }
            for k in TRENDING_STATE_KEYS:
                base.pop(k, None)
            base["trending_mode"] = "non_trending"
            if inline_cc:
                return _show_trending_for_country(inline_cc, base, text, mode="non_trending")
            base["step"] = "trending_awaiting_country"
            return save(base, _t(flow_lang, MSGS["trending_ask_country"]))
        if _wants_trending_products(text):
            llm_res = await _try_trending_llm(entry_intent="trending")
            if llm_res is not None:
                return llm_res
            inline_cc = _parse_trending_country_reply(text)
            base = {
                **flow,
                "intro_shown": bool(flow.get("intro_shown")),
                "lang": flow_lang,
            }
            for k in TRENDING_STATE_KEYS:
                base.pop(k, None)
            base["trending_mode"] = "trending"
            if inline_cc:
                return _show_trending_for_country(inline_cc, base, text)
            base["step"] = "trending_awaiting_country"
            return save(base, _t(flow_lang, MSGS["trending_ask_country"]))

        # Product sourcing / bulk order detection → collect details then hand off
        if _wants_product_sourcing(text):
            # Try to extract a product name from the message
            product_hint = _extract_sourcing_product_name(text)
            # If message already has quantity (bulk), skip collection → hand off directly
            has_bulk = bool(re.search(
                r"\b\d{2,}\s*(?:piece|pieces|pcs|unit|units|qty)\b",
                text.lower(),
            ))
            if has_bulk:
                team = TEAM_NEW_CUSTOMER
                if flow.get("verified"):
                    team = flow.get("experience_team") or TEAM_BEGINNER
                nf = {
                    **flow,
                    "step": "awaiting_agent",
                    "intro_shown": True,
                    "pending_handoff_team": team,
                    "sourcing_product_name": product_hint,
                    "lang": flow_lang,
                }
                return save(
                    nf,
                    _t(flow_lang, MSGS["sourcing_bulk_handoff"]),
                    team=team,
                    esc=True,
                )
            # Otherwise ask for details before handoff
            nf = {
                **flow,
                "step": "sourcing_collecting_details",
                "intro_shown": True,
                "sourcing_product_name": product_hint,
                "lang": flow_lang,
            }
            if product_hint:
                return save(
                    nf,
                    _t(flow_lang, MSGS["sourcing_with_product"]).format(product=product_hint),
                )
            return save(nf, _t(flow_lang, MSGS["sourcing_collect_details"]))

        # Let customer switch to "new" path at any time
        if kind == "existing" and not flow.get("verified") and _wants_new_customer_path(text):
            nf = {**flow, "step": "conversational", "customer_kind": "new", "lang": flow_lang}
            return save(nf, _t(flow_lang, MSGS["new_customer_welcome"]))

        # Greeting: just acknowledge — do NOT re-show the new/existing menu here.
        # The welcome menu is only shown on fresh entry or /reset; mid-conversation
        # greetings get a simple acknowledgment so the customer can continue naturally.
        if _looks_like_greeting(text):
            return save(
                {**flow, "step": "conversational"},
                _t(flow_lang, MSGS["hello_ack"]),
            )

        # Simple acknowledgments (okay, good, fine, hmm, etc.) — reply naturally
        _lowered_text = text.strip().lower()
        _thank_words = {
            "thanks", "thank you", "shukriya", "shukria", "jazakallah",
            "thank u", "thankyou", "thnx", "thnks",
        }
        _ack_words_conv = {
            "ok", "okay", "okey", "oki", "k",
            "good", "fine", "nice", "great", "cool", "alright", "right",
            "yes", "yeah", "yep", "yea", "yah", "haan", "han", "ji",
            "hmm", "hm", "hmmmm", "achha", "acha", "accha", "theek",
            "theek hai", "thik", "thik hai", "sahi", "sahi hai",
            "no", "nahi", "nhi", "na",
        }
        if _lowered_text in _thank_words:
            return save(
                {**flow, "step": "conversational"},
                _t(flow_lang, MSGS["thanks_ack"]),
            )
        if _lowered_text in _ack_words_conv:
            return save(
                {**flow, "step": "conversational"},
                _t(flow_lang, MSGS["hello_ack"]),
            )

        # customer_kind not set yet — first real message without a greeting
        # Treat as implicit new customer and answer directly
        if not kind:
            nf = {
                **flow,
                "step": "conversational",
                "customer_kind": "new",
                "intro_shown": True,
                "lang": flow_lang,
            }
            return ai_forward(text, nf, skip_api=True)

        # --- Existing customer (verified) path ---
        # Route ALL verified-customer queries through the LLM with full
        # store-API context.  fetch_customer_context() in the orchestrator
        # already fetches orders, tracking, invoices, and FAQs using the
        # seller_id — the LLM formulates a natural-language answer.
        if flow.get("verified"):
            return ai_forward(
                "[Customer question] " + text,
                {**flow, "step": "conversational"},
                skip_api=False,
            )

        # --- Unverified: order/account questions start existing-customer identity (or bypass order-id path) ---
        if _needs_account_verification(flow) and (
            _looks_like_order_status_question(text)
            or _looks_like_account_question(text)
            or _looks_like_invoice_for_order(text)
        ):
            flow = {**flow, "customer_kind": "existing"}
            if mem_id:
                ConversationMemory.store_bot_customer_kind(mem_id, "existing")
            pre_ref = ""
            if _is_likely_order_id_only(text):
                pre_ref = re.sub(r"[^\d\-#]", "", (text or "").strip()) or (text or "").strip()
            else:
                pre_ref = (_extract_order_id_from_message(text, phone) or "").strip()
            if (
                _looks_like_order_status_question(text)
                or _is_likely_order_id_only(text)
                or _looks_like_invoice_for_order(text)
            ):
                reason = "order"
            else:
                reason = "account"
            if verification_expired_this_turn:
                intro_key = "verification_expired_reverify"
            else:
                intro_key = "order_verify_intro" if reason == "order" else "account_verify_intro"
            f_iv, msg_iv = _existing_identity_entry(
                flow,
                flow_lang,
                verify_reason=reason,
                pending_order_ref=pre_ref or None,
                intro_key=intro_key,
            )
            if mem_id and (text or "").strip():
                ConversationMemory.store_pending_intent(
                    mem_id,
                    "resume_after_verify",
                    reason,
                    (text or "").strip(),
                    queue_previous=False,
                )
            return save(f_iv, msg_iv)

        # --- New customer or existing with general questions: answer from KB directly ---
        skip = not flow.get("verified")
        return ai_forward(
            "[Customer question] " + text if kind else text,
            {**flow, "step": "conversational", "intro_shown": True},
            skip_api=skip,
        )

    if step == "awaiting_agent":
        # Re-check agent availability on every message so we stop looping if no one comes online.
        _agt_team = (
            flow.get("pending_handoff_team")
            or (
                (flow.get("experience_team") or TEAM_BEGINNER)
                if flow.get("verified")
                else TEAM_NEW_CUSTOMER
            )
        )
        if not _any_agent_available(db, tenant_id, team=_agt_team):
            nf = {**flow, "step": "conversational", "intro_shown": True, "lang": flow_lang}
            nf.pop("pending_handoff_team", None)
            return save(nf, _build_handoff_unavailable_reply(db, tenant_id, flow_lang), skip_api=True)

        if not wants_human_agent(text) and is_conversational_acknowledgment(text):
            skip = not flow.get("verified")
            return ai_forward(
                text,
                {**flow, "step": "conversational", "intro_shown": True},
                skip_api=skip,
            )
        if flow.get("verified"):
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
        team = flow.get("pending_handoff_team") or TEAM_NEW_CUSTOMER
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
            skip_api=True,
        )

    # Unknown / legacy step — migrate to conversational greeting
    nf = _reset_bot_flow(flow_lang)
    return save(nf, _t(flow_lang, MSGS["greeting"]), skip_api=False)
