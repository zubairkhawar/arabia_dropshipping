"""
Safety net: release chats that have been assigned to an agent with no
conversation activity for ``agent_chat_stale_release_hours`` (default 24h).

Without this, a permanently-disappeared agent could hold customer conversations
hostage now that we no longer auto-release on WebSocket disconnect or on manual
offline. Activity = any message in the conversation; we use
``Conversation.updated_at``, which is touched on every message write.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Agent, Conversation
from services.messaging_service.conversation_offline_release import (
    IDLE_HANDOVER_TEXT,
    release_live_conversations_when_agent_went_offline,
)

logger = logging.getLogger(__name__)


async def release_stale_assigned_conversations(
    db: Session,
    *,
    stale_hours: int,
) -> int:
    """
    Release every assigned, non-closed conversation whose ``updated_at`` is older
    than ``stale_hours``. Returns the number of conversations released.
    """
    if stale_hours <= 0:
        return 0
    cutoff = datetime.utcnow() - timedelta(hours=stale_hours)
    candidate_convs = (
        db.query(Conversation)
        .filter(
            Conversation.agent_id.isnot(None),
            func.lower(func.coalesce(Conversation.status, "")).notin_(
                ["closed", "resolved"]
            ),
            Conversation.updated_at < cutoff,
        )
        .all()
    )
    if not candidate_convs:
        return 0

    by_agent: dict[int, list[Conversation]] = {}
    for c in candidate_convs:
        by_agent.setdefault(int(c.agent_id), []).append(c)

    released = 0
    for agent_id in by_agent:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if agent is None:
            continue
        try:
            released += await release_live_conversations_when_agent_went_offline(
                db, agent, handover_text=IDLE_HANDOVER_TEXT
            )
        except Exception:
            logger.exception(
                "stale chat release failed for agent_id=%s", agent_id
            )
    return released


async def run_stale_chat_release_tick() -> int:
    """Single tick: open a session, run the sweep, close. Returns rows released."""
    from config import settings

    hours = int(getattr(settings, "agent_chat_stale_release_hours", 0) or 0)
    if hours <= 0:
        return 0
    db = SessionLocal()
    try:
        return await release_stale_assigned_conversations(db, stale_hours=hours)
    finally:
        db.close()
