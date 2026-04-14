"""
Detect when a customer wants a human agent (English, Arabic script, Roman Urdu).

Lives outside customer_bot_flow so ai_orchestrator can import it without pulling
SQLAlchemy via customer_bot_flow.__init__.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def is_slash_reset_command(text: str) -> bool:
    """Exact `/reset` (case-insensitive, optional surrounding whitespace)."""
    return bool(re.match(r"^/reset\s*$", (text or "").strip(), re.IGNORECASE))


def wants_human_agent(text: str) -> bool:
    """
    True if the message clearly asks to speak with a person / agent / support human.

    Aligns with bot languages: english, arabic (script), roman_urdu (Latin letters).
    """
    raw = (text or "").strip()
    if not raw:
        return False

    s = _nfkc(raw)
    lowered = s.lower()

    # Latin / Roman Urdu (ASCII and common chat spellings)
    latin_phrases: Iterable[str] = (
        "support",
        "agent",
        "help",
        "real agent",
        "actual agent",
        "live agent",
        "human agent",
        "human",
        "talk to human",
        "talk to someone",
        "talk to a person",
        "talk to person",
        "speak to someone",
        "speak with",
        "talk to",
        "real person",
        "live person",
        "human being",
        "customer service",
        "customer care",
        "representative",
        "help me talk",
        "baat karni hai",
        "baat karna hai",
        "insaan se",
        "bande se",
        "aadmi se",
        "asaal agent",
        "asli agent",
        "sachcha agent",
        "madad",
    )
    if any(p in lowered for p in latin_phrases):
        return True

    # Arabic script (templates / WhatsApp Arabic)
    if any(
        ("\u0600" <= ch <= "\u06FF")
        or ("\u0750" <= ch <= "\u077F")
        or ("\u08A0" <= ch <= "\u08FF")
        for ch in s
    ):
        arabic_markers = (
            "موظف",
            "وكيل",
            "ممثل",
            "دعم",
            "مساعدة",
            "إنسان",
            "انسان",
            "حقيقي",
            "حقيقى",
            "تحدث",
            "تكلم",
            "كلام",
            "موظف حقيقي",
            "خدمة العملاء",
            "الدعم",
        )
        if any(m in s for m in arabic_markers):
            return True

    return False


def wants_bot_flow_reset(text: str) -> bool:
    """
    Customer wants to restart the scripted bot (clear stale session / see 1–2 entry again).
    """
    raw = (text or "").strip()
    if not raw:
        return False
    s = _nfkc(raw)
    lowered = s.lower()

    lowered_stripped = lowered.strip()
    if lowered_stripped == "reset":
        return True

    latin = (
        "start over",
        "start again",
        "restart",
        "main menu",
        "go to menu",
        "back to menu",
        "new chat",
        "reset chat",
        "begin again",
        "from the beginning",
        "wapas menu",
        "dobara menu",
        "dubara se",
        "pehle wala menu",
        "naya chat",
    )
    if any(p in lowered for p in latin):
        return True

    if any(
        ("\u0600" <= ch <= "\u06FF")
        or ("\u0750" <= ch <= "\u077F")
        or ("\u08A0" <= ch <= "\u08FF")
        for ch in s
    ):
        arabic = (
            "القائمة الرئيسية",
            "من البداية",
            "ابدأ من جديد",
            "من جديد",
            "القائمة",
        )
        if any(m in s for m in arabic):
            return True

    return False


def solo_menu_digit(text: str, allowed: str) -> str | None:
    """
    If the message is essentially a single menu digit (incl. Arabic-Indic), return it.
    `allowed` e.g. "12" or "123".
    """
    t = _nfkc((text or "").strip())
    t = t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    digits = re.sub(r"[^\d]", "", t)
    if len(digits) == 1 and digits in allowed:
        return digits
    return None
