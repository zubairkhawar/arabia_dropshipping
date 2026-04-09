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
            "order",
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

        if phone:
            try:
                customer = await self.store_client.get_customer_by_phone(phone)
                if customer and customer.get("id"):
                    verification_method = "phone"
                    try:
                        orders = await self.store_client.get_recent_orders_for_customer(
                            customer_id=str(customer["id"]),
                            limit=3,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Store API recent orders failed")
                        store_context_error = f"orders_fetch:{exc!s}"[:220]
            except Exception as exc:  # noqa: BLE001
                logger.exception("Store API customer by phone failed")
                store_context_error = f"customer_fetch:{exc!s}"[:220]

        order_id = _extract_order_id_from_message(message_text or "", phone)
        if order_id:
            try:
                detail = await self.store_client.get_order_by_id(order_id)
                if detail:
                    orders = [detail] + [
                        o for o in orders if str(o.get("id", o)) != str(detail.get("id", detail))
                    ]
            except Exception as exc:  # noqa: BLE001
                logger.exception("Store API order by id failed")
                store_context_error = (store_context_error or "") + f" order_fetch:{exc!s}"[:220]

        return {
            "customer": customer or {},
            "recent_orders": orders,
            "is_store_customer": bool(customer and customer.get("id")),
            "verification_method": verification_method,
            "store_context_error": store_context_error,
        }

    async def should_escalate(self, message: str) -> bool:
        """Determine if conversation should be escalated to agent."""
        return wants_human_agent(message)
