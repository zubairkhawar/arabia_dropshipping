"""LLM-driven trending / non-trending product conversation runner.

This module owns the entire trending product browsing experience for the
customer bot. It replaces the deterministic ``_show_trending_for_country`` and
``trending_showing_products`` branches in ``service.py`` with a single
LLM-rendered turn per customer message.

Design:

* **No tool calling loop.** To stay compatible with ``langchain-openai==0.0.2``
  and to keep latency predictable, the runner *pre-fetches* the relevant data
  from the database (active products in the active mode/country) and hands the
  fully-resolved product list to the LLM as context. The LLM then emits one
  strict-JSON envelope describing what to say, which products it's showing and
  whether to hand off to an agent. The runner resolves image URLs from the
  pre-fetched list so the LLM can never hallucinate a URL.

* **State is tiny.** Per-conversation memory is three keys::

      {"country": "KSA"|"UAE"|"PK"|None,
       "mode": "trending"|"non_trending",
       "shown_ids": [int, ...]}

  The runner seeds this from the incoming ``flow`` dict, updates it, and hands
  it back so ``service.py`` can persist it onto ``conversation.metadata``.

* **Defensive by construction.** If the LLM output fails validation or the
  OpenAI call throws, the runner returns ``ok=False`` and the caller falls
  back to the deterministic path — the user always gets *some* answer.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from config import get_openai_api_key, settings
from services.trending_products_service.bot_query import (
    list_active_non_trending_for_country,
    list_active_trending_for_country,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

TRENDING_LLM_MAX_OUTPUT_TOKENS = 600
TRENDING_LLM_TIMEOUT_SECONDS = 12.0
TRENDING_LLM_PAGE_SIZE = 5
TRENDING_LLM_MAX_PRODUCTS_IN_CONTEXT = 25

COUNTRY_ALIASES: Dict[str, str] = {
    "ksa": "KSA",
    "saudi": "KSA",
    "saudia": "KSA",
    "saudi arabia": "KSA",
    "السعودية": "KSA",
    "المملكة": "KSA",
    "uae": "UAE",
    "emirates": "UAE",
    "united arab emirates": "UAE",
    "الإمارات": "UAE",
    "الامارات": "UAE",
    "pk": "PK",
    "pakistan": "PK",
    "pakistani": "PK",
    "باكستان": "PK",
    "پاکستان": "PK",
}

_COUNTRY_PICK_DIGIT = {"1": "KSA", "2": "UAE", "3": "PK"}


@dataclass
class TrendingLLMResult:
    """Outcome of one LLM-rendered trending turn.

    ``ok=False`` means: don't trust any of the other fields — the caller
    should fall back to the deterministic trending flow.
    """

    ok: bool
    reply_text: str = ""
    image_urls: List[str] = field(default_factory=list)
    suggested_followups: List[str] = field(default_factory=list)
    escalate: bool = False
    state: str = "done"
    # Memory to persist back onto the conversation flow.
    memory: Dict[str, Any] = field(default_factory=dict)
    # Whether the LLM asked us to clear state and return to conversational
    # mode (used when the customer drops out of the trending topic).
    exit_trending: bool = False
    # Raw product rows the LLM claimed it's showing this turn, in the order
    # the LLM listed them. Used by the caller to build per-product WhatsApp
    # image payloads with correct captions.
    shown_products: List[Dict[str, Any]] = field(default_factory=list)
    failure_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------


def load_memory_from_flow(flow: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the compact trending memory dict from the wider flow state."""

    raw_country = str(flow.get("trending_country") or "").strip().upper()
    country = raw_country if raw_country in {"KSA", "UAE", "PK"} else None
    raw_mode = str(flow.get("trending_mode") or "").strip().lower()
    mode = "non_trending" if raw_mode == "non_trending" else "trending"
    shown = flow.get("trending_shown_ids")
    shown_ids: List[int] = []
    if isinstance(shown, list):
        for x in shown:
            try:
                shown_ids.append(int(x))
            except (TypeError, ValueError):
                continue
    return {"country": country, "mode": mode, "shown_ids": shown_ids}


def memory_to_flow_patch(memory: Dict[str, Any]) -> Dict[str, Any]:
    """Build the subset of flow keys we want to persist on the conversation."""

    return {
        "trending_country": memory.get("country"),
        "trending_mode": memory.get("mode") or "trending",
        "trending_shown_ids": list(memory.get("shown_ids") or []),
    }


# ---------------------------------------------------------------------------
# Preflight: extract light intent from the raw message so the LLM doesn't have
# to re-derive it. These heuristics are narrow on purpose — anything ambiguous
# is left for the LLM to decide.
# ---------------------------------------------------------------------------


def _detect_country(msg: str) -> Optional[str]:
    s = (msg or "").strip().lower()
    if not s:
        return None
    if s in _COUNTRY_PICK_DIGIT:
        return _COUNTRY_PICK_DIGIT[s]
    for alias, iso in COUNTRY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", s):
            return iso
    return None


_NON_TRENDING_RE = re.compile(
    r"(non[-\s]*trending|not\s+trending|un\s*trending|"
    r"غير\s*(?:ال)?رائج|ليست?\s*رائج|ليس\s*رائج|ما\s*رائج|"
    r"trending\s+(?:nahi|nahin|nhi|nahe|nai)\b|"
    r"(?:nahi|nahin|nhi|nahe|nai)\s+trending|"
    r"non\s*trend)",
    re.IGNORECASE,
)

_TRENDING_RE = re.compile(
    r"(^|\b)(trending|hot|popular|best\s*sell|رائج|trend\s*kar|trend\s*hue)",
    re.IGNORECASE,
)


def _detect_mode(msg: str, prior: str) -> str:
    s = (msg or "").lower()
    if _NON_TRENDING_RE.search(s):
        return "non_trending"
    if _TRENDING_RE.search(s):
        return "trending"
    return prior


# ---------------------------------------------------------------------------
# Data shaping — trim the product list to what the LLM actually needs
# ---------------------------------------------------------------------------


def _compact_product(p: Dict[str, Any]) -> Dict[str, Any]:
    """Project a full product row to just what the LLM needs to see."""

    try:
        price = float(p.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0
    desc = str(p.get("description") or "").strip()
    if len(desc) > 400:
        desc = desc[:397] + "…"
    return {
        "id": int(p["id"]),
        "name": str(p.get("product_name") or "").strip(),
        "price": price,
        "currency": str(p.get("currency") or "").strip(),
        "category": str(p.get("category") or "").strip() or None,
        "description": desc,
    }


def _fetch_products(
    db: Session, tenant_id: int, country: str, mode: str
) -> List[Dict[str, Any]]:
    if mode == "non_trending":
        return list_active_non_trending_for_country(db, tenant_id, country)
    return list_active_trending_for_country(db, tenant_id, country)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """You are the "Trending Products" specialist for Arabia Dropship,
a dropshipping marketplace serving KSA (Saudi Arabia), UAE and Pakistan (PK).

Your ONE job: help the customer browse and pick from the TRENDING or NON-TRENDING
product list for one country. You do nothing else.

=== TOOL YOU RELY ON ===
The system has already fetched the product list for the current country/mode
and given it to you in the `available_products` block. The list is ordered
1..N. Products the customer has already been shown live in `memory.shown_ids`.
Never invent products, prices, categories, descriptions or image URLs that are
not in `available_products`. If a piece of data is missing, say so plainly.

=== OUTPUT — STRICT JSON, NO MARKDOWN FENCES, NO EXTRA TEXT ===
Return exactly one JSON object with this shape:
{
  "reply_text": "<string, in customer_language>",
  "product_ids_shown": [<int>, ...],
  "suggested_followups": ["<string>", "<string>", "<string>"],
  "escalate_to_agent": <bool>,
  "state": "trending_active" | "trending_awaiting_country" | "done",
  "memory": {
    "country": "KSA" | "UAE" | "PK" | null,
    "mode": "trending" | "non_trending",
    "shown_ids": [<int>, ...]
  }
}

Field rules:
- reply_text: one message to the customer. Do NOT include raw image URLs —
  the system attaches images separately based on product_ids_shown.
  Keep it short; WhatsApp-friendly; numbered list style with emoji digits
  (1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣ 8️⃣ 9️⃣ 🔟) when listing 2+ products.
- product_ids_shown: the exact ids (from available_products) you are showing
  in this reply. When just acknowledging / asking a clarifying question, use [].
- suggested_followups: 2 or 3 very short phrases the user could say next.
  Use the customer's language. Never duplicate what you just said.
- escalate_to_agent: true ONLY if the customer explicitly asked to speak to a
  human, OR you've shown them one specific product they picked and it makes
  sense to hand them to sales. Default false.
- state:
    "trending_awaiting_country" — you need the customer to tell you which
        country (ask them; offer KSA / UAE / Pakistan).
    "trending_active" — you're actively showing / paginating / detailing
        products; stay in the trending flow next turn.
    "done" — the customer wants something else entirely, or you've
        escalated. Controller will exit the trending flow.
- memory.country / memory.mode: reflect what the current turn uses.
- memory.shown_ids: union of the previous shown_ids plus any new
  product_ids_shown in this turn. Never shrink it unless the country or
  mode changed (then start fresh).

=== BEHAVIOUR ===
1. If `available_products` is empty and memory.country is set, tell the
   customer there are none and offer: a) another country, b) switching
   between trending and non-trending. state="trending_active".
2. If memory.country is null and you can't infer it from the message, ask
   which country: KSA / UAE / Pakistan. state="trending_awaiting_country".
3. Paginate in batches of up to 5. Prefer products whose id is NOT in
   memory.shown_ids. If the user says anything like "show me more" /
   "aur dikhao" / "المزيد", show the next up-to-5 unseen. If none remain,
   say so and suggest another country/mode.
4. If the customer picks a specific product by number or by name (e.g.
   "tell me about 3" or "the necklace"), show just that product's details
   from available_products — price, category, short description — and set
   product_ids_shown=[that_one_id]. Do NOT re-send images the user has
   already seen; product_ids_shown only drives images for NEW product ids.
5. If the customer thanks you, says ok, changes topic, or asks something
   off-topic (shipping, account, agent hours, other products), set
   state="done" and leave a brief graceful reply — the main bot will pick
   up the conversation.
6. Language: answer in the customer's language. If language is "arabic" use
   Arabic. If "roman_urdu" use Roman Urdu. If "english" use English. If the
   customer's most recent message is clearly in a different language,
   match the most recent message instead.
7. Never ask for personal info (email, phone). That's handled elsewhere.
8. Never promise delivery times, payment methods or discounts — you don't
   know those here.

Return ONLY the JSON object. No prose before or after it.
"""


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------


def _build_context_block(
    *,
    memory: Dict[str, Any],
    products: List[Dict[str, Any]],
    customer_language: str,
    channel: str,
    user_message: str,
    history_block: str,
) -> str:
    compact = [_compact_product(p) for p in products[:TRENDING_LLM_MAX_PRODUCTS_IN_CONTEXT]]
    ctx = {
        "customer_language": customer_language,
        "channel": channel,
        "memory": {
            "country": memory.get("country"),
            "mode": memory.get("mode") or "trending",
            "shown_ids": list(memory.get("shown_ids") or []),
        },
        "available_products": compact,
        "available_products_total": len(products),
        "page_size": TRENDING_LLM_PAGE_SIZE,
    }
    parts = [
        "=== Context (JSON) ===",
        json.dumps(ctx, ensure_ascii=False),
    ]
    if history_block.strip():
        parts.append("")
        parts.append("=== Recent conversation ===")
        parts.append(history_block.strip())
    parts.append("")
    parts.append("=== Latest customer message ===")
    parts.append(user_message.strip() or "(empty)")
    return "\n".join(parts)


async def _call_llm(system_prompt: str, user_block: str) -> Optional[str]:
    key = get_openai_api_key()
    if not key:
        logger.warning("trending_llm_runner: no OpenAI API key configured")
        return None
    try:
        llm = ChatOpenAI(
            model_name=settings.openai_model,
            temperature=0.2,
            openai_api_key=key,
            max_tokens=TRENDING_LLM_MAX_OUTPUT_TOKENS,
            model_kwargs={"response_format": {"type": "json_object"}},
            request_timeout=TRENDING_LLM_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception("trending_llm_runner: ChatOpenAI init failed")
        return None
    try:
        resp = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_block)]
        )
    except Exception:
        logger.exception("trending_llm_runner: OpenAI call failed")
        return None
    content = getattr(resp, "content", None)
    if isinstance(content, str):
        return content.strip()
    if content is not None:
        return str(content).strip()
    return None


# ---------------------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------------------


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """Parse the LLM output, tolerating stray markdown fences."""

    s = (raw or "").strip()
    if not s:
        return None
    if s.startswith("```"):
        # Strip ``` fences if the model ignored response_format.
        s = re.sub(r"^```(?:json)?", "", s).strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        # Last-ditch: grab the outermost {...} block.
        match = re.search(r"\{.*\}", s, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


_ALLOWED_STATES = {"trending_active", "trending_awaiting_country", "done"}
_ALLOWED_MODES = {"trending", "non_trending"}
_ALLOWED_COUNTRIES = {"KSA", "UAE", "PK"}


def _validate_and_scrub(
    data: Dict[str, Any],
    *,
    products: List[Dict[str, Any]],
    prior_memory: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    reply_text = data.get("reply_text")
    if not isinstance(reply_text, str) or not reply_text.strip():
        return False, {}, "missing_reply_text"

    ids_raw = data.get("product_ids_shown") or []
    if not isinstance(ids_raw, list):
        return False, {}, "bad_product_ids_shown_type"
    valid_ids_set = {int(p["id"]) for p in products if "id" in p}
    product_ids_shown: List[int] = []
    for x in ids_raw:
        try:
            xi = int(x)
        except (TypeError, ValueError):
            continue
        if xi in valid_ids_set and xi not in product_ids_shown:
            product_ids_shown.append(xi)

    followups_raw = data.get("suggested_followups") or []
    followups: List[str] = []
    if isinstance(followups_raw, list):
        for f in followups_raw[:3]:
            if isinstance(f, str):
                fs = f.strip()
                if 0 < len(fs) <= 120:
                    followups.append(fs)

    escalate = bool(data.get("escalate_to_agent", False))

    state = data.get("state") or "trending_active"
    if state not in _ALLOWED_STATES:
        state = "trending_active"

    mem_raw = data.get("memory") or {}
    if not isinstance(mem_raw, dict):
        mem_raw = {}
    country = mem_raw.get("country")
    if isinstance(country, str):
        country = country.strip().upper() or None
    if country not in _ALLOWED_COUNTRIES:
        country = None
    mode = mem_raw.get("mode")
    if not isinstance(mode, str) or mode.strip().lower() not in _ALLOWED_MODES:
        mode = prior_memory.get("mode") or "trending"
    else:
        mode = mode.strip().lower()

    shown_raw = mem_raw.get("shown_ids") or []
    if not isinstance(shown_raw, list):
        shown_raw = []
    shown_ids: List[int] = []
    for x in shown_raw:
        try:
            xi = int(x)
        except (TypeError, ValueError):
            continue
        if xi not in shown_ids:
            shown_ids.append(xi)
    # Always include what was shown this turn.
    for xi in product_ids_shown:
        if xi not in shown_ids:
            shown_ids.append(xi)
    # If country or mode changed, prune any shown_ids that don't exist in the
    # new product universe — they're meaningless now.
    if country != prior_memory.get("country") or mode != (prior_memory.get("mode") or "trending"):
        shown_ids = [i for i in shown_ids if i in valid_ids_set]

    clean = {
        "reply_text": reply_text.strip(),
        "product_ids_shown": product_ids_shown,
        "suggested_followups": followups,
        "escalate_to_agent": escalate,
        "state": state,
        "memory": {
            "country": country,
            "mode": mode,
            "shown_ids": shown_ids,
        },
    }
    return True, clean, None


def _image_urls_for_ids(
    ids: Sequence[int],
    products: List[Dict[str, Any]],
    *,
    already_shown: Sequence[int],
) -> List[str]:
    """Resolve product ids to image URLs, skipping anything already shown.

    Trending rows may carry multiple images. We keep the list flat and in the
    same order as ``ids`` so the UI layer can match captions / ranks.
    """

    by_id = {int(p["id"]): p for p in products if "id" in p}
    already = set(int(x) for x in already_shown)
    urls: List[str] = []
    for pid in ids:
        if pid in already:
            continue
        row = by_id.get(int(pid))
        if not row:
            continue
        imgs = row.get("image_urls") or []
        if isinstance(imgs, list) and imgs:
            for u in imgs:
                if isinstance(u, str) and u.strip():
                    urls.append(u.strip())
        else:
            single = row.get("image_url")
            if isinstance(single, str) and single.strip():
                urls.append(single.strip())
    return urls


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_trending_llm(
    *,
    user_message: str,
    channel: str,
    language: str,
    flow: Dict[str, Any],
    db: Session,
    tenant_id: int,
    conversation_history_block: str = "",
) -> TrendingLLMResult:
    """Run one LLM turn for the trending / non-trending flow.

    ``flow`` is the current bot flow dict; the runner reads memory off it and
    returns memory that the caller should merge back. ``user_message`` is the
    raw customer text for this turn.
    """

    memory = load_memory_from_flow(flow)

    # Preflight enrichment: cheap, narrow heuristics only.
    new_country = _detect_country(user_message)
    if new_country and new_country != memory.get("country"):
        memory["country"] = new_country
        memory["shown_ids"] = []
    new_mode = _detect_mode(user_message, memory.get("mode") or "trending")
    if new_mode != memory.get("mode"):
        memory["mode"] = new_mode
        memory["shown_ids"] = []

    # Fetch products if we know the country. If not, the LLM will ask.
    products: List[Dict[str, Any]] = []
    if memory.get("country"):
        try:
            products = _fetch_products(db, tenant_id, memory["country"], memory["mode"])
        except Exception:
            logger.exception(
                "trending_llm_runner: product fetch failed tenant=%s country=%s mode=%s",
                tenant_id,
                memory.get("country"),
                memory.get("mode"),
            )
            return TrendingLLMResult(ok=False, failure_reason="product_fetch_failed")

    ctx_block = _build_context_block(
        memory=memory,
        products=products,
        customer_language=language or "english",
        channel=channel or "web",
        user_message=user_message or "",
        history_block=conversation_history_block or "",
    )

    logger.info(
        "trending_llm_runner: tenant=%s country=%s mode=%s products=%d shown=%d "
        "channel=%s lang=%s msg=%r",
        tenant_id,
        memory.get("country"),
        memory.get("mode"),
        len(products),
        len(memory.get("shown_ids") or []),
        channel,
        language,
        (user_message or "")[:120],
    )

    raw = await _call_llm(_SYSTEM_PROMPT, ctx_block)
    if not raw:
        return TrendingLLMResult(ok=False, failure_reason="llm_no_output")

    data = _parse_json(raw)
    if data is None:
        logger.warning("trending_llm_runner: could not parse LLM output: %r", raw[:200])
        return TrendingLLMResult(ok=False, failure_reason="unparseable_json")

    ok, clean, reason = _validate_and_scrub(data, products=products, prior_memory=memory)
    if not ok:
        logger.warning(
            "trending_llm_runner: validation failed reason=%s raw=%r", reason, raw[:200]
        )
        return TrendingLLMResult(ok=False, failure_reason=reason)

    prior_shown = set(memory.get("shown_ids") or [])
    fresh_shown_ids = [pid for pid in clean["product_ids_shown"] if pid not in prior_shown]
    image_urls = _image_urls_for_ids(fresh_shown_ids, products, already_shown=set())
    by_id = {int(p["id"]): p for p in products if "id" in p}
    shown_products = [by_id[pid] for pid in fresh_shown_ids if pid in by_id]

    exit_trending = clean["state"] == "done"

    result = TrendingLLMResult(
        ok=True,
        reply_text=clean["reply_text"],
        image_urls=image_urls,
        suggested_followups=clean["suggested_followups"],
        escalate=bool(clean["escalate_to_agent"]),
        state=clean["state"],
        memory=clean["memory"],
        exit_trending=exit_trending,
        shown_products=shown_products,
    )
    logger.info(
        "trending_llm_runner: ok state=%s esc=%s shown_now=%d images=%d "
        "followups=%d",
        result.state,
        result.escalate,
        len(clean["product_ids_shown"]),
        len(result.image_urls),
        len(result.suggested_followups),
    )
    return result
