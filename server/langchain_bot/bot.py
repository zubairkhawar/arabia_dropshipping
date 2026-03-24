from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from config import get_openai_api_key, settings
from models import Broadcast, KnowledgeSource, TenantSchedule
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

    def _build_knowledge_context(self, tenant_id: int, max_items: int = 8) -> str:
        rows = (
            self.db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.tenant_id == tenant_id,
                KnowledgeSource.status.in_(["ready", "indexing"]),
            )
            .order_by(KnowledgeSource.updated_at.desc())
            .limit(max_items)
            .all()
        )
        if not rows:
            return "No knowledge sources connected."

        items: List[str] = []
        for src in rows:
            metadata = src.knowledge_metadata or {}
            if src.type == "api":
                base_url = src.url or metadata.get("base_url") or "N/A"
                schema_notes = metadata.get("schema_notes") or ""
                items.append(f"- API: {src.name} ({base_url}) {schema_notes}".strip())
            elif src.type == "url":
                items.append(f"- URL: {src.name} ({src.url or 'N/A'})")
            else:
                filename = metadata.get("filename") or src.name
                items.append(f"- FILE: {filename} (chunks: {src.chunk_count})")
        return "\n".join(items)

    async def generate_reply(
        self,
        *,
        tenant_id: int,
        user_message: str,
        channel: str,
        language: str,
        customer_context: Optional[Dict[str, Any]] = None,
        recent_orders: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        key = get_openai_api_key()
        if not key:
            raise RuntimeError("OpenAI API key is not configured.")

        llm = ChatOpenAI(
            model_name=self.model_name,
            temperature=self.temperature,
            openai_api_key=key,
        )

        customer_context_text = normalize_context_text(
            str(customer_context or {}), fallback="No customer context."
        )
        orders_context_text = normalize_context_text(
            str(recent_orders or []), fallback="No order context."
        )
        schedule_context = self._build_schedule_context(tenant_id)
        broadcast_context = self._build_active_broadcast_context(tenant_id)
        knowledge_context = self._build_knowledge_context(tenant_id)

        messages = self.prompt.format_messages(
            current_time=now_utc_iso(),
            channel=normalize_context_text(channel, "unknown"),
            language=normalize_context_text(language, "english"),
            customer_context=customer_context_text,
            orders_context=orders_context_text,
            schedule_context=schedule_context,
            broadcast_context=broadcast_context,
            knowledge_context=knowledge_context,
            user_message=user_message,
        )
        response = await llm.ainvoke(messages)
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content.strip()
        return str(response).strip()
