"""
Agent online/offline rules during AI-targeted broadcasts (target_ai).

While ``starts_at <= now <= ends_at`` for a broadcast with ``target_ai`` true, agents must not
go online/busy; a background task also forces online agents offline.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from models import Agent, Broadcast
from services.messaging_service.conversation_offline_release import (
    release_live_conversations_when_agent_went_offline,
)
from services.attendance_session_redis import (
    attendance_redis_available,
    delete_attendance_session_redis,
)

logger = logging.getLogger(__name__)

PKT = ZoneInfo("Asia/Karachi")


def utc_now_naive() -> datetime:
    return datetime.utcnow()


def broadcast_covers_now(b: Broadcast, now: datetime) -> bool:
    if not getattr(b, "target_ai", True):
        return False
    if b.starts_at is None or b.ends_at is None:
        return False
    return b.starts_at <= now <= b.ends_at


def active_agent_locking_broadcast(db: Session, tenant_id: int) -> Optional[Broadcast]:
    """First matching broadcast that blocks agents going online, or None."""
    now = utc_now_naive()
    rows = (
        db.query(Broadcast)
        .filter(Broadcast.tenant_id == tenant_id)
        .order_by(Broadcast.starts_at.desc().nullslast())
        .all()
    )
    for b in rows:
        if broadcast_covers_now(b, now):
            return b
    return None


def _close_open_attendance_sessions(db: Session, agent: Agent, now: datetime) -> None:
    from models import AgentAttendanceSession

    open_sessions = (
        db.query(AgentAttendanceSession)
        .filter(
            AgentAttendanceSession.tenant_id == agent.tenant_id,
            AgentAttendanceSession.agent_id == agent.id,
            AgentAttendanceSession.ended_at.is_(None),
        )
        .all()
    )
    for s in open_sessions:
        s.ended_at = now
        db.add(s)


async def enforce_tenant_agents_offline_for_broadcast_async(db: Session, tenant_id: int) -> int:
    """
    Set all online/busy agents for the tenant to offline, close attendance, and return live
    assigned chats to the bot. Returns how many agents were changed.
    """
    now = utc_now_naive()
    agents = (
        db.query(Agent)
        .filter(
            Agent.tenant_id == tenant_id,
            Agent.status.in_(("online", "busy")),
        )
        .all()
    )
    changed = 0
    for agent in agents:
        if attendance_redis_available():
            delete_attendance_session_redis(agent.id)
        _close_open_attendance_sessions(db, agent, now)
        await release_live_conversations_when_agent_went_offline(db, agent)
        agent.status = "offline"
        db.add(agent)
        changed += 1
    if changed:
        logger.info(
            "Broadcast lock: set %s agent(s) offline for tenant_id=%s",
            changed,
            tenant_id,
        )
    return changed


async def run_broadcast_agent_enforcement_tick_async(db: Session) -> None:
    """Periodic job: for every tenant in an AI broadcast window, force agents offline."""
    now = utc_now_naive()
    tenant_ids = (
        db.query(Broadcast.tenant_id)
        .filter(
            Broadcast.target_ai == True,  # noqa: E712
            Broadcast.starts_at.isnot(None),
            Broadcast.ends_at.isnot(None),
            Broadcast.starts_at <= now,
            Broadcast.ends_at >= now,
        )
        .distinct()
        .all()
    )
    for (tid,) in tenant_ids:
        if tid is None:
            continue
        await enforce_tenant_agents_offline_for_broadcast_async(db, int(tid))
    db.commit()


def utc_naive_to_pkt_iso(naive_utc: Optional[datetime]) -> Optional[str]:
    """ISO-8601 string in Asia/Karachi for LLM / API messages."""
    if naive_utc is None:
        return None
    aware = naive_utc.replace(tzinfo=timezone.utc)
    return aware.astimezone(PKT).isoformat(timespec="seconds")
