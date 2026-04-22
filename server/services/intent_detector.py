"""Lightweight topic / intent detection for Redis memory (no LLM)."""
from __future__ import annotations

import re
from typing import Optional, Tuple


class IntentDetector:
    """Deterministic intent detection for short-term memory."""

    @staticmethod
    def detect_topic_and_intent(message: str) -> Tuple[Optional[str], str]:
        """
        Returns (topic, intent_type).
        topic may be None when nothing specific matches.
        """
        msg_lower = (message or "").strip().lower()
        if not msg_lower:
            return None, "general_question"

        if any(
            w in msg_lower
            for w in (
                "track",
                "where is my order",
                "order status",
                "tracking number",
                "mera order",
            )
        ):
            return "orders", "order_tracking"

        if any(
            w in msg_lower
            for w in (
                "existing customer",
                "i am existing",
                "purana customer",
                "verify",
                "verification",
                "sign in",
                "log in",
                "login",
            )
        ):
            return "verification", "verification"

        if any(
            w in msg_lower
            for w in (
                "human agent",
                "talk to human",
                "speak to someone",
                "customer care",
                "support agent",
            )
        ):
            return "escalation", "escalation"

        if "dropshipping" in msg_lower or "drop shipping" in msg_lower:
            if any(w in msg_lower for w in ("profit", "earn", "make money", "money")):
                return "dropshipping", "profit_query"
            if any(w in msg_lower for w in ("ksa", "uae", "pakistan", "country", "allowed")):
                return "dropshipping", "policy_country"
            if any(w in msg_lower for w in ("start", "begin", "how to", "setup", "set up")):
                return "dropshipping", "onboarding"
            return "dropshipping", "how_it_works"

        if "fulfillment" in msg_lower:
            return "fulfillment", "how_it_works"

        if "3pl" in msg_lower or "third party logistics" in msg_lower:
            return "threepl", "how_it_works"

        if "agency" in msg_lower or "partner" in msg_lower:
            if "commission" in msg_lower or "earn" in msg_lower:
                return "agency", "profit_query"
            return "agency", "how_it_works"

        if "profit" in msg_lower or "calculator" in msg_lower:
            return "profit", "profit_query"

        if any(w in msg_lower for w in ("payment", "payout", "payouts", "invoice")):
            return "payments", "general_question"

        if "shipping" in msg_lower:
            return "shipping", "general_question"

        if "return" in msg_lower:
            return "returns", "general_question"

        if any(
            w in msg_lower
            for w in ("trending", "products", "catalog", "show me", "dikhao")
        ):
            return "products", "product_search"

        # Full Arabia service list (Roman Urdu / English) — pairs with LLM COMPLETE SERVICES LIST in prompts.
        _svc_cat_markers = (
            "all services",
            "list of services",
            "services list",
            "what services",
            "which services",
            "kya services",
            "kya kya services",
            "sari services",
            "saari services",
            "poori services",
            "puri services",
            "full services",
            "complete services",
            "tamam services",
            "saare services",
        )
        if any(m in msg_lower for m in _svc_cat_markers):
            return "services", "service_catalog"

        return None, "general_question"

    @staticmethod
    def extract_country(message: str) -> Optional[str]:
        msg_lower = (message or "").lower()
        if any(w in msg_lower for w in ("ksa", "saudi", "السعودية")):
            return "KSA"
        if any(w in msg_lower for w in ("uae", "emirates", "dubai", "الامارات", "الإمارات")):
            return "UAE"
        if any(w in msg_lower for w in ("pk", "pakistan", "پاکستان")):
            return "PK"
        return None

    @staticmethod
    def extract_order_id(message: str) -> Optional[str]:
        m = re.search(r"\b(\d{5,12})\b", message or "")
        return m.group(1) if m else None

    @staticmethod
    def extract_product_id(message: str) -> Optional[str]:
        m = re.search(r"(?i)\b(?:product|item)\s*#?\s*(\d{2,12})\b", message or "")
        if m:
            return m.group(1)
        return None
