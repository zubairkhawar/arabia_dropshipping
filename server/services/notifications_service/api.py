from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Notification, Agent, User
from services.auth_service.api import get_current_user


router = APIRouter()


class NotificationOut(BaseModel):
    id: int
    type: str
    message: str
    description: str | None
    from_agent_id: int | None
    conversation_id: int | None
    created_at: str
    read: bool

    class Config:
        from_attributes = True


@router.get("", response_model=List[NotificationOut])
async def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List notifications for the current agent.
    """
    agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    rows = (
        db.query(Notification)
        .filter(
            Notification.tenant_id == current_user.tenant_id,
            Notification.agent_id == agent.id,
        )
        .order_by(Notification.created_at.desc())
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


@router.post("/read-all")
async def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark all notifications for current agent as read.
    """
    agent = db.query(Agent).filter(Agent.user_id == current_user.id).first()
    if not agent:
        return {"updated": 0}

    updated = (
        db.query(Notification)
        .filter(
            Notification.tenant_id == current_user.tenant_id,
            Notification.agent_id == agent.id,
            Notification.read.is_(False),
        )
        .update({Notification.read: True})
    )
    db.commit()
    return {"updated": updated}

