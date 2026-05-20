"""
Safety net: release chats that have been assigned to an agent for a long time
without an agent reply. Without this, a permanently-disappeared agent could
hold customer conversations hostage now that we no longer auto-release on
WebSocket disconnect.

A conversation is "stale" when:
- It is assigned (``agent_id IS NOT NULL``)
- It is not closed/resolved
- Its most recent inbound customer message is older than the configured
  threshold AND there has been no agent-sent message since that customer
  message.

When stale, reuse :func:`release_live_conversations_when_agent_went_offline`
so the customer-visible handover text and bot-resume logic are identical to
the manual path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Agent, Conversation, Message
from services.messaging_service.conversation_offline_release import (
    release_live_conversations_when_agent_went_offline,
)

logger = logging.getLogger(__name__)


async def release_stale_assigned_conversations(
    db: Session,
    *,
    stale_hours: int,
) -> int:
    """
    Find conversations assigned to an agent where the last customer message is
    older than ``stale_hours`` and no agent reply has happened since, then
    release them back to the bot. Returns the number of conversations released.
    """
    if stale_hours <= 0:
        return 0
    cutoff = datetime.utcnow() - timedelta(hours=stale_hours)
    candidate_convs: List[Conversation] = (
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

    # Group conversations by agent, double-check staleness per conversation,
    # then call the existing release helper per agent.
    by_agent: dict[int, List[Conversation]] = {}
    for c in candidate_convs:
        last_customer = (
            db.query(Message)
            .filter(
                Message.conversation_id == c.id,
                Message.sender_type == "customer",
            )
            .order_by(Message.created_at.desc())
            .first()
        )
        if last_customer is None or last_customer.created_at >= cutoff:
            continue
        last_agent = (
            db.query(Message)
            .filter(
                Message.conversation_id == c.id,
                Message.sender_type == "agent",
                Message.created_at > last_customer.created_at,
            )
            .first()
        )
        if last_agent is not None:
            continue
        by_agent.setdefault(int(c.agent_id), []).append(c)

    released = 0
    for agent_id, _convs in by_agent.items():
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if agent is None:
            continue
        try:
            released += await release_live_conversations_when_agent_went_offline(db, agent)
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
