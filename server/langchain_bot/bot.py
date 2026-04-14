from datetime import datetime
import re
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import get_openai_api_key, settings
from models import Broadcast, KnowledgeSource, Message, TenantSchedule
from langchain_bot.context_format import (
    build_customer_identity_summary,
    format_orders_summary_for_llm,
)
from langchain_bot.prompts import build_prompt, normalize_context_text, now_utc_iso


class ArabiaLangChainBot:
    """
    LangChain-based bot runtime for Arabia support flows.
    Pulls tenant knowledge/schedule/broadcast context from DB and calls OpenAI chat model.
    """

    def __init__(self, db: Session, model_name: Optional[str] = None, temperature: Optional[float] = None):
        self.db = db
        self.model_name = model_name or settings.openai_model
        self.temperature = temperature if temperature is not None else settings.openai_temperature
        self.prompt = build_prompt()

    def _build_schedule_context(self, tenant_id: int) -> str:
        sched = (
            self.db.query(TenantSchedule)
            .filter(TenantSchedule.tenant_id == tenant_id)
            .first()
        )
        if not sched:
            return "No configured agent schedule."
        return (
            f"Working days: {sched.working_days}. "
            f"Agent hours: {sched.start_time} to {sched.end_time}."
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

    def _build_knowledge_context(
        self,
        tenant_id: int,
        *,
        user_message: str,
        max_items: int = 8,
        max_chunks: int = 8,
        min_score: int = 1,
    ) -> str:
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
            return "No knowledge sources connected."

        tokens = self._normalized_query_tokens(user_message)
        scored_chunks: List[tuple[int, str]] = []
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
                    scored_chunks.append((score, f"[{src.name}{cite}] {chunk_text[:700]}"))
            if src.type == "api":
                base_url = src.url or metadata.get("base_url") or "N/A"
                schema_notes = metadata.get("schema_notes") or ""
                items.append(f"- API: {src.name} ({base_url}) {schema_notes}".strip())
            elif src.type == "url":
                items.append(f"- URL: {src.name} ({src.url or 'N/A'})")
            else:
                filename = metadata.get("filename") or src.name
                items.append(f"- FILE: {filename} (chunks: {src.chunk_count})")
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [c for _, c in scored_chunks[:max_chunks]]
        if top_chunks:
            return "\n".join(
                [
                    "Connected knowledge sources:",
                    *items,
                    "",
                    "Most relevant knowledge excerpts:",
                    *[f"- {c}" for c in top_chunks],
                ]
            )
        return "\n".join(items)

    def _normalize_token(self, token: str) -> str:
        t = re.sub(r"[^a-z0-9]", "", (token or "").lower()).strip()
        if len(t) <= 3:
            return t
        if t.endswith("ies") and len(t) > 4:
            t = t[:-3] + "y"
        for suffix in ("ing", "edly", "ed", "ly", "es", "s"):
            if t.endswith(suffix) and len(t) - len(suffix) >= 3:
                t = t[: -len(suffix)]
                break
        return t

    def _normalized_query_tokens(self, text: str) -> set[str]:
        out: set[str] = set()
        for tok in (text or "").lower().split():
            nt = self._normalize_token(tok)
            if len(nt) > 2:
                out.add(nt)
        return out

    def _score_chunk_overlap(self, tokens: set[str], chunk_text: str) -> int:
        if not tokens:
            return 0
        chunk_tokens = {
            self._normalize_token(tok)
            for tok in re.split(r"\W+", (chunk_text or "").lower())
            if tok
        }
        return sum(1 for t in tokens if t and t in chunk_tokens)

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
    ) -> str:
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
            }
        identity_block = build_customer_identity_summary(fc, bot_flow)
        orders_block = format_orders_summary_for_llm(fc.get("recent_orders") or recent_orders or [])
        history_block = self._conversation_history_block(
            conversation_id,
            exclude_message_id=exclude_history_message_id,
        )
        schedule_context = self._build_schedule_context(tenant_id)
        broadcast_context = self._build_active_broadcast_context(tenant_id)
        min_score = max(0, int(getattr(settings, "kb_min_score", 1) or 0))
        if bool(getattr(settings, "kb_use_embeddings", False)):
            knowledge_context = self._build_knowledge_context_embeddings(
                tenant_id,
                user_message=user_message,
            )
        else:
            knowledge_context = self._build_knowledge_context(
                tenant_id,
                user_message=user_message,
                min_score=min_score,
            )

        messages = self.prompt.format_messages(
            current_time=now_utc_iso(),
            channel=normalize_context_text(channel, "unknown"),
            language=normalize_context_text(language, "english"),
            customer_context=identity_block,
            orders_context=orders_block,
            schedule_context=schedule_context,
            broadcast_context=broadcast_context,
            knowledge_context=knowledge_context,
            conversation_history=history_block,
            user_message=user_message,
        )
        response = await llm.ainvoke(messages)
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content.strip()
        return str(response).strip()
