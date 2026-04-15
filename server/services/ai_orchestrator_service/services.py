import logging
import re
from typing import Optional, Dict, Any, Set

from services.human_handoff_intent import wants_human_agent
from services.store_integration_service.client import StoreIntegrationClient

logger = logging.getLogger(__name__)


def _extract_order_id_from_message(message: str, phone: Optional[str]) -> Optional[str]:
    """
    Best-effort order reference from free text (e.g. "order 123432", "#123432").
    Avoids treating the full WhatsApp phone number as an order id when possible.
    """
    if not (message or "").strip():
        return None
    phone_digits = re.sub(r"\D", "", phone or "")
    for pattern in (
        r"(?i)\b(?:order|ord)\s*[#:\-]?\s*(\d{4,14})\b",
        r"#\s*(\d{4,14})\b",
    ):
        m = re.search(pattern, message)
        if m:
            return m.group(1)
    for m in re.finditer(r"\b(\d{5,12})\b", message):
        cand = m.group(1)
        if phone_digits and cand == phone_digits:
            continue
        if len(phone_digits) >= 10 and cand in phone_digits and len(cand) >= 8:
            continue
        return cand
    return None


def _extract_tracking_id_from_message(message: str) -> Optional[str]:
    text = (message or "").strip()
    if not text:
        return None
    m = re.search(r"\b([A-Z]{2}\d{6,20})\b", text.upper())
    if m:
        return m.group(1)
    return None


class AIOrchestrator:
    """
    Central place where we orchestrate:
    - language detection
    - customer/store lookups via the client's API
    - escalation heuristics

    LLM calls use langchain_bot.ArabiaLangChainBot (not this class).
    """

    def __init__(self):
        self.store_client = StoreIntegrationClient()

    async def detect_language(self, text: str) -> str:
        """
        Detect language for customer chat routing.
        Returns one of: arabic | english | roman_urdu
        """
        source = (text or "").strip()
        if not source:
            return "english"

        # Arabic script block (Arabic + supplemental ranges)
        if any(
            ("\u0600" <= ch <= "\u06FF")
            or ("\u0750" <= ch <= "\u077F")
            or ("\u08A0" <= ch <= "\u08FF")
            for ch in source
        ):
            return "arabic"

        lowered = source.lower()
        # Normalize punctuation so we can score words reliably.
        normalized = re.sub(r"[^a-z0-9\s]", " ", lowered)
        tokens = [t for t in normalized.split() if t]
        token_set = set(tokens)

        # Common Roman Urdu / Roman Hindi words and variants.
        roman_ur_words: Set[str] = {
            "kya",
            "kahan",
            "kahaan",
            "mujhay",
            "mujhe",
            "salam",
            "assalam",
            "kaisa",
            "kaise",
            "haal",
            "hain",
            "hai",
            "han",
            "hun",
            "ho",
            "rhy",
            "rahy",
            "rahe",
            "rha",
            "raha",
            "kr",
            "kar",
            "krna",
            "karna",
            "karo",
            "kerna",
            "ap",
            "aap",
            "tum",
            "mera",
            "meri",
            "mjy",
            "please",
            "plz",
            "bhai",
            "yar",
            "yaar",
            "acha",
            "achha",
            "theek",
            "thik",
            "thk",
            "nahi",
            "nhi",
            "nahin",
            "hanji",
            "ji",
            "shukriya",
            "jazakallah",
            "kab",
            "kis",
            "kyun",
            "q",
            "qa",
        }
        roman_ur_bigrams = {
            ("kya", "haal"),
            ("kya", "kar"),
            ("kya", "kr"),
            ("kr", "rhy"),
            ("kar", "rahe"),
            ("kaise", "ho"),
            ("ap", "ka"),
            ("aap", "ka"),
        }

        roman_score = 0
        english_score = 0

        for token in tokens:
            if token in roman_ur_words:
                roman_score += 2
            # lightweight english hints
            if token in {
                "hello",
                "hi",
                "thanks",
                "thank",
                "please",
                "where",
                "when",
                "order",
                "delivery",
                "status",
                "update",
                "support",
                "agent",
                "help",
            }:
                english_score += 1

        for i in range(len(tokens) - 1):
            pair = (tokens[i], tokens[i + 1])
            if pair in roman_ur_bigrams:
                roman_score += 3

        # Strong pattern for the user's examples:
        # "kya haal hain", "kya kr rhy ho"
        if "kya" in token_set and ("haal" in token_set or "kr" in token_set or "kar" in token_set):
            roman_score += 3
        if {"rhy", "ho"} <= token_set or {"rahe", "ho"} <= token_set:
            roman_score += 2

        if roman_score >= max(2, english_score + 1):
            return "roman_urdu"

        return "english"

    async def fetch_customer_context(
        self,
        phone: Optional[str],
        message_text: Optional[str] = None,
        bot_flow: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Resolve customer and recent orders via the merchant API, plus a single order
        lookup when the user message mentions an order id (e.g. GET /v1/orders/{id}).

        For personalized answers (is_store_customer, orders), the merchant must implement
        e.g. GET /customers?phone=… and GET /customers/{id}/orders — see StoreIntegrationClient.
        If those are missing, the bot still runs but store-linked context stays empty.
        """
        customer: Optional[Dict[str, Any]] = None
        orders: list = []
        store_context_error: Optional[str] = None
        verification_method = "none"
        faq_entries: list = []
        tracking_detail: Optional[Dict[str, Any]] = None
        invoices: list = []
        seller_id: Optional[str] = None

        flow = bot_flow if isinstance(bot_flow, dict) else {}
        vc = flow.get("verified_customer")
        if isinstance(vc, dict):
            customer = vc
            verification_method = "email_code"

        seller_raw = flow.get("seller_id")
        if seller_raw is not None:
            seller_id = str(seller_raw)
        elif isinstance(customer, dict) and customer.get("seller_id") is not None:
            seller_id = str(customer.get("seller_id"))

        # Only use Arabia APIs: orders by id, tracking, faq, invoice by seller_id
        if seller_id:
            try:
                inv_payload = await self.store_client.get_invoice_by_seller_id(seller_id)
                if isinstance(inv_payload.get("orders"), list):
                    orders = [x for x in inv_payload.get("orders") if isinstance(x, dict)]
                elif isinstance(inv_payload.get("data"), list):
                    orders = [x for x in inv_payload.get("data") if isinstance(x, dict)]
                if isinstance(inv_payload.get("invoices"), list):
                    invoices = [x for x in inv_payload.get("invoices") if isinstance(x, dict)]
            except Exception as exc:  # noqa: BLE001
                logger.exception("Store API invoice by seller_id failed")
                store_context_error = f"invoice_fetch:{exc!s}"[:220]

        if not seller_id and phone:
            # Preserve compatibility for channels that still only provide phone.
            try:
                customer = await self.store_client.get_customer_by_phone(phone)
                if customer and customer.get("id"):
                    verification_method = "phone"
                    if customer.get("seller_id") is not None:
                        seller_id = str(customer.get("seller_id"))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Store API customer by phone failed")
                store_context_error = (store_context_error or "") + f" customer_fetch:{exc!s}"[:220]

        order_id = _extract_order_id_from_message(message_text or "", phone)
        if order_id:
            try:
                detail = await self.store_client.get_order_by_id(order_id, seller_id=seller_id)
                if detail:
                    orders = [detail] + [
                        o for o in orders if str(o.get("id", o)) != str(detail.get("id", detail))
                    ]
            except Exception as exc:  # noqa: BLE001
                logger.exception("Store API order by id failed")
                store_context_error = (store_context_error or "") + f" order_fetch:{exc!s}"[:220]

        tracking_id = _extract_tracking_id_from_message(message_text or "")
        if tracking_id:
            try:
                tracking_detail = await self.store_client.get_tracking_status(
                    tracking_id,
                    seller_id=seller_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Store API tracking failed")
                store_context_error = (store_context_error or "") + f" tracking_fetch:{exc!s}"[:220]

        try:
            faq_entries = await self.store_client.get_faq()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Store API faq failed")
            store_context_error = (store_context_error or "") + f" faq_fetch:{exc!s}"[:220]

        return {
            "customer": customer or {},
            "recent_orders": orders,
            "is_store_customer": bool(customer and customer.get("id")),
            "verification_method": verification_method,
            "store_context_error": store_context_error,
            "seller_id": seller_id,
            "tracking_detail": tracking_detail or {},
            "faq_entries": faq_entries,
            "invoices": invoices,
        }

    async def should_escalate(self, message: str) -> bool:
        """Determine if conversation should be escalated to agent."""
        return wants_human_agent(message)
