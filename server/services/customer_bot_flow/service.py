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

from config import settings
from models import Conversation, Message, Order
from services.ai_orchestrator_service.services import (
    AIOrchestrator,
    _extract_order_id_from_message,
)
from services.store_integration_service.client import StoreIntegrationClient
from services.trending_products_service.bot_query import list_active_trending_for_country
from services.human_handoff_intent import (
    is_slash_reset_command,
    solo_menu_digit,
    wants_bot_flow_reset,
    wants_human_agent,
)
from services.customer_bot_flow.templates import BOT_FLOW_TEMPLATES

logger = logging.getLogger(__name__)

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

    asks_confirmation_service = _contains_any("confirmation") and _contains_any("service", "charges", "charge", "facility", "timing", "proof", "transparent", "whatsapp")
    if asks_confirmation_service:
        if _contains_any("pak", "pakistan"):
            if lang == "english":
                return "Order Confirmation service is currently available only in UAE and KSA. It is not available for Pakistan market right now."
            if lang == "arabic":
                return "خدمة تأكيد الطلبات متاحة حاليا فقط في الإمارات والسعودية، وهي غير متاحة حاليا لسوق باكستان."
            return "Order confirmation service filhaal sirf UAE aur KSA mein available hai. Pakistan market mein yeh service abhi available nahi hai."

    asks_confirmation_charges = _contains_any("confirmation") and _contains_any("charges", "charge", "rate", "pricing", "per order", "cost")
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

    asks_activate_confirmation = _contains_any("activate", "activated", "activation", "activate kar", "service kese", "service kaise", "confirmation service kese")
    if asks_activate_confirmation and _contains_any("confirmation"):
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
    if _contains_any("confirmation") and (asks_confirmation_timing or asks_confirmation_proof):
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
    """
    Normalize phone numbers from Pakistan (92), UAE (971), Saudi Arabia (966).
    Returns the normalized string or None when the number doesn't belong to any
    of the three supported countries.

    Pakistan  → local format  03XXXXXXXXX  (11 digits)
    UAE       → international 971XXXXXXXX  (10-12 digits)
    Saudi     → international 966XXXXXXXXX (12 digits)
    """
    s = re.sub(r"[\s\-().]+", "", (raw or "").strip())
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("00"):
        s = s[2:]
    if not s.isdigit():
        return None

    # --- Pakistan (92) ---
    # International: 923XXXXXXXXX (12 digits)
    if s.startswith("92") and len(s) == 12 and s[2] == "3":
        return "0" + s[2:]
    # Local with leading 0: 03XXXXXXXXX (11 digits)
    if s.startswith("03") and len(s) == 11:
        return s
    # Bare local (e.g. from 003XXXXXXXXX after stripping 00): 3XXXXXXXXX (10 digits)
    if s.startswith("3") and len(s) == 10:
        return "0" + s

    # --- UAE (971) ---
    if s.startswith("971") and 10 <= len(s) <= 12:
        return s

    # --- Saudi Arabia (966) ---
    if s.startswith("966") and 12 <= len(s) <= 13:
        return s

    return None


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


TRENDING_WA_MAX = 8
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


def _wa_caption_for_trending_row(it: Dict[str, Any]) -> str:
    name = str(it.get("product_name") or "").strip()
    pb = _trending_price_bit(it)
    if pb:
        return f"📦 {name}\n💰 {pb}"
    return f"📦 {name}"


def _trending_inbox_and_web_body(
    lang: str,
    country: str,
    items: List[Dict[str, Any]],
    category: Optional[str] = None,
) -> str:
    if not items:
        return _t(lang, MSGS["trending_no_products"]).format(
            country=_trending_footer_country_label(country)
        )
    if category:
        lines = [_t(lang, MSGS["trending_header_category"]).format(country=country, category=category)]
    else:
        lines = [_t(lang, MSGS["trending_header"]).format(country=country)]
    for i, it in enumerate(items, start=1):
        nm = str(it.get("product_name") or "").strip()
        pb = _trending_price_bit(it)
        price_suffix = f" — {pb}" if pb else ""
        cat = str(it.get("category") or "").strip()
        desc = str(it.get("description") or "").strip()
        img = (it.get("image_url") or "").strip()
        lines.append(f"{i}) {nm}{price_suffix}\n   {cat}")
        if desc:
            lines.append(f"   {desc}")
        if img:
            lines.append(f"   📷 {img}")
    return "\n\n".join(lines)


def _strip_trending_detail_query(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(
        r"(?i)^(?:tell me about|details on|detail on|info on|more about|what about|about)\s+",
        "",
        s,
    ).strip()
    return s


def _select_trending_product_from_cache(
    cache: List[Dict[str, Any]], text: str
) -> Optional[Dict[str, Any]]:
    if not cache or not (text or "").strip():
        return None
    raw = text.strip()
    t_norm = unicodedata.normalize("NFKC", raw).lower()
    t_norm = t_norm.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    query = _strip_trending_detail_query(t_norm)

    if re.fullmatch(r"\d+", query):
        idx = int(query) - 1
        if 0 <= idx < len(cache):
            return cache[idx]

    if query:
        for row in cache:
            nm = str(row.get("product_name") or "").strip().lower()
            if nm and (nm in query or query in nm):
                return row

        name_lowers = [str(x.get("product_name") or "").strip().lower() for x in cache]
        name_lowers = [n for n in name_lowers if n]
        best = difflib.get_close_matches(query, name_lowers, n=1, cutoff=0.55)
        if best:
            for row in cache:
                if str(row.get("product_name") or "").strip().lower() == best[0]:
                    return row

        qflat = re.sub(r"[^\w\u0600-\u06FF\s]", " ", query)
        qflat = re.sub(r"\s+", " ", qflat).strip()
        for row in cache:
            desc = str(row.get("description") or "").strip().lower()
            if len(desc) >= 10 and qflat and qflat in desc:
                return row
    return None


def _format_trending_product_detail(_lang: str, p: Dict[str, Any]) -> str:
    nm = str(p.get("product_name") or "").strip()
    cat = str(p.get("category") or "").strip()
    desc = str(p.get("description") or "").strip()
    pb = _trending_price_bit(p)
    img = (p.get("image_url") or "").strip()
    parts: List[str] = [f"📦 {nm}"]
    if cat:
        parts.append(f"📂 {cat}")
    if pb:
        parts.append(f"💰 {pb}")
    if desc:
        parts.append(desc)
    if img:
        parts.append(f"📷 {img}")
    return "\n".join(parts)


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
        "trending_awaiting_country",
        "trending_showing_products",
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
        detail = await store_client.get_order_by_id(ref)
        if not detail:
            detail = await store_client.get_order_by_number(ref)
    except Exception:
        return None, "api_error"

    if not detail:
        return None, "not_found"

    return _extract_order_fields(detail, ref), "api"


def _format_order_sentence(lang: str, o: Dict[str, Any]) -> str:
    """
    Build a natural-language sentence from all available order fields.
    Matches user language (English / Arabic / Roman Urdu).
    """
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
            return save(restored, _t(flow_lang, MSGS["resume_continued"]))
        if choice == "fresh":
            nf = _reset_bot_flow(flow_lang)
            return save(nf, _t(flow_lang, MSGS["greeting"]), skip_api=False)
        return save(flow, _t(flow_lang, MSGS["welcome_back"]))

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

    # --- New / Existing customer selection ---
    if step == "awaiting_customer_type":
        choice = _parse_choice(
            text,
            {
                "1": "new", "new": "new", "new customer": "new", "n": "new",
                "2": "existing", "existing": "existing", "old": "existing",
                "existing customer": "existing", "e": "existing",
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
        # Trending products intent at the entry menu — jump straight to trending flow
        if _wants_trending_products(text):
            nf = {
                **flow,
                "step": "trending_awaiting_country",
                "customer_kind": flow.get("customer_kind") or "new",
                "intro_shown": True,
                "lang": flow_lang,
            }
            return save(nf, _t(flow_lang, MSGS["trending_ask_country"]))

        # Product sourcing at entry menu — collect details then hand off
        if _wants_product_sourcing(text):
            product_hint = _extract_sourcing_product_name(text)
            has_bulk = bool(re.search(
                r"\b\d{2,}\s*(?:piece|pieces|pcs|unit|units|qty)\b",
                text.lower(),
            ))
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
        if _is_natural_language(text) and _parse_trending_country_reply(text) is None:
            nf = _bail_to_conversational(flow, flow_lang)
            return ai_forward(text, nf, skip_api=_default_skip_store_api(nf))
        cc = _parse_trending_country_reply(text)
        if not cc:
            return save(flow, _t(flow_lang, MSGS["trending_country_retry"]))
        wanted_category = _parse_trending_category(text)
        items_all = list_active_trending_for_country(db, tenant_id, cc)
        items_filtered = _filter_trending_items_by_category(items_all, wanted_category)
        items = items_filtered[:TRENDING_WA_MAX]
        if not items:
            # Stay in trending_awaiting_country so the user can pick another country
            nf = {**flow, "step": "trending_awaiting_country", "lang": flow_lang}
            nf.pop("trending_country", None)
            nf.pop("trending_products_cache", None)
            nf.pop("trending_products_all", None)
            nf.pop("trending_category", None)
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
        nf = {
            **flow,
            "step": "trending_showing_products",
            "lang": flow_lang,
            "trending_country": cc,
            "trending_category": wanted_category,
            "trending_products_all": items_all,
            "trending_products_cache": items,
        }
        body = _trending_inbox_and_web_body(flow_lang, cc, items, wanted_category)
        footer = _t(flow_lang, MSGS["trending_after_images_footer"]).format(
            country=_trending_footer_country_label(cc)
        )
        full_reply = f"{body}\n\n{footer}".strip()
        wa_images: Optional[List[Dict[str, str]]] = None
        wa_after: Optional[str] = None
        if ch == "whatsapp":
            wa_list: List[Dict[str, str]] = []
            no_url_lines: List[str] = []
            for it in items:
                url = (it.get("image_url") or "").strip()
                cap = _wa_caption_for_trending_row(it)
                if url:
                    wa_list.append({"image_url": url, "caption": cap})
                else:
                    no_url_lines.append(f"{cap}\n(no image URL — open chat on web for full list)")
            if wa_list:
                wa_images = wa_list
                wa_after = footer
                if no_url_lines:
                    wa_after = "\n\n".join([*no_url_lines, footer]).strip()
        return save(nf, full_reply, wa_images=wa_images, wa_text_after=wa_after)

    if step == "trending_showing_products":
        cache_raw = flow.get("trending_products_cache")
        cache: List[Dict[str, Any]] = cache_raw if isinstance(cache_raw, list) else []
        all_raw = flow.get("trending_products_all")
        all_items: List[Dict[str, Any]] = all_raw if isinstance(all_raw, list) else cache
        wanted_category = _parse_trending_category(text)
        if not cache:
            nf = {**flow, "step": "conversational", "lang": flow_lang}
            nf.pop("trending_country", None)
            nf.pop("trending_products_cache", None)
            nf.pop("trending_products_all", None)
            nf.pop("trending_category", None)
            return save(nf, _t(flow_lang, MSGS["trending_product_not_matched"]))

        if _wants_trending_products(text):
            nf = {
                **flow,
                "step": "trending_awaiting_country",
                "lang": flow_lang,
            }
            nf.pop("trending_country", None)
            nf.pop("trending_products_cache", None)
            nf.pop("trending_products_all", None)
            nf.pop("trending_category", None)
            return save(nf, _t(flow_lang, MSGS["trending_ask_country"]))

        if wanted_category:
            cc = str(flow.get("trending_country") or "").strip().upper()
            next_items = _filter_trending_items_by_category(all_items, wanted_category)[:TRENDING_WA_MAX]
            if not next_items:
                return save(
                    flow,
                    _t(flow_lang, MSGS["trending_no_products_category"]).format(
                        country=_trending_footer_country_label(cc),
                        category=wanted_category,
                    ),
                )
            nf = {
                **flow,
                "step": "trending_showing_products",
                "lang": flow_lang,
                "trending_category": wanted_category,
                "trending_products_cache": next_items,
                "trending_products_all": all_items,
            }
            body = _trending_inbox_and_web_body(flow_lang, cc, next_items, wanted_category)
            if ch == "whatsapp":
                wa_list: List[Dict[str, str]] = []
                for it in next_items:
                    url = (it.get("image_url") or "").strip()
                    if url:
                        wa_list.append({"image_url": url, "caption": _wa_caption_for_trending_row(it)})
                if wa_list:
                    return save(nf, body, wa_images=wa_list, wa_text_after=None)
            return save(nf, body)

        picked = _select_trending_product_from_cache(cache, text)
        if picked:
            detail = _format_trending_product_detail(flow_lang, picked)
            nf = {**flow, "step": "conversational", "lang": flow_lang}
            nf.pop("trending_country", None)
            nf.pop("trending_products_cache", None)
            nf.pop("trending_products_all", None)
            nf.pop("trending_category", None)
            url = (picked.get("image_url") or "").strip()
            nm = str(picked.get("product_name") or "").strip()
            pb = _trending_price_bit(picked)
            cap_lines = [f"📦 {nm}"]
            if pb:
                cap_lines.append(f"💰 {pb}")
            caption = "\n".join(cap_lines)[:1024]
            rest_parts: List[str] = []
            cat = str(picked.get("category") or "").strip()
            desc = str(picked.get("description") or "").strip()
            if cat:
                rest_parts.append(f"📂 {cat}")
            if desc:
                rest_parts.append(desc)
            if url:
                rest_parts.append(f"📷 {url}")
            wa_tail = "\n".join(rest_parts) if rest_parts else None
            if ch == "whatsapp" and url:
                return save(
                    nf,
                    detail,
                    wa_images=[{"image_url": url, "caption": caption}],
                    wa_text_after=wa_tail,
                )
            return save(nf, detail)

        if _is_natural_language(text):
            names = ", ".join(
                str(x.get("product_name") or "").strip()
                for x in cache[:TRENDING_WA_MAX]
                if (x.get("product_name") or "").strip()
            )
            nf = {**flow, "step": "trending_showing_products", "lang": flow_lang}
            hint = (
                "[Trending products shown in this chat: "
                f"{names}. User message may not match a product name; answer helpfully "
                "or ask which listed product they mean.]\n"
            )
            return ai_forward(hint + text, nf, skip_api=_default_skip_store_api(nf))

        return save(flow, _t(flow_lang, MSGS["trending_product_not_matched"]))

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
        customer = await store_client.get_customer_by_email_mobile(pending_email, mobile)
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
            order, src = await _lookup_order(db, tenant_id, oref, store_client)
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
        order, src = await _lookup_order(db, tenant_id, ref, store_client)
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
                    order, src = await _lookup_order(db, tenant_id, ref, store_client)
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
