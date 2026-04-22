"""Lightweight topic hints for LLM continuity (not a state machine)."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple


def _extract_country_hint(text_lower: str) -> str:
    if "pakistan" in text_lower or re.search(r"\bpak\b", text_lower):
        return "Pakistan"
    if any(x in text_lower for x in ("uae", "emirates", "dubai", "abu dhabi")):
        return "UAE"
    if any(x in text_lower for x in ("ksa", "saudi", "riyadh", "jeddah")):
        return "KSA"
    return ""


def compute_last_topic(
    user_message: str,
    fetch_context: Optional[Dict[str, Any]],
    bot_flow: Optional[Dict[str, Any]],
    *,
    previous_metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    Return (topic_code, detail). topic_code is one of:
    trending | order | invoice | verification | general
    detail is optional (e.g. country name for trending).
    """
    m = (user_message or "").strip().lower()
    fc = fetch_context if isinstance(fetch_context, dict) else {}
    bf = bot_flow if isinstance(bot_flow, dict) else {}
    prev = previous_metadata if isinstance(previous_metadata, dict) else {}
    prev_topic = (prev.get("last_topic") or "").strip().lower()
    compact = re.sub(r"\s+", " ", m).strip()
    if prev_topic == "trending" and compact in (
        "more",
        "show more",
        "next",
        "aur",
        "same",
        "haan",
        "yes",
        "ok",
        "okay",
    ):
        return "trending", (prev.get("last_topic_detail") or "").strip()

    has_order_id = bool(
        re.search(r"(?i)(?:order|ord)\s*[#:]?\s*(\d{5,12})\b|\b#\s*(\d{5,12})\b", m)
    ) or bool(re.search(r"\b\d{6,12}\b", m) and any(k in m for k in ("order", "track", "invoice")))
    order_kw = any(
        k in m
        for k in (
            "tracking",
            "track order",
            "order status",
            "order detail",
            "order ki",
            "mera order",
            "where is my order",
            "shipped",
            "delivery",
        )
    )
    if has_order_id or order_kw:
        return "order", ""

    inv_kw = any(
        k in m
        for k in (
            "invoice",
            "faloo",
            "payable",
            "unpaid",
            "paid invoice",
            "show my invoices",
            "mera invoice",
        )
    )
    if inv_kw:
        return "invoice", ""

    trend_kw = any(
        k in m
        for k in (
            "trending",
            "non-trending",
            "non trending",
            "popular product",
            "top product",
        )
    ) or ("dikhao" in m and "product" in m)
    if trend_kw:
        return "trending", _extract_country_hint(m)

    ver_kw = any(
        k in m
        for k in (
            "verify",
            "verification",
            "otp",
            "expire",
            "expired",
            "registered email",
            "email address",
        )
    )
    if ver_kw or (bf.get("verified") and "thank" in m):
        return "verification", ""

    if isinstance(fc.get("order_tracking"), dict) and fc.get("order_tracking"):
        return "order", ""

    return "general", ""


def patch_conversation_metadata_with_last_topic(
    metadata: Optional[Dict[str, Any]],
    user_message: str,
    fetch_context: Optional[Dict[str, Any]],
    bot_flow: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge last_topic / last_topic_detail into conversation_metadata."""
    out: Dict[str, Any] = dict(metadata) if isinstance(metadata, dict) else {}
    topic, detail = compute_last_topic(
        user_message,
        fetch_context,
        bot_flow,
        previous_metadata=out,
    )
    out["last_topic"] = topic
    if detail:
        out["last_topic_detail"] = detail
    else:
        out.pop("last_topic_detail", None)
    return out


def format_recent_context_hint_for_prompt(metadata: Optional[Dict[str, Any]]) -> str:
    """One line for RUNTIME_CONTEXT_TEMPLATE (previous turn's focus)."""
    if not isinstance(metadata, dict):
        return "None"
    topic = (metadata.get("last_topic") or "").strip().lower()
    detail = (metadata.get("last_topic_detail") or "").strip()
    if not topic or topic == "general":
        return "None"

    if topic == "trending":
        if detail:
            return f"The customer was recently discussing trending products ({detail})."
        return "The customer was recently discussing trending products."

    if topic == "order":
        return "The customer was recently asking about an order (status, tracking, or details)."

    if topic == "invoice":
        return "The customer was recently asking about invoices or payment status."

    if topic == "verification":
        return "The customer was recently discussing account verification (email, OTP, or expiry)."

    return "None"


def format_post_agent_close_context_for_prompt(metadata: Optional[Dict[str, Any]]) -> str:
    """
    When an agent just closed the chat, the next customer message should get a natural LLM reply
    (e.g. brief thanks acknowledgment). Not a state machine — one line of grounding for the model.
    """
    if not isinstance(metadata, dict):
        return "None"
    if not metadata.get("awaiting_first_customer_after_agent_close"):
        return "None"
    return (
        "A human agent closed this chat moments ago; Dropbot is resuming. The thread may show a "
        "short system line about that. If the customer is brief (e.g. okay/thanks), reply warmly "
        "and invite further help — do not repeat the closure notice verbatim unless needed."
    )
