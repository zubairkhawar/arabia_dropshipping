import re
from typing import Optional, Dict, Any, Set

from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.schema import BaseMessage

from config import get_openai_api_key
from services.store_integration_service.client import StoreIntegrationClient


def _clear_llm_cache() -> None:
    AIOrchestrator._llm_cache = None
    AIOrchestrator._llm_cache_key = None


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
    - knowledge base retrieval (to be plugged in)
    - LLM reasoning and escalation decisions
    """

    _llm_cache = None
    _llm_cache_key = None

    def __init__(self):
        self.store_client = StoreIntegrationClient()

    @property
    def llm(self):
        key = get_openai_api_key()
        if key != AIOrchestrator._llm_cache_key:
            AIOrchestrator._llm_cache = ChatOpenAI(
                model_name="gpt-4o-mini",
                temperature=0.3,
                openai_api_key=key,
            )
            AIOrchestrator._llm_cache_key = key
        return AIOrchestrator._llm_cache

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
        """
        customer: Optional[Dict[str, Any]] = None
        orders: list = []

        if phone:
            customer = await self.store_client.get_customer_by_phone(phone)
            if customer and customer.get("id"):
                orders = await self.store_client.get_recent_orders_for_customer(
                    customer_id=str(customer["id"]),
                    limit=3,
                )

        order_id = _extract_order_id_from_message(message_text or "", phone)
        if order_id:
            detail = await self.store_client.get_order_by_id(order_id)
            if detail:
                orders = [detail] + [o for o in orders if str(o.get("id", o)) != str(detail.get("id", detail))]

        return {
            "customer": customer or {},
            "recent_orders": orders,
        }

    async def process_message(
        self,
        message: str,
        channel: str,
        phone: Optional[str] = None,
        store_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main AI entrypoint.
        Returns a dict with:
        - reply_text: what the bot should say
        - language: detected language
        - escalate: bool
        - context: minimal context we used
        """
        language = await self.detect_language(message)
        customer_context = await self.fetch_customer_context(phone=phone, message_text=message)

        # TODO: plug in knowledge base retrieval here. For now we just pass metadata.
        kb_snippets: str = ""

        system_prompt = ChatPromptTemplate.from_template(
            """
You are Arabia, an AI support assistant for ecommerce merchants in the Middle East.
You must always be honest about what you know.

Context:
- Channel: {channel}
- Language: {language}
- Customer: {customer_summary}
- Recent orders: {orders_summary}
- Knowledge base snippets: {kb_snippets}

If the user asks specifically for a real agent, check if escalation is needed,
but DO NOT promise an agent unless the message clearly requires it.
Respond in the same language as the user (arabic, english, or roman urdu).
Keep answers concise and friendly.

Do NOT compose welcome messages, new/existing customer prompts, numbered menus,
verification or handoff lines, or order-ID prompts — the API sends those as fixed
templates. Only answer substantive support questions in free text.
"""
        )

        customer = customer_context.get("customer") or {}
        orders = customer_context.get("recent_orders") or []

        customer_summary = (
            f"{customer.get('name') or 'Unknown'} ({customer.get('email') or 'no email'})"
            if customer
            else "Unknown"
        )
        orders_summary = "\n".join(
            f"- Order {o.get('order_number')} status: {o.get('status')}"
            for o in orders
        )

        prompt = system_prompt.format_messages(
            channel=channel,
            language=language,
            customer_summary=customer_summary,
            orders_summary=orders_summary or "No recent orders",
            kb_snippets=kb_snippets or "None",
        )

        messages: [BaseMessage] = [
            *prompt,
            # user message at the end
            # langchain_openai will convert to appropriate type
        ]
        messages.append({"role": "user", "content": message})  # type: ignore[arg-type]

        llm_response = await self.llm.ainvoke(messages)
        reply_text = llm_response.content if isinstance(llm_response, BaseMessage) else str(
            llm_response
        )

        escalate = await self.should_escalate(message)

        return {
            "reply_text": reply_text,
            "language": language,
            "escalate": escalate,
            "context": {
                "customer": customer,
                "recent_orders": orders,
            },
        }

    async def should_escalate(self, message: str) -> bool:
        """Determine if conversation should be escalated to agent."""
        message_lower = (message or "").lower()
        phrases = (
            "agent",
            "human",
            "support",
            "help",
            "talk to",
            "speak with",
            "talk to human",
            "baat karni hai",
            "madad",
            "representative",
        )
        return any(p in message_lower for p in phrases)
