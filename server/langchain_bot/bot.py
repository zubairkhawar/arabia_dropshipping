from datetime import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from langchain_openai import ChatOpenAI
from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import get_openai_api_key, settings
from models import Broadcast, Conversation, KnowledgeSource, Message, TenantSchedule
from langchain_bot.conversation_hints import format_post_agent_close_context_for_prompt
from langchain_bot.context_format import (
    build_customer_identity_summary,
    format_invoices_summary_for_llm,
    format_order_discovery_for_llm,
    format_order_invoice_match_hints,
    format_orders_summary_for_llm,
)
from langchain_bot.kb_followup_hints import dedupe_suggestions, heuristic_kb_followups
from langchain_bot.prompts import (
    build_prompt,
    knowledge_gap_reply,
    llm_unavailable_reply,
    normalize_context_text,
    now_utc_iso,
    strip_followup_block_when_disabled,
    strip_followup_suggestions_block,
)
from services.agent_availability_context import format_agent_availability_json_for_prompt
from services.tenant_schedule_text import format_tenant_schedule_for_customer

logger = logging.getLogger(__name__)

KB_QUERY_SYNONYMS: Dict[str, List[str]] = {
    "kitny": ["how", "many", "count"],
    "kitne": ["how", "many", "count"],
    "countries": ["country", "market", "coverage"],
    "country": ["countries", "market", "coverage"],
    "konsi": ["which", "active", "market"],
    "kon": ["which", "active", "market"],
    "successful": ["active", "performance", "dispatch"],
    "success": ["active", "performance", "dispatch"],
    "reliable": ["trusted", "performance", "dispatch", "sellers"],
    "bharosa": ["trusted", "reliable", "performance"],
    "confirmation": ["confirm", "whatsapp", "attempt", "proof", "screenshot"],
    "confirm": ["confirmation", "attempt", "proof", "screenshot"],
    "timing": ["attempt", "times", "response", "order"],
    "time": ["timing", "attempt", "delivery"],
    "transparent": ["transparency", "proof", "screenshot", "dashboard"],
    "proof": ["screenshot", "documented", "confirmation"],
    "charges": ["pricing", "charge", "aed", "sar", "pkr"],
    "charge": ["charges", "pricing", "aed", "sar", "pkr"],
    "service": ["services", "offered", "available"],
    "pak": ["pakistan"],
    "ksa": ["saudi", "saudiarabia", "market"],
    "uae": ["emirates", "market"],
    "qatar": ["coming", "soon", "market"],
}

KB_QUERY_PHRASE_HINTS: Dict[str, List[str]] = {
    "confirmation service": ["whatsapp", "order", "confirmation", "pricing"],
    "support number": ["contact", "support", "whatsapp", "agent"],
    "confirmation timing": ["attempt", "times", "screenshot", "proof"],
    "success rate": ["performance", "dispatch", "delivered", "sellers"],
    "active countries": ["market", "coverage", "uae", "saudi", "pakistan", "qatar"],
    # Roman Urdu / English "what services" style → overlap with English KB chunks
    "kya services": ["service", "services", "dropshipping", "fulfillment", "sourcing", "marketing"],
    "kya kya services": ["service", "services", "dropshipping", "fulfillment", "agency", "3pl", "payout"],
    "sari services": ["service", "services", "dropshipping", "fulfillment", "agency", "calculator"],
    "saari services": ["service", "services", "dropshipping", "fulfillment", "agency", "calculator"],
    "services provide": ["service", "offer", "dropshipping", "fulfillment", "sourcing"],
    "services dete": ["service", "offer", "provide", "dropshipping"],
    "services offer": ["service", "dropshipping", "fulfillment", "sourcing"],
    "what services": ["service", "dropshipping", "sourcing", "fulfillment"],
    "which services": ["service", "dropshipping", "sourcing", "fulfillment"],
    "all services": ["service", "services", "dropshipping", "fulfillment", "agency", "3pl"],
    "services list": ["service", "services", "dropshipping", "fulfillment", "sourcing", "marketing"],
    "company services": ["service", "dropshipping", "fulfillment", "sourcing"],
    "services do you": ["service", "offer", "dropshipping", "fulfillment"],
    "list of services": ["service", "dropshipping", "fulfillment", "sourcing"],
}

# Extra stems merged into the query token set when the user is asking for offerings / catalog.
def _chunk_followup_questions(chunk: Any) -> List[str]:
    """Read optional per-chunk follow-ups from ingest metadata (``followup_questions`` etc.)."""
    if not isinstance(chunk, dict):
        return []
    raw = chunk.get("followup_questions")
    if raw is None:
        raw = chunk.get("follow_up_questions") or chunk.get("followups")
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _format_kb_followup_suggestions_block(lines: List[str]) -> str:
    if not lines:
        return "None"
    body = "\n".join(f"- {x}" for x in lines[:12])
    return (
        "Suggested follow-up questions (from retrieved knowledge excerpts — translate to Detected language; "
        "use to shape your **three** bullets when applicable):\n"
        f"{body}"
    )


_SERVICE_QUERY_STEMS: tuple[str, ...] = (
    "dropshipping",
    "sourcing",
    "fulfillment",
    "warehouse",
    "marketing",
    "agency",
    "partnership",
    "invoice",
    "confirmation",
    "whatsapp",
    "profit",
    "store",
    "returns",
    "shipping",
    "dropship",
    "services",
    "service",
    "offering",
    "3pl",
    "bulk",
    "seller",
    "commission",
    "payout",
    "payments",
    "calculator",
    "uae",
    "saudi",
    "pakistan",
)


class ArabiaLangChainBot:
    """
    LangChain-based bot runtime for Arabia support flows.
    Pulls tenant knowledge/schedule/broadcast context from DB and calls OpenAI chat model.
    """

    def __init__(self, db: Session, model_name: Optional[str] = None, temperature: Optional[float] = None):
        self.db = db
        self.model_name = model_name or settings.openai_model
        self.temperature = temperature if temperature is not None else settings.openai_temperature
        self.last_reply_used_kb: bool = False

    def _build_schedule_context(self, tenant_id: int, language: str = "english") -> str:
        sched = (
            self.db.query(TenantSchedule)
            .filter(TenantSchedule.tenant_id == tenant_id)
            .first()
        )
        if not sched:
            return "No configured agent schedule."
        lang = (language or "english").strip().lower()
        return format_tenant_schedule_for_customer(
            lang,
            working_days=sched.working_days,
            start_time=sched.start_time,
            end_time=sched.end_time,
        )

    def _build_active_broadcast_context(self, tenant_id: int) -> str:
        now = datetime.utcnow()
        rows = (
            self.db.query(Broadcast)
            .filter(Broadcast.tenant_id == tenant_id)
            .all()
        )
        active: List[Broadcast] = []
        for b in rows:
            if not getattr(b, "target_ai", True):
                continue
            starts_ok = b.starts_at is None or b.starts_at <= now
            ends_ok = b.ends_at is None or b.ends_at >= now
            if starts_ok and ends_ok:
                active.append(b)
        if not active:
            return "No active broadcast."
        lines = []
        for b in active[:3]:
            lines.append(
                f"- {b.title}: {b.message}"
                + (f" (Occasion: {b.occasion})" if b.occasion else "")
            )
        return "\n".join(lines)

    def _service_catalog_question(self, user_message: str) -> bool:
        """True when the user is asking what services / offerings Arabia provides (not helpline-only)."""
        t = (user_message or "").lower()
        if not re.search(r"\bservices?\b", t):
            return False
        if re.search(
            r"\b(customer|care|technical)\s+service\b",
            t,
        ) and not re.search(
            r"\b(offer|provid|what|which|kya|list|deta|dete|mil|kart|krte|krta|kaun|kon)\b",
            t,
        ):
            return False
        return bool(
            re.search(
                r"\b(what|which|how|tell|list|describe|include|offers?|provid|giving|give|"
                r"kya|kaun|kon|det[ei]|deta|mil|milt|kart[ea]|krte|krty|krta|krti|"
                r"hai|ho|sab|poor|pura|complete|more|aur|kis|all|everything|entire|full|total|"
                r"batao|btao|bataye|batain|bataen|bta)\b",
                t,
            )
            or re.search(r"\b(sari|saari|saare|tamam|poori|puri)\s+services?\b", t)
            or "arabia" in t
        )

    def _merge_service_query_tokens(self, tokens: set[str], user_message: str) -> set[str]:
        out = set(tokens)
        if not self._service_catalog_question(user_message):
            return out
        for stem in _SERVICE_QUERY_STEMS:
            nt = self._normalize_token(stem)
            if len(nt) > 2:
                out.add(nt)
        return out

    def _keyword_fallback_chunk_lines(
        self,
        rows: List[KnowledgeSource],
        user_message: str,
        *,
        max_chunks: int,
    ) -> List[str]:
        """Rank KB chunks by domain keyword density when token overlap alone misses Roman Urdu phrasing."""
        lex = (
            "dropship",
            "sourcing",
            "fulfillment",
            "warehouse",
            "marketing",
            "agency",
            "partnership",
            "invoice",
            "payout",
            "confirmation",
            "whatsapp",
            "profit",
            "store",
            "return",
            "shipping",
            "service",
            "seller",
            "uae",
            "saudi",
            "pakistan",
            "commission",
            "bulk",
            "offer",
        )
        raw_l = (user_message or "").lower()
        ranked: List[tuple[int, str]] = []
        for src in rows:
            metadata = src.knowledge_metadata or {}
            chunk_list = metadata.get("chunks")
            if not isinstance(chunk_list, list):
                continue
            for chunk in chunk_list:
                chunk_text = self._chunk_text_value(chunk)
                if not chunk_text:
                    continue
                low = chunk_text.lower()
                hits = sum(low.count(k) for k in lex)
                if "arabia" in raw_l and "arabia" in low:
                    hits += 2
                if hits <= 0:
                    continue
                cite = self._chunk_citation(chunk)
                ranked.append((hits, f"[{src.name}{cite}] {chunk_text[:700]}"))
        ranked.sort(key=lambda x: x[0], reverse=True)
        lines: List[str] = []
        seen: set[str] = set()
        for _, line in ranked:
            key = line[:160]
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)
            if len(lines) >= max_chunks:
                break
        return lines

    def _build_knowledge_context(
        self,
        tenant_id: int,
        *,
        user_message: str,
        max_items: int = 8,
        max_chunks: int = 8,
        min_score: int = 1,
    ) -> Tuple[str, str]:
        rows = (
            self.db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.tenant_id == tenant_id,
                KnowledgeSource.status == "ready",
            )
            .order_by(KnowledgeSource.updated_at.desc())
            .limit(max_items)
            .all()
        )
        if not rows:
            return "No knowledge sources connected.", "None"

        tokens = self._normalized_query_tokens(user_message)
        tokens = self._merge_service_query_tokens(tokens, user_message)
        scored_entries: List[tuple[int, str, Any]] = []
        items: List[str] = []
        for src in rows:
            metadata = src.knowledge_metadata or {}
            chunk_list = metadata.get("chunks")
            if isinstance(chunk_list, list):
                for chunk in chunk_list:
                    chunk_text = self._chunk_text_value(chunk)
                    if not chunk_text:
                        continue
                    score = self._score_chunk_overlap(tokens, chunk_text)
                    if score < max(min_score, 0) and tokens:
                        continue
                    cite = self._chunk_citation(chunk)
                    scored_entries.append(
                        (score, f"[{src.name}{cite}] {chunk_text[:700]}", chunk),
                    )
            if src.type == "api":
                base_url = src.url or metadata.get("base_url") or "N/A"
                schema_notes = metadata.get("schema_notes") or ""
                items.append(f"- API: {src.name} ({base_url}) {schema_notes}".strip())
            elif src.type == "url":
                items.append(f"- URL: {src.name} ({src.url or 'N/A'})")
            else:
                filename = metadata.get("filename") or src.name
                items.append(f"- FILE: {filename} (chunks: {src.chunk_count})")
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        top_entries = scored_entries[:max_chunks]
        top_chunks = [line for _, line, _ in top_entries]

        if not top_chunks and self._service_catalog_question(user_message):
            top_chunks = self._keyword_fallback_chunk_lines(
                rows, user_message, max_chunks=max_chunks
            )
            merged_followups = dedupe_suggestions(
                heuristic_kb_followups(user_message, top_chunks),
                max_items=10,
            )
        else:
            merged: List[str] = []
            for _, _, ch in top_entries:
                merged.extend(_chunk_followup_questions(ch))
            merged.extend(heuristic_kb_followups(user_message, top_chunks))
            merged_followups = dedupe_suggestions(merged, max_items=10)

        if top_chunks:
            knowledge_str = "\n".join(
                [
                    "Connected knowledge sources:",
                    *items,
                    "",
                    "Most relevant knowledge excerpts:",
                    *[f"- {c}" for c in top_chunks],
                ]
            )
            return knowledge_str, _format_kb_followup_suggestions_block(merged_followups)

        return "\n".join(items), "None"

    def _load_knowledge_rows(self, tenant_id: int, max_items: int = 8) -> List[KnowledgeSource]:
        return (
            self.db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.tenant_id == tenant_id,
                KnowledgeSource.status == "ready",
            )
            .order_by(KnowledgeSource.updated_at.desc())
            .limit(max_items)
            .all()
        )

    def _fetch_text_url(self, url: str, timeout_s: int = 6) -> str:
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ArabiaBot/1.0)",
                    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                },
            )
            with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
                raw = resp.read(200_000).decode("utf-8", errors="ignore")
            # Basic HTML cleanup without extra deps.
            cleaned = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
            cleaned = re.sub(r"(?is)<style.*?>.*?</style>", " ", cleaned)
            cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            return cleaned[:5000]
        except Exception:
            return ""

    def _crawl_configured_urls_context(
        self,
        rows: List[KnowledgeSource],
        user_message: str,
        *,
        min_score: int = 2,
    ) -> str:
        tokens = self._merge_service_query_tokens(
            self._normalized_query_tokens(user_message),
            user_message,
        )
        urls: List[str] = []
        for src in rows:
            metadata = src.knowledge_metadata or {}
            u = (src.url or "").strip()
            if src.type == "url" and u:
                urls.append(u)
            alt = metadata.get("url")
            if isinstance(alt, str) and alt.strip():
                urls.append(alt.strip())
        # Safe defaults for brand-owned pages if KB URLs are sparse.
        urls.extend(
            [
                "https://www.arabiadropship.com/",
                "https://www.arabiadropship.com/services",
                "https://www.arabiadropship.com/faq",
                "https://www.agency.arabiadropship.com/",
            ]
        )
        deduped: List[str] = []
        seen = set()
        for u in urls:
            if u and u not in seen:
                seen.add(u)
                deduped.append(u)

        scored: List[tuple[int, str]] = []
        for u in deduped[:8]:
            txt = self._fetch_text_url(u)
            if not txt:
                continue
            score = self._score_chunk_overlap(tokens, txt)
            if score < min_score:
                continue
            scored.append((score, f"[Crawled {u}] {txt[:700]}"))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [c for _, c in scored[:4]]
        if not top:
            return ""
        return "\n".join(["Website crawl excerpts:", *[f"- {x}" for x in top]])

    def _web_search_context(self, user_message: str) -> str:
        """
        Lightweight web-search fallback (no paid API key):
        DuckDuckGo instant answer endpoint with Arabia context.
        """
        q = f"Arabia Dropshipping {user_message}".strip()
        endpoint = (
            "https://api.duckduckgo.com/?q="
            + quote_plus(q)
            + "&format=json&no_redirect=1&no_html=1"
        )
        try:
            req = Request(endpoint, headers={"User-Agent": "Mozilla/5.0 (compatible; ArabiaBot/1.0)"})
            with urlopen(req, timeout=6) as resp:  # noqa: S310
                payload = json.loads(resp.read(120_000).decode("utf-8", errors="ignore"))
        except Exception:
            return ""

        lines: List[str] = []
        abstract = (payload.get("AbstractText") or "").strip()
        if abstract:
            src = (payload.get("AbstractURL") or "").strip()
            if src:
                lines.append(f"- [Web search {src}] {abstract}")
            else:
                lines.append(f"- [Web search] {abstract}")

        related = payload.get("RelatedTopics")
        if isinstance(related, list):
            for item in related[:5]:
                if not isinstance(item, dict):
                    continue
                text = (item.get("Text") or "").strip()
                first_url = (item.get("FirstURL") or "").strip()
                if text:
                    tag = f"[Web search {first_url}]" if first_url else "[Web search]"
                    lines.append(f"- {tag} {text}")
                if len(lines) >= 4:
                    break
        if not lines:
            return ""
        return "\n".join(["Web search excerpts:", *lines[:4]])

    def _normalize_token(self, token: str) -> str:
        t = re.sub(r"[^a-z0-9]", "", (token or "").lower()).strip()
        if len(t) <= 3:
            return t
        if t.endswith("ies") and len(t) > 4:
            t = t[:-3] + "y"
        # Longer suffixes first so "integration" → "integr" (not "integratio")
        for suffix in ("ation", "tion", "ment", "able", "ible", "ate", "ing", "edly", "ed", "ly", "es", "s"):
            if t.endswith(suffix) and len(t) - len(suffix) >= 3:
                t = t[: -len(suffix)]
                break
        return t

    def _normalized_query_tokens(self, text: str) -> set[str]:
        out: set[str] = set()
        raw = (text or "").lower()
        for tok in raw.split():
            nt = self._normalize_token(tok)
            if len(nt) > 2:
                out.add(nt)
                for synonym in KB_QUERY_SYNONYMS.get(nt, []):
                    ns = self._normalize_token(synonym)
                    if len(ns) > 2:
                        out.add(ns)

        normalized_raw = " ".join(raw.split())
        for phrase, hints in KB_QUERY_PHRASE_HINTS.items():
            if phrase in normalized_raw:
                for hint in hints:
                    nh = self._normalize_token(hint)
                    if len(nh) > 2:
                        out.add(nh)
        return out

    def _score_chunk_overlap(self, tokens: set[str], chunk_text: str) -> int:
        if not tokens:
            return 0
        chunk_tokens = {
            self._normalize_token(tok)
            for tok in re.split(r"\W+", (chunk_text or "").lower())
            if tok
        }
        overlap = sum(1 for t in tokens if t and t in chunk_tokens)
        chunk_l = (chunk_text or "").lower()
        boost = 0
        if "confirmation" in chunk_l and ("whatsapp" in chunk_l or "screenshot" in chunk_l):
            boost += 2
        if "market coverage" in chunk_l or ("active" in chunk_l and "coming soon" in chunk_l):
            boost += 2
        if "98.4% on-time dispatch" in chunk_l or "12k+ sellers" in chunk_l:
            boost += 2
        return overlap + boost

    def _chunk_text_value(self, chunk: Any) -> str:
        if isinstance(chunk, str):
            return chunk
        if isinstance(chunk, dict):
            txt = chunk.get("text")
            if isinstance(txt, str):
                return txt
        return ""

    def _chunk_citation(self, chunk: Any) -> str:
        if not isinstance(chunk, dict):
            return ""
        page = chunk.get("page")
        idx = chunk.get("index")
        parts: List[str] = []
        if isinstance(page, int):
            parts.append(f"p{page}")
        if isinstance(idx, int):
            parts.append(f"c{idx}")
        return f" ({', '.join(parts)})" if parts else ""

    def _build_knowledge_context_embeddings(
        self,
        tenant_id: int,
        *,
        user_message: str,
        max_items: int = 8,
        max_chunks: int = 8,
    ) -> Tuple[str, str]:
        """
        Optional semantic retrieval hook.
        TODO: integrate pgvector/external embeddings; currently falls back to token overlap.
        """
        return self._build_knowledge_context(
            tenant_id,
            user_message=user_message,
            max_items=max_items,
            max_chunks=max_chunks,
            min_score=max(0, int(getattr(settings, "kb_min_score", 1) or 0)),
        )

    def _post_close_handover_line(self, conversation_id: Optional[int]) -> str:
        if not conversation_id:
            return "None"
        row = (
            self.db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if not row:
            return "None"
        return format_post_agent_close_context_for_prompt(row.conversation_metadata)

    def _conversation_history_block(
        self,
        conversation_id: Optional[int],
        *,
        limit: int = 8,
        exclude_message_id: Optional[int] = None,
    ) -> str:
        """
        Load prior turns for the system prompt.

        The **current** inbound user text is passed separately as ``user_message`` in the chat
        template; it is **not** duplicated here under normal operation because WhatsApp and
        ``/ai/chat`` persist the customer ``Message`` only **after** ``generate_reply`` returns.
        Optionally pass ``exclude_message_id`` if a caller ever saves the customer row first.
        """
        if not conversation_id:
            return "No conversation id — thread history not loaded."
        q = self.db.query(Message).filter(Message.conversation_id == conversation_id)
        if exclude_message_id is not None:
            q = q.filter(Message.id != exclude_message_id)
        rows = q.order_by(desc(Message.id)).limit(limit).all()
        rows.reverse()
        if not rows:
            return "No prior messages in this thread."
        lines: List[str] = []
        for m in rows:
            label = (
                "Customer"
                if m.sender_type == "customer"
                else ("Agent" if m.sender_type == "agent" else "Bot")
            )
            body = (m.content or "").strip().replace("\n", " ")
            if len(body) > 600:
                body = body[:597] + "..."
            lines.append(f"{label}: {body}")
        return "\n".join(lines)

    async def generate_reply(
        self,
        *,
        tenant_id: int,
        user_message: str,
        channel: str,
        language: str,
        customer_context: Optional[Dict[str, Any]] = None,
        recent_orders: Optional[List[Dict[str, Any]]] = None,
        fetch_context: Optional[Dict[str, Any]] = None,
        bot_flow: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[int] = None,
        exclude_history_message_id: Optional[int] = None,
        recent_context_hint: Optional[str] = None,
        memory_context: Optional[str] = None,
    ) -> str:
        key = get_openai_api_key()
        if not key:
            raise RuntimeError("OpenAI API key is not configured.")

        llm = ChatOpenAI(
            model_name=self.model_name,
            temperature=self.temperature,
            openai_api_key=key,
        )

        fc = fetch_context
        if fc is None:
            c = customer_context or {}
            fc = {
                "customer": c,
                "recent_orders": recent_orders or [],
                "is_store_customer": bool(c.get("id")),
                "verification_method": "none",
                "store_context_error": None,
                "orders_last_30_days": [],
                "orders_last_90_days": [],
                "orders_last_365_days": [],
                "has_orders": False,
            }
        identity_block = build_customer_identity_summary(fc, bot_flow)
        discovery_block = format_order_discovery_for_llm(fc)
        ro = fc.get("recent_orders") or recent_orders or []
        orders_block = format_orders_summary_for_llm(ro)
        inv_raw = fc.get("invoices")
        inv_list = inv_raw if isinstance(inv_raw, list) else []
        inv_hints = format_order_invoice_match_hints(ro, inv_list)
        if inv_hints:
            orders_block = f"{orders_block}\n\n{inv_hints}".strip()
        cust = fc.get("customer") if isinstance(fc.get("customer"), dict) else None
        invoices_block = format_invoices_summary_for_llm(inv_list, customer=cust)
        history_block = self._conversation_history_block(
            conversation_id,
            exclude_message_id=exclude_history_message_id,
        )
        schedule_context = self._build_schedule_context(tenant_id, language)
        broadcast_context = self._build_active_broadcast_context(tenant_id)
        min_score = max(0, int(getattr(settings, "kb_min_score", 1) or 0))
        rows = self._load_knowledge_rows(tenant_id)
        if bool(getattr(settings, "kb_use_embeddings", False)):
            knowledge_context, kb_followup_suggestions = self._build_knowledge_context_embeddings(
                tenant_id,
                user_message=user_message,
            )
        else:
            knowledge_context, kb_followup_suggestions = self._build_knowledge_context(
                tenant_id,
                user_message=user_message,
                min_score=min_score,
            )
        kb_hit = "Most relevant knowledge excerpts:" in knowledge_context
        self.last_reply_used_kb = kb_hit
        if not kb_hit:
            crawl_min = 1 if self._service_catalog_question(user_message) else 2
            crawl_context = self._crawl_configured_urls_context(
                rows, user_message, min_score=crawl_min
            )
            if crawl_context:
                knowledge_context = f"{knowledge_context}\n\n{crawl_context}".strip()
            else:
                web_context = self._web_search_context(user_message)
                if web_context:
                    knowledge_context = f"{knowledge_context}\n\n{web_context}".strip()

        # Fresh template each turn so LLM_FOLLOWUP_SUGGESTIONS env changes apply without restart.
        hint_line = normalize_context_text(
            recent_context_hint,
            "None",
        )
        memory_line = normalize_context_text(
            memory_context,
            "None (no Redis memory for this scope).",
        )
        agent_availability_context = format_agent_availability_json_for_prompt(
            self.db,
            tenant_id,
            language=language,
            customer_message=user_message,
        )
        post_close_handover_context = normalize_context_text(
            self._post_close_handover_line(conversation_id),
            "None",
        )
        messages = build_prompt().format_messages(
            current_time=now_utc_iso(),
            channel=normalize_context_text(channel, "unknown"),
            language=normalize_context_text(language, "english"),
            recent_context_hint=hint_line,
            memory_context=memory_line,
            customer_context=identity_block,
            order_discovery_context=discovery_block,
            orders_context=orders_block,
            invoices_context=invoices_block,
            schedule_context=schedule_context,
            broadcast_context=broadcast_context,
            agent_availability_context=agent_availability_context,
            post_close_handover_context=post_close_handover_context,
            knowledge_context=knowledge_context,
            kb_followup_suggestions=kb_followup_suggestions,
            conversation_history=history_block,
            user_message=user_message,
        )
        for _attempt in range(2):
            try:
                response = await llm.ainvoke(messages)
                break
            except Exception as exc:
                if _attempt == 0:
                    logger.warning("LangChain OpenAI chat call failed (attempt 1), retrying: %s", exc)
                    import asyncio as _asyncio
                    await _asyncio.sleep(1)
                else:
                    logger.exception("LangChain OpenAI chat call failed (attempt 2)")
                    return llm_unavailable_reply(language)
        else:
            return llm_unavailable_reply(language)
        content = getattr(response, "content", None)
        out = content.strip() if isinstance(content, str) else str(response).strip()
        if out:
            return strip_followup_block_when_disabled(out)
        return knowledge_gap_reply(language)

    async def generate_handoff_unavailable_addon(
        self,
        *,
        tenant_id: int,
        language: str,
        channel: str,
        customer_message: str,
        conversation_id: Optional[int] = None,
        exclude_history_message_id: Optional[int] = None,
        recent_context_hint: Optional[str] = None,
        memory_context: Optional[str] = None,
        customer_context: Optional[Dict[str, Any]] = None,
        bot_flow: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Short reply when routing failed with no_available_agent; appended after the main bot answer.
        """
        key = get_openai_api_key()
        if not key:
            return ""

        fc: Dict[str, Any] = {
            "customer": customer_context or {},
            "recent_orders": [],
            "is_store_customer": bool((customer_context or {}).get("id")),
            "verification_method": "none",
            "store_context_error": None,
            "orders_last_30_days": [],
            "orders_last_90_days": [],
            "orders_last_365_days": [],
            "has_orders": False,
        }
        identity_block = build_customer_identity_summary(fc, bot_flow)
        discovery_block = format_order_discovery_for_llm(fc)
        orders_block = format_orders_summary_for_llm([])
        invoices_block = format_invoices_summary_for_llm([], customer=fc.get("customer") if isinstance(fc.get("customer"), dict) else None)
        history_block = self._conversation_history_block(
            conversation_id,
            exclude_message_id=exclude_history_message_id,
        )
        schedule_context = self._build_schedule_context(tenant_id, language)
        broadcast_context = self._build_active_broadcast_context(tenant_id)
        knowledge_context = "(Not required for this administrative reply.)"
        agent_availability_context = format_agent_availability_json_for_prompt(
            self.db,
            tenant_id,
            language=language,
            customer_message=customer_message,
        )
        post_close_handover_context = normalize_context_text(
            self._post_close_handover_line(conversation_id),
            "None",
        )
        hint_line = normalize_context_text(recent_context_hint, "None")
        memory_line = normalize_context_text(
            memory_context,
            "None (no Redis memory for this scope).",
        )
        user_message = (
            "[HANDOFF_UNAVAILABILITY_REPLY]\n\n"
            "A live human agent was requested but none could be assigned right now.\n\n"
            f"Customer message:\n{customer_message.strip()}"
        )
        llm = ChatOpenAI(
            model_name=self.model_name,
            temperature=self.temperature,
            openai_api_key=key,
        )
        messages = build_prompt(omit_followup_suggestions=True).format_messages(
            current_time=now_utc_iso(),
            channel=normalize_context_text(channel, "unknown"),
            language=normalize_context_text(language, "english"),
            recent_context_hint=hint_line,
            memory_context=memory_line,
            customer_context=identity_block,
            order_discovery_context=discovery_block,
            orders_context=orders_block,
            invoices_context=invoices_block,
            schedule_context=schedule_context,
            broadcast_context=broadcast_context,
            agent_availability_context=agent_availability_context,
            post_close_handover_context=post_close_handover_context,
            knowledge_context=knowledge_context,
            kb_followup_suggestions="None",
            conversation_history=history_block,
            user_message=user_message,
        )
        try:
            response = await llm.ainvoke(messages)
        except Exception:
            logger.exception("Handoff-unavailable LLM call failed")
            return ""
        content = getattr(response, "content", None)
        out = content.strip() if isinstance(content, str) else str(response).strip()
        if not out:
            return ""
        return strip_followup_suggestions_block(out)
