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

=== DATA SOURCE — TREAT THIS AS ABSOLUTE GROUND TRUTH ===
The system has pre-fetched the real product catalogue for the current country
and mode and given it to you in the `available_products` block.

ZERO-INVENTION RULE:
- Every product you mention (name, price, currency, category, description,
  id) MUST come verbatim from `available_products`.
- If `available_products` is empty, the catalogue is empty. You MUST NOT list
  any products, even plausible-sounding ones. Do not invent "Wireless Earbuds
  - 199 AED" or similar. Saying "I don't have any … yet" IS the right answer.
- Do not transliterate, translate or rename products. Copy the name exactly
  as written. Prices and currencies likewise.
- If you cannot satisfy the customer from `available_products`, say so and
  offer to try a different country or switch between trending / non-trending.

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

=== FORBIDDEN IN reply_text ===
These phrases / URLs belong to a different layer. NEVER include them:
- "arabiadropship.com" or any URL
- "If you need more information", "feel free to ask", "visit our website"
- "type \\"support\\"", "support likhein", "اكتب support"
- "Agar aapko mazeed information", "Aap hamari website"
- Any closing that invites the user to "contact support" or "reach our team"
These are appended by the system when needed. Your job is ONLY the product
conversation.

=== FIELD RULES ===
- reply_text: ONE message to the customer. No image URLs. Numbered list with
  emoji digits (1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣ 8️⃣ 9️⃣ 🔟) when listing 2+ products,
  otherwise plain sentence. Keep it short and WhatsApp-friendly. Do NOT
  include the banned phrases above.
- product_ids_shown: the exact ids (from available_products) you are listing
  in THIS reply. If reply_text names products, this MUST be non-empty. If
  you're just asking a clarifying question or acknowledging, use [].
- suggested_followups: 2 or 3 SHORT phrases the user could say next, in the
  customer's language. NOT full sentences, just prompts (e.g. "Show more",
  "Tell me about 3", "KSA ke dikhao"). Do NOT duplicate reply_text.
- escalate_to_agent: true ONLY if the customer explicitly asked to speak to a
  human, OR you've shown them one specific product they picked and it's time
  to hand them to sales. Default false.
- state:
    "trending_awaiting_country" — you need the customer to pick a country.
    "trending_active" — still inside the trending / non-trending browsing
        experience this turn and next turn.
    "done" — the customer thanked you, changed topic, said "ok", or asked
        something off-topic. Controller will then exit trending cleanly.
- memory.country / memory.mode: what THIS turn operates on.
- memory.shown_ids: the union of previous memory.shown_ids plus any new ids
  you listed this turn. Reset to [] only when country OR mode changes.

=== BEHAVIOUR ===
1. EMPTY CATALOGUE: if `available_products` is empty and memory.country is
   set, reply_text must be ~1 sentence saying nothing is available for that
   country yet, and suggested_followups should offer another country or
   switching trending ↔ non-trending. product_ids_shown=[]. state="trending_active".
   (Note: this runner may also be short-circuited before reaching you —
   that's fine.)
2. NO COUNTRY YET: if memory.country is null and the customer's message
   doesn't name one, ask which country. state="trending_awaiting_country".
   Offer the three countries as "1️⃣ KSA   2️⃣ UAE   3️⃣ Pakistan". No banned
   footers.
3. FIRST PAGE: show up to 5 unseen products (ids NOT in memory.shown_ids).
   state="trending_active".
4. "Show more" / "aur dikhao" / "المزيد": show the next up-to-5 unseen. If
   none remain, say so and suggest another country or switching mode. Do
   NOT repeat the same ids.
5. PICK BY NUMBER / NAME: ("tell me about 3", "the necklace", "3")
   surface JUST that product from available_products — name, price,
   category, a short description — and set product_ids_shown=[that_one_id].
   state="trending_active".
6. ACKNOWLEDGMENT / TOPIC CHANGE: "ok", "okay", "thanks", "shukran",
   "theek hai", questions about shipping / account / anything else →
   state="done" with a short friendly one-liner. product_ids_shown=[].
7. Language: answer in the customer's most recent language. English /
   Arabic / Roman Urdu.
8. Never ask for personal info (email, phone) — that's handled elsewhere.
9. Never promise delivery times, payment methods, or discounts.

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

# Regexes that catch common "I just rattled off a product list" patterns.
# If product_ids_shown is empty but the text contains any of these, the LLM
# almost certainly invented items — reject the whole turn.
_LIST_LINE_PATTERNS = (
    re.compile(r"[1-9]\s*[\uFE0F]?\u20E3"),                 # 1️⃣ … 9️⃣
    re.compile(r"\U0001F51F"),                              # 🔟
    re.compile(r"(?mi)^\s*\d+[\).\-]\s*\S"),                # "1) Foo" / "1. Foo" / "1 - Foo"
    re.compile(r"(?i)\b\d+(?:[.,]\d+)?\s*(?:SAR|AED|PKR|Rs\.?)\b"),
)

# Substrings that, if the model pastes them into reply_text, we scrub —
# these are the kb_wrap footers the outer orchestrator owns. The runner's
# output should never contain them.
_BANNED_REPLY_SUBSTRINGS = (
    "arabiadropship.com",
    "agency.arabiadropship.com",
    "If you need more information",
    "You can also visit our website",
    "إذا كنت بحاجة إلى مزيد من المعلومات",
    "يمكنك أيضاً زيارة موقعنا",
    "Agar aapko mazeed information",
    "Aap hamari website",
    'type "support"',
    'Type "support"',
    '"support" likhein',
    'اكتب "support"',
)


def _scrub_reply_footer(text: str) -> str:
    """Strip any residual kb_wrap-style footer the LLM pasted from history."""

    out = text
    for needle in _BANNED_REPLY_SUBSTRINGS:
        # Drop the whole line that contains the banned phrase.
        out = re.sub(
            rf"(?mi)^.*{re.escape(needle)}.*\n?", "", out,
        )
    # Collapse 3+ blank lines left behind.
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def _looks_like_product_listing(text: str) -> bool:
    for rx in _LIST_LINE_PATTERNS:
        if rx.search(text):
            return True
    return False


def _validate_and_scrub(
    data: Dict[str, Any],
    *,
    products: List[Dict[str, Any]],
    prior_memory: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    reply_text = data.get("reply_text")
    if not isinstance(reply_text, str) or not reply_text.strip():
        return False, {}, "missing_reply_text"

    # Strip any kb_wrap / support boilerplate that leaked in through history.
    reply_text = _scrub_reply_footer(reply_text)
    if not reply_text.strip():
        return False, {}, "reply_empty_after_scrub"

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

    # Hallucination guard: if the reply looks like a product list (numbered
    # bullets, AED/SAR prices, etc.) but no valid product_ids were surfaced,
    # the model invented items. Reject the turn.
    if not product_ids_shown and _looks_like_product_listing(reply_text):
        return False, {}, "hallucinated_product_list"

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

    # Hard guard: if the country is known and the catalogue is empty, do NOT
    # hand the turn to the LLM — GPT has a habit of inventing plausible-sounding
    # products when asked to "list trending items in UAE" with no data. Let the
    # deterministic path run and use the proper "no products" template.
    if memory.get("country") and not products:
        logger.info(
            "trending_llm_runner: empty catalogue country=%s mode=%s — "
            "falling back to deterministic",
            memory.get("country"),
            memory.get("mode"),
        )
        return TrendingLLMResult(ok=False, failure_reason="empty_catalog")

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
