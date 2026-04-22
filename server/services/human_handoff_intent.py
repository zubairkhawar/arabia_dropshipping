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


def is_conversational_acknowledgment(text: str) -> bool:
    """
    Short replies that should not count as asking for a human (okay, thanks, etc.).
    Used to avoid re-handoff after an agent closes the chat or while awaiting_agent is stale.
    """
    raw = (text or "").strip()
    if not raw:
        return True

    s = _nfkc(raw).lower()
    s = re.sub(r"[^\w\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return True

    exact = {
        "ok",
        "okay",
        "k",
        "kk",
        "yes",
        "yeah",
        "yep",
        "yup",
        "no",
        "nope",
        "nah",
        "sure",
        "fine",
        "alright",
        "cool",
        "nice",
        "great",
        "good",
        "thanks",
        "thank you",
        "thx",
        "ty",
        "np",
        "noted",
        "understood",
        "got it",
        "gotcha",
        "sounds good",
        "appreciate it",
        "thank u",
        "tysm",
    }
    if s in exact:
        return True

    tokens = s.split()
    if len(tokens) > 4:
        return False

    ack_tokens = {
        "ok",
        "okay",
        "yes",
        "yeah",
        "yep",
        "yup",
        "no",
        "nope",
        "nah",
        "thanks",
        "thank",
        "you",
        "thx",
        "ty",
        "sure",
        "fine",
        "cool",
        "great",
        "good",
        "very",
        "much",
        "so",
        "noted",
    }
    return all(t in ack_tokens for t in tokens)


def wants_human_agent(text: str) -> bool:
    """
    True if the message clearly asks to speak with a person / agent / support human.

    Aligns with bot languages: english, arabic (script), roman_urdu (Latin letters).
    """
    raw = (text or "").strip()
    if not raw:
        return False

    if is_conversational_acknowledgment(raw):
        return False

    s = _nfkc(raw)
    lowered = s.lower()

    # Multi-word phrases: specific enough for safe substring matching
    phrases: Iterable[str] = (
        "real agent",
        "actual agent",
        "live agent",
        "human agent",
        "talk to human",
        "talk to someone",
        "talk to a person",
        "talk to person",
        "talk to agent",
        "speak to someone",
        "speak with agent",
        "speak with human",
        "real person",
        "live person",
        "human being",
        "customer service",
        "customer care",
        "representative",
        "help me talk",
        "connect me",
        "connect me to support",
        "connect me to an agent",
        "connect me with support",
        "connect me with an agent",
        "take me to support",
        "take me to an agent",
        "get me to support",
        "get me an agent",
        "put me through to support",
        "put me through to an agent",
        "speak to support",
        "talk to support",
        "transfer me",
        "baat karni hai",
        "baat karna hai",
        "insaan se baat",
        "bande se baat",
        "aadmi se baat",
        "asaal agent",
        "asli agent",
        "sachcha agent",
        "try again for support",
        "need support",
        "need agent",
        "need human",
        "want support",
        "want agent",
        "want human",
        "get support",
        "get agent",
        "agent chahiye",
        "support chahiye",
        "agent se baat",
        # Roman Urdu: "connect me to support / talk to support"
        "support say baat",
        "support se baat",
        "support say milao",
        "support se milao",
        "support say milwao",
        "support se milwao",
        "agent say baat",
        "agent say milao",
        "agent se milao",
        "support ko bulao",
        "agent ko bulao",
        "baat karwao",
        "baat krawao",
        "baat krwao",
        "baat karwa do",
        "baat karwa dein",
        "connect karo",
        "connect kar do",
        "connect kara do",
        "milao mujhe",
        "mujhe milao",
        "mujhe connect",
        "support lay jao",
        "support le jao",
        "support ley jao",
        # Support number / contact requests — customer wants to reach a person
        "support number",
        "support ka number",
        "customer support number",
        "customer care number",
        "customer support ka number",
        "helpline number",
        "contact number",
        "phone number de",
        "number mil sakta",
        "number mil skta",
        "number de do",
        "number dedo",
        "number chahiye",
        "number btao",
        "number batao",
        "kis se rabta",
        "kis se contact",
        "kisse rabta",
        "kisse contact",
        "who should i contact",
        "how to contact",
        "how can i contact",
        "how do i contact",
        "give me number",
        "contact details",
    )
    if any(p in lowered for p in phrases):
        return True

    # Solo keywords only escalate in very short messages (≤ 3 words)
    # so "madad" alone escalates but "kiya madad kar lo gy" does not.
    tokens = lowered.split()
    if len(tokens) <= 3:
        solo = {"support", "agent", "help", "human", "madad", "insaan"}
        if any(t in solo for t in tokens):
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
