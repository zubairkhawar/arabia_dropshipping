from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Notification


router = APIRouter()


class NotificationOut(BaseModel):
    id: int
    type: str
    message: str
    description: str | None
    from_agent_id: int | None
    conversation_id: int | None
    created_at: datetime
    read: bool

    class Config:
        from_attributes = True


class NotificationCreate(BaseModel):
    tenant_id: int
    agent_id: int
    type: str
    message: str
    description: str | None = None
    from_agent_id: int | None = None
    conversation_id: int | None = None


@router.get("", response_model=List[NotificationOut])
async def list_notifications(
    tenant_id: int,
    agent_id: int,
    db: Session = Depends(get_db),
):
    """
    List notifications for the current agent (last 7 days, max 50).
    """
    cutoff = datetime.utcnow() - timedelta(days=7)
    rows = (
        db.query(Notification)
        .filter(
            Notification.tenant_id == tenant_id,
            Notification.agent_id == agent_id,
            Notification.created_at >= cutoff,
        )
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return rows


@router.patch("/{notification_id}", response_model=NotificationOut)
async def mark_notification_read(notification_id: int, db: Session = Depends(get_db)):
    """
    Mark a single notification as read.
    """
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.read = True
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


@router.post("", response_model=NotificationOut)
async def create_notification(payload: NotificationCreate, db: Session = Depends(get_db)):
    notif = Notification(
        tenant_id=payload.tenant_id,
        agent_id=payload.agent_id,
        type=payload.type,
        message=payload.message,
        description=payload.description,
        from_agent_id=payload.from_agent_id,
        conversation_id=payload.conversation_id,
        read=False,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    from services.agent_portal_service.broadcast import push_notification_event
    from services.agent_portal_service.unread_compute import build_unread_summary_dict

    notif_dict = {
        "id": notif.id,
        "type": notif.type,
        "message": notif.message,
        "description": notif.description,
        "from_agent_id": notif.from_agent_id,
        "conversation_id": notif.conversation_id,
        "created_at": notif.created_at,
        "read": notif.read,
    }
    summary = build_unread_summary_dict(db, payload.tenant_id, payload.agent_id)
    await push_notification_event(payload.tenant_id, payload.agent_id, notif_dict, summary)
    return notif


@router.post("/read-all")
async def mark_all_read(
    tenant_id: int,
    agent_id: int,
    db: Session = Depends(get_db),
):
    """
    Mark all notifications for current agent as read.
    """
    updated = (
        db.query(Notification)
        .filter(
            Notification.tenant_id == tenant_id,
            Notification.agent_id == agent_id,
            Notification.read.is_(False),
        )
        .update({Notification.read: True})
    )
    db.commit()
    return {"updated": updated}

