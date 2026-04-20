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
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import get_openai_api_key, settings
from langchain_bot.prompts import strip_followup_block_when_disabled
from models import Conversation, Message, Order, TenantSchedule
from services.ai_orchestrator_service.services import (
    AIOrchestrator,
    _extract_order_id_from_message,
)
from services.phone_lookup_variants import normalize_mobile_for_flow
from services.store_integration_service.client import StoreIntegrationClient
from services.trending_products_service.bot_query import (
    get_trending_product_by_id,
    list_active_trending_for_country,
)
from services.human_handoff_intent import (
    is_slash_reset_command,
    solo_menu_digit,
    wants_bot_flow_reset,
    wants_human_agent,
)
from services.customer_bot_flow.templates import BOT_FLOW_TEMPLATES
from services.tenant_schedule_text import format_tenant_schedule_for_customer
try:
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:  # pragma: no cover — older langchain pin
    from langchain.schema import HumanMessage, SystemMessage

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

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
)
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


def _append_trending_followup_suggestions(lang: str, country_code: str, text: str) -> str:
    """Append deterministic follow-ups when LLM_FOLLOWUP_SUGGESTIONS is enabled (trending is non-LLM)."""
    if not bool(getattr(settings, "llm_followup_suggestions", True)):
        return (text or "").strip()
    base = (text or "").strip()
    if not base:
        return base
    oa, ob = _trending_followup_other_markets(country_code)
    block = _t(lang, MSGS["trending_followup_suggestions"]).format(other_a=oa, other_b=ob)
    return f"{base}{block}".strip()


def _exit_trending_for_greeting(flow: Dict[str, Any], flow_lang: str) -> Tuple[Dict[str, Any], str]:
    """Leave trending steps on hi/hello; keep customer_kind when set, else show new/existing greeting."""
    nf = {**flow, "lang": flow_lang}
    for k in TRENDING_STATE_KEYS:
        nf.pop(k, None)
    nf["step"] = "conversational"
    if flow.get("customer_kind"):
        return nf, _t(flow_lang, MSGS["hello_ack"])
    nf["step"] = "awaiting_customer_type"
    nf["intro_shown"] = True
    nf["customer_kind"] = None
    return nf, _t(flow_lang, MSGS["greeting"])


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


def _wants_trending_more(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    flat = unicodedata.normalize("NFKC", t).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    tokens = [x for x in re.split(r"\s+", flat) if x]
    if len(tokens) <= 2 and tokens in (
        ["more"],
        ["m"],
        ["next"],
        ["مزيد"],
        ["التالي"],
        ["mazeed"],
    ):
        return True
    phrases = (
        "show me more",
        "show more",
        "more products",
        "more trending",
        "load more",
        "next page",
        "aur dikhao",
        "aur dikha",
        "mazeed",
        "مزيد",
        "mazeed dikhao",
        "aur dikha do",
    )
    return any(p in flat for p in phrases)


def _trending_footer_template_key(*, first_batch: bool, has_more: bool) -> tuple[str, bool]:
    """Return (MSGS key, whether template expects {country})."""
    if first_batch and has_more:
        return ("trending_footer_first_has_more", False)
    if first_batch and not has_more:
        return ("trending_footer_first_only", True)
    if not first_batch and has_more:
        return ("trending_footer_more_has_more", False)
    return ("trending_footer_more_end", True)


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
) -> str:
    if not items:
        return _t(lang, MSGS["trending_no_products"]).format(
            country=_trending_footer_country_label(country)
        )
    if category:
        intro_key = "trending_intro_more_category" if is_more_batch else "trending_intro_first_category"
        intro = _t(lang, MSGS[intro_key]).format(country=country, category=category)
    else:
        intro_key = "trending_intro_more" if is_more_batch else "trending_intro_first"
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
    if query in (
        "more",
        "m",
        "next",
        "next page",
        "show more",
        "show me more",
        "مزيد",
        "التالي",
        "mazeed",
        "aur",
        "aur dikhao",
    ):
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


def _wants_trending_products(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t or len(t) > 220:
        return False
    flat = t.replace("\n", " ")
    # Negation — user explicitly does NOT want trending products
    if re.search(r"\bnot\s+trending\b|\bnon[\s-]?trending\b|\bwithout\s+trending\b", flat):
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
    return not bool(flow.get("verified"))


def _reset_bot_flow(lang_code: str) -> Dict[str, Any]:
    return {
        "step": "awaiting_customer_type",
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
        "(the bot just asked: new customer or existing customer?).\n"
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
        ),
        "status": _pick(raw, "status"),
        "delivery_status": _pick(raw, "delivery_status", "fulfillment_status", "shipping_status"),
        "expected_delivery": _pick(raw, "expected_delivery", "estimated_delivery", "delivery_date", "expected_delivery_date"),
        "tracking_id": _pick(raw, "tracking_id", "tracking_number", "awb_number", "awb"),
        "payment_status": _pick(raw, "payment_status"),
        "invoice_id": _pick(raw, "invoice_id", "invoice_number", "invoice_ref"),
        "invoice_amount": _pick(raw, "invoice_amount"),
        "return_status": _pick(raw, "return_status"),
        "return_date": _pick(raw, "return_date"),
        "return_charges": _pick(raw, "return_charges"),
        "return_charge_invoice": _pick(raw, "return_charge_invoice"),
        "return_reason": _pick(raw, "return_reason"),
        "cancellation_type": _pick(raw, "cancellation_type"),
        "cancellation_reason": _pick(raw, "cancellation_reason"),
        "total_amount": _pick(raw, "total_amount", "amount"),
        "currency": _pick(raw, "currency"),
    }


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
            detail = await store_client.get_order_by_number(ref)
    except Exception:  # noqa: BLE001
        logger.exception("order lookup: /orders/%s failed", ref)
        return None, "api_error"

    if not detail:
        return None, "not_found"

    try:
        tracking = await store_client.get_order_tracking(ref, seller_id=sid)
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
    whatsapp_text_after_images: Optional[str] = None
    """When set with whatsapp_image_outbound, sent as the text message after images on WhatsApp."""


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
            whatsapp_text_after_images=None,
        )

    meta = _normalize_meta(conversation)
    flow = _get_flow(meta)
    meta, flow = _apply_inactivity_bot_reset(db, conversation, meta, flow)
    flow = _migrate_legacy_bot_flow(flow)
    flow, verification_expired_this_turn = _apply_verification_expiry(flow)

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

    store_client = StoreIntegrationClient()
    escalate_for_ai_turn = await orchestrator.should_escalate(user_message)

    def save(
        f: Dict[str, Any],
        reply: str,
        team: Optional[str] = None,
        esc: bool = False,
        skip_api: Optional[bool] = None,
        wa_images: Optional[List[Dict[str, str]]] = None,
        wa_text_after: Optional[str] = None,
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
            whatsapp_text_after_images=wa_text_after,
        )

    def ai_forward(msg: str, f: Dict[str, Any], skip_api: bool):
        deterministic = _deterministic_kb_answer(msg, flow_lang)
        if deterministic:
            return save(
                f,
                format_kb_reply(flow_lang, deterministic),
                skip_api=True,
            )
        logger.debug(
            "customer_bot_flow ai_forward skip_store_api=%s preview=%s",
            skip_api,
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
            whatsapp_text_after_images=None,
        )

    ch = (channel or "web").strip().lower()
    text = (user_message or "").strip()

    if is_slash_reset_command(text):
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
        nf = _reset_bot_flow(flow_lang)
        return save(nf, _t(flow_lang, MSGS["greeting"]), skip_api=False)

    # Global handoff: any step (incl. verification) when user asks for a human agent
    if wants_human_agent(text):
        exp_team = flow.get("experience_team")
        if flow.get("verified"):
            team = exp_team or TEAM_BEGINNER
        else:
            team = TEAM_NEW_CUSTOMER
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
            nf = {
                **flow,
                "step": "conversational",
                "customer_kind": "new",
                "intro_shown": True,
                "lang": flow_lang,
            }
            return save(nf, _t(flow_lang, MSGS["new_customer_welcome"]))
        if choice == "existing":
            nf = {
                **flow,
                "step": "existing_awaiting_email",
                "customer_kind": "existing",
                "intro_shown": True,
                "lang": flow_lang,
            }
            return save(nf, _t(flow_lang, MSGS["ask_email"]))
        # Trending / sourcing before the entry LLM so phrases like "Give me trending products"
        # are never treated as an unclear 1/2 menu reply.
        if _wants_trending_products(text):
            nf = {
                **flow,
                "step": "trending_awaiting_country",
                "customer_kind": flow.get("customer_kind") or "new",
                "intro_shown": True,
                "lang": flow_lang,
            }
            for k in (
                "trending_country",
                "trending_products_cache",
                "trending_products_all",
                "trending_category",
                "trending_offset",
            ):
                nf.pop(k, None)
            return save(nf, _t(flow_lang, MSGS["trending_ask_country"]))
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
            nf = {
                **flow,
                "step": "conversational",
                "customer_kind": "new",
                "intro_shown": True,
                "lang": flow_lang,
            }
            return save(nf, _t(flow_lang, MSGS["new_customer_welcome"]))
        if entry_intent == "existing":
            nf = {
                **flow,
                "step": "existing_awaiting_email",
                "customer_kind": "existing",
                "intro_shown": True,
                "lang": flow_lang,
            }
            return save(nf, _t(flow_lang, MSGS["ask_email"]))
        # Short menu-ish input but classifier could not decide — ask again (avoid empty LLM reply / fallback).
        if entry_intent == "other" and len(text.strip()) <= 48 and not _looks_like_free_text_question(text):
            return save(flow, _t(flow_lang, MSGS["customer_type_unclear"]))

        # Free-text that isn't a choice → treat as new customer and answer directly
        nf = {
            **flow,
            "step": "conversational",
            "customer_kind": "new",
            "intro_shown": True,
            "lang": flow_lang,
        }
        return ai_forward(text, nf, skip_api=True)

    if step == "trending_awaiting_country":
        if _looks_like_greeting(text):
            nf, greet_reply = _exit_trending_for_greeting(flow, flow_lang)
            return save(nf, greet_reply, skip_api=False)
        if _is_natural_language(text) and _parse_trending_country_reply(text) is None:
            nf = _bail_to_conversational(flow, flow_lang)
            return ai_forward(text, nf, skip_api=_default_skip_store_api(nf))
        cc = _parse_trending_country_reply(text)
        if not cc:
            return save(flow, _t(flow_lang, MSGS["trending_country_retry"]))
        wanted_category = _parse_trending_category(text)
        items_all = list_active_trending_for_country(db, tenant_id, cc)
        visible = _trending_visible_list(items_all, wanted_category)
        offset = 0
        page = visible[offset : offset + TRENDING_PAGE_SIZE]
        if not page:
            # Stay in trending_awaiting_country so the user can pick another country
            nf = {**flow, "step": "trending_awaiting_country", "lang": flow_lang}
            for k in TRENDING_STATE_KEYS:
                nf.pop(k, None)
            if wanted_category:
                no_msg = _t(flow_lang, MSGS["trending_no_products_category"]).format(
                    country=_trending_footer_country_label(cc),
                    category=wanted_category,
                )
            else:
                no_msg = _t(flow_lang, MSGS["trending_no_products"]).format(
                    country=_trending_footer_country_label(cc)
                )
            retry = _t(flow_lang, MSGS["trending_country_retry"])
            return save(nf, f"{no_msg}\n\n{retry}")
        has_more = offset + len(page) < len(visible)
        fk, needs_c = _trending_footer_template_key(first_batch=True, has_more=has_more)
        footer = (
            _t(flow_lang, MSGS[fk]).format(country=_trending_footer_country_label(cc))
            if needs_c
            else _t(flow_lang, MSGS[fk])
        )
        nf = {
            **flow,
            "step": "trending_showing_products",
            "lang": flow_lang,
            "trending_country": cc,
            "trending_category": wanted_category,
            "trending_products_all": items_all,
            "trending_products_cache": page,
            "trending_offset": offset,
        }
        body = _trending_inbox_and_web_body(
            flow_lang,
            cc,
            page,
            category=wanted_category,
            start_rank=1,
            is_more_batch=False,
        )
        full_reply = _append_trending_followup_suggestions(
            flow_lang, cc, f"{body}\n\n{footer}".strip()
        )
        wa_images: Optional[List[Dict[str, str]]] = None
        wa_after: Optional[str] = None
        if ch == "whatsapp":
            wa_list: List[Dict[str, str]] = []
            no_url_lines: List[str] = []
            for i, it in enumerate(page):
                url = (it.get("image_url") or "").strip()
                cap = _wa_caption_for_trending_row(it, rank=offset + i + 1)
                if url:
                    wa_list.append({"image_url": url, "caption": cap})
                else:
                    no_url_lines.append(f"{cap}\n(no image URL — open chat on web for full list)")
            if wa_list:
                wa_images = wa_list
                # Send intro + numbered list + footer after images (captions are per-product only).
                wa_after = full_reply.strip()
                if no_url_lines:
                    wa_after = "\n\n".join([*no_url_lines, full_reply]).strip()
        return save(nf, full_reply, wa_images=wa_images, wa_text_after=wa_after)

    if step == "trending_showing_products":
        cache_raw = flow.get("trending_products_cache")
        cache: List[Dict[str, Any]] = cache_raw if isinstance(cache_raw, list) else []
        all_raw = flow.get("trending_products_all")
        all_items: List[Dict[str, Any]] = all_raw if isinstance(all_raw, list) else cache
        cc = str(flow.get("trending_country") or "").strip().upper()
        flow_cat = flow.get("trending_category")
        visible = _trending_visible_list(all_items, flow_cat)
        wanted_category = _parse_trending_category(text)
        if _looks_like_greeting(text):
            nf, greet_reply = _exit_trending_for_greeting(flow, flow_lang)
            return save(nf, greet_reply, skip_api=False)
        if not cache:
            nf = _conversation_bail_from_trending(flow, flow_lang)
            hint = (
                "[Context: Trending product list was not available in session. "
                "Help them choose a country for trending products or answer their message naturally.]\n"
            )
            return ai_forward(hint + text, nf, skip_api=_default_skip_store_api(nf))

        if _wants_trending_more(text):
            off_raw = flow.get("trending_offset")
            try:
                offset = int(off_raw) if off_raw is not None else 0
            except (TypeError, ValueError):
                offset = 0
            new_offset = offset + TRENDING_PAGE_SIZE
            if new_offset >= len(visible):
                return save(
                    flow,
                    _t(flow_lang, MSGS["trending_no_more_pages"]).format(
                        country=_trending_footer_country_label(cc)
                    ),
                )
            page = visible[new_offset : new_offset + TRENDING_PAGE_SIZE]
            has_more = new_offset + len(page) < len(visible)
            fk, needs_c = _trending_footer_template_key(first_batch=False, has_more=has_more)
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
            }
            body = _trending_inbox_and_web_body(
                flow_lang,
                cc,
                page,
                category=flow_cat if isinstance(flow_cat, str) and flow_cat.strip() else None,
                start_rank=new_offset + 1,
                is_more_batch=True,
            )
            full_reply = _append_trending_followup_suggestions(
                flow_lang, cc, f"{body}\n\n{footer}".strip()
            )
            if ch == "whatsapp":
                wa_list2: List[Dict[str, str]] = []
                no_url2: List[str] = []
                for i, it in enumerate(page):
                    url = (it.get("image_url") or "").strip()
                    cap = _wa_caption_for_trending_row(it, rank=new_offset + i + 1)
                    if url:
                        wa_list2.append({"image_url": url, "caption": cap})
                    else:
                        no_url2.append(f"{cap}\n(no image URL — open chat on web for full list)")
                if wa_list2:
                    wa_after2 = full_reply.strip()
                    if no_url2:
                        wa_after2 = "\n\n".join([*no_url2, full_reply]).strip()
                    return save(nf, full_reply, wa_images=wa_list2, wa_text_after=wa_after2)
            return save(nf, full_reply)

        if _wants_trending_products(text):
            nf = {
                **flow,
                "step": "trending_awaiting_country",
                "lang": flow_lang,
            }
            for k in TRENDING_STATE_KEYS:
                nf.pop(k, None)
            return save(nf, _t(flow_lang, MSGS["trending_ask_country"]))

        if wanted_category:
            next_visible = _filter_trending_items_by_category(all_items, wanted_category)
            if not next_visible:
                return save(
                    flow,
                    _t(flow_lang, MSGS["trending_no_products_category"]).format(
                        country=_trending_footer_country_label(cc),
                        category=wanted_category,
                    ),
                )
            offset = 0
            page = next_visible[offset : offset + TRENDING_PAGE_SIZE]
            has_more = offset + len(page) < len(next_visible)
            fk, needs_c = _trending_footer_template_key(first_batch=True, has_more=has_more)
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
            }
            body = _trending_inbox_and_web_body(
                flow_lang,
                cc,
                page,
                category=wanted_category,
                start_rank=1,
                is_more_batch=False,
            )
            full_reply = _append_trending_followup_suggestions(
                flow_lang, cc, f"{body}\n\n{footer}".strip()
            )
            if ch == "whatsapp":
                wa_list: List[Dict[str, str]] = []
                no_url_lines: List[str] = []
                for i, it in enumerate(page):
                    url = (it.get("image_url") or "").strip()
                    cap = _wa_caption_for_trending_row(it, rank=offset + i + 1)
                    if url:
                        wa_list.append({"image_url": url, "caption": cap})
                    else:
                        no_url_lines.append(f"{cap}\n(no image URL — open chat on web for full list)")
                if wa_list:
                    wa_after = full_reply.strip()
                    if no_url_lines:
                        wa_after = "\n\n".join([*no_url_lines, full_reply]).strip()
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
            nf = {**flow, "step": "trending_showing_products", "lang": flow_lang}
            if desc:
                detail_msg = _t(flow_lang, MSGS["trending_product_detail_ok"]).format(
                    name=nm,
                    price_line=price_line or "—",
                    description=desc,
                )
            else:
                detail_msg = _t(flow_lang, MSGS["trending_product_detail_missing"]).format(name=nm)
            detail_msg = _append_trending_followup_suggestions(flow_lang, cc, detail_msg)
            if ch == "whatsapp":
                img_u = str(p.get("image_url") or "").strip()
                if img_u:
                    rk = _trending_global_rank(visible, p)
                    cap = _wa_caption_for_trending_row(p, rank=rk) if rk else _wa_caption_for_trending_row(p)
                    return save(
                        nf,
                        detail_msg,
                        wa_images=[{"image_url": img_u, "caption": cap}],
                        wa_text_after=detail_msg,
                    )
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
        hint = " ".join(hint_parts) + "\n"
        return ai_forward(hint + text, nf, skip_api=_default_skip_store_api(nf))

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
        if _is_natural_language(text) and not _is_likely_email(text):
            nf = _bail_to_conversational(flow, flow_lang)
            return ai_forward(text, nf, skip_api=True)
        email = (text or "").strip().lower()
        if not _is_likely_email(email):
            return save(flow, _t(flow_lang, MSGS["email_invalid"]))
        logger.info("Verification flow: sending code to %s", email)
        sent = await store_client.send_verification_code(email)
        logger.info("Verification flow: send_verification_code result for %s = %s", email, sent)
        if not sent:
            return save(flow, _t(flow_lang, MSGS["verify_send_error"]))
        f = {
            **flow,
            "pending_email": email,
            "verified": False,
            "step": "existing_awaiting_verification_code",
            "lang": flow_lang,
        }
        return save(f, _t(flow_lang, MSGS["code_sent"]).format(email=email))

    if step == "existing_awaiting_verification_code":
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

        base_f: Dict[str, Any] = {
            **flow,
            "verified": True,
            "step": "conversational",
            "customer_kind": "existing",
            "verified_customer": customer,
            "seller_id": customer.get("seller_id"),
            "customer_email": pending_email,
            "verified_at": verified_at,
            "pending_mobile": mobile,
            "pending_email": None,
            "verify_reason": None,
            "pending_order_ref": None,
            "lang": flow_lang,
        }

        intro_line = _t(flow_lang, MSGS["verification_success"])
        parts: list[str] = [intro_line]

        if oref:
            order, src = await _lookup_order(
                db, tenant_id, oref, store_client,
                seller_id=base_f.get("seller_id"),
            )
            if order:
                parts.append(_format_order_sentence(flow_lang, order))
                parts.append(_t(flow_lang, MSGS["verified_followup"]))
                return save(base_f, "\n\n".join(parts))
            if src == "api_error":
                parts.append(_t(flow_lang, MSGS["order_lookup_error"]))
                parts.append(_t(flow_lang, MSGS["verified_followup"]))
                return save(base_f, "\n\n".join(parts))
            parts.append(_t(flow_lang, MSGS["order_not_found"]))
            parts.append(_t(flow_lang, MSGS["ask_order"]))
            oid_flow = {**base_f, "step": "existing_awaiting_order_id"}
            return save(oid_flow, "\n\n".join(parts))

        if reason == "order":
            parts.append(_t(flow_lang, MSGS["ask_order"]))
            oid_flow = {**base_f, "step": "existing_awaiting_order_id"}
            return save(oid_flow, "\n\n".join(parts))

        parts.append(_t(flow_lang, MSGS["existing_customer_welcome"]))
        return save(base_f, "\n\n".join(parts))

    if step == "existing_awaiting_order_id":
        raw = (text or "").strip()
        ref = raw if _is_likely_order_id_only(raw) else (_extract_order_id_from_message(raw, phone) or raw)
        order, src = await _lookup_order(
            db, tenant_id, ref, store_client,
            seller_id=flow.get("seller_id"),
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

        if _wants_trending_products(text):
            nf = {
                **flow,
                "step": "trending_awaiting_country",
                "intro_shown": bool(flow.get("intro_shown")),
                "lang": flow_lang,
            }
            for k in (
                "trending_country",
                "trending_products_cache",
                "trending_products_all",
                "trending_category",
                "trending_offset",
            ):
                nf.pop(k, None)
            return save(nf, _t(flow_lang, MSGS["trending_ask_country"]))

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

        # Greeting: if customer_kind not yet set, ask new/existing; otherwise just ack
        if _looks_like_greeting(text):
            if kind:
                return save(
                    {**flow, "step": "conversational"},
                    _t(flow_lang, MSGS["hello_ack"]),
                )
            nf = {
                **flow,
                "step": "awaiting_customer_type",
                "intro_shown": True,
                "lang": flow_lang,
            }
            return save(nf, _t(flow_lang, MSGS["greeting"]))

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
        if flow.get("verified"):
            if _looks_like_order_status_question(text) or _is_likely_order_id_only(text):
                ref = ""
                if _is_likely_order_id_only(text):
                    ref = re.sub(r"[^\d\-#]", "", (text or "").strip()) or (text or "").strip()
                else:
                    ref = (_extract_order_id_from_message(text, phone) or "").strip()
                if ref:
                    order, src = await _lookup_order(
                        db, tenant_id, ref, store_client,
                        seller_id=flow.get("seller_id"),
                    )
                    if order:
                        f = {**flow, "step": "conversational", "lang": flow_lang}
                        return save(f, _format_order_sentence(flow_lang, order))
                    if src == "api_error":
                        f = {**flow, "step": "conversational", "lang": flow_lang}
                        return save(f, _t(flow_lang, MSGS["order_lookup_error"]))
                    f = {**flow, "step": "conversational", "lang": flow_lang}
                    return save(f, _t(flow_lang, MSGS["order_not_found"]))
                nf = {**flow, "step": "existing_awaiting_order_id", "lang": flow_lang}
                return save(nf, _t(flow_lang, MSGS["ask_order"]))
            return ai_forward(
                "[Customer question] " + text,
                {**flow, "step": "conversational"},
                skip_api=False,
            )

        # --- Existing customer (NOT yet verified): order/account questions need verification ---
        if kind == "existing" and _needs_account_verification(flow):
            if _looks_like_order_status_question(text) or _looks_like_account_question(text):
                pre_ref = ""
                if _is_likely_order_id_only(text):
                    pre_ref = re.sub(r"[^\d\-#]", "", (text or "").strip()) or (text or "").strip()
                else:
                    pre_ref = (_extract_order_id_from_message(text, phone) or "").strip()
                reason = "order" if _looks_like_order_status_question(text) else "account"
                if verification_expired_this_turn:
                    intro_key = "verification_expired_reverify"
                else:
                    intro_key = "order_verify_intro" if reason == "order" else "account_verify_intro"
                f = {
                    **flow,
                    "step": "existing_awaiting_email",
                    "verify_reason": reason,
                    "pending_order_ref": pre_ref or None,
                    "intro_shown": True,
                    "lang": flow_lang,
                }
                return save(f, _t(flow_lang, MSGS[intro_key]))

        # --- New customer or existing with general questions: answer from KB directly ---
        skip = not flow.get("verified")
        return ai_forward(
            "[Customer question] " + text if kind else text,
            {**flow, "step": "conversational", "intro_shown": True},
            skip_api=skip,
        )

    if step == "awaiting_agent":
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
