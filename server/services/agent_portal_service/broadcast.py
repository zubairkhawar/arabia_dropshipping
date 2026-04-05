"""Async push to agent portal WebSocket clients."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models import TeamMembership
from services.agent_portal_service.hub import hub
from services.agent_portal_service.unread_compute import build_unread_summary_dict


async def push_unread_summary(db: Session, tenant_id: int, agent_id: int) -> None:
    data = build_unread_summary_dict(db, tenant_id, agent_id)
    await hub.broadcast_json(tenant_id, agent_id, {"type": "unread_summary", **data})


async def push_inbox_message(
    db: Session,
    tenant_id: int,
    agent_id: int,
    conversation_id: int,
    message: Dict[str, Any],
) -> None:
    summary = build_unread_summary_dict(db, tenant_id, agent_id)
    await hub.broadcast_json(
        tenant_id,
        agent_id,
        {
            "type": "inbox_message",
            "conversation_id": conversation_id,
            "message": message,
            **summary,
        },
    )


async def push_notification_event(
    tenant_id: int, agent_id: int, notification: Dict[str, Any], unread_summary: Optional[Dict[str, int]] = None
) -> None:
    payload: Dict[str, Any] = {
        "type": "notification",
        "notification": notification,
    }
    if unread_summary is not None:
        payload.update(unread_summary)
    await hub.broadcast_json(tenant_id, agent_id, payload)


async def push_refresh_unread(db: Session, tenant_id: int, agent_id: int) -> None:
    data = build_unread_summary_dict(db, tenant_id, agent_id)
    await hub.broadcast_json(tenant_id, agent_id, {"type": "unread_summary", **data})


async def notify_team_members_unread(db: Session, tenant_id: int, team_id: int) -> None:
    rows = (
        db.query(TeamMembership)
        .filter(TeamMembership.tenant_id == tenant_id, TeamMembership.team_id == team_id)
        .all()
    )
    for m in rows:
        await push_refresh_unread(db, tenant_id, m.agent_id)
