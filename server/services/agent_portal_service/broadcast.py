"""Async push to agent portal WebSocket clients."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from models import Customer, Notification, TeamMembership
from services.agent_portal_service.hub import hub
from services.agent_portal_service.unread_compute import build_unread_summary_dict


async def push_unread_summary(db: Session, tenant_id: int, agent_id: int) -> None:
    data = build_unread_summary_dict(db, tenant_id, agent_id)
    await hub.broadcast_json(tenant_id, agent_id, {"type": "unread_summary", **data})


async def push_inbox_sync_event(
    db: Session, tenant_id: int, agent_id: int, payload: Dict[str, Any]
) -> None:
    """Generic inbox-related event (edit, delete, etc.) with unread summary."""
    data = build_unread_summary_dict(db, tenant_id, agent_id)
    await hub.broadcast_json(tenant_id, agent_id, {**payload, **data})


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


async def notify_bot_handoff_assigned(
    db: Session,
    tenant_id: int,
    agent_id: int,
    conversation_id: int,
    customer_id: int,
    store_id: int,
) -> None:
    """
    Persist and push when a conversation is first assigned to an agent after bot handoff.
    """
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        .first()
    )
    cust_label = "Customer"
    if customer:
        name = (customer.name or "").strip()
        phone = (customer.phone or "").strip()
        if name and phone:
            cust_label = f"{name} ({phone})"
        elif name or phone:
            cust_label = name or phone
    n = Notification(
        tenant_id=tenant_id,
        agent_id=agent_id,
        type="bot_new_chat",
        message="You have a new chat from WhatsApp",
        description=f"Customer: {cust_label}",
        from_agent_id=None,
        conversation_id=conversation_id,
        read=False,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    notif_dict = {
        "id": n.id,
        "type": n.type,
        "message": n.message,
        "description": n.description,
        "from_agent_id": n.from_agent_id,
        "conversation_id": n.conversation_id,
        "created_at": n.created_at,
        "read": n.read,
    }
    summary = build_unread_summary_dict(db, tenant_id, agent_id)
    await push_notification_event(tenant_id, agent_id, notif_dict, summary)


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
