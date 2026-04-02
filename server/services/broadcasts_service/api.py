import asyncio
import logging
import re
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Agent, Broadcast, Conversation, Customer, Notification
from services.whatsapp_service.meta_cloud import MetaWhatsAppClient

logger = logging.getLogger(__name__)

router = APIRouter()


def _normalize_wa_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    s = re.sub(r"[\s\-()]", "", (raw or "").strip())
    if not s:
        return None
    return s


class BroadcastPayload(BaseModel):
    id: int | None = None
    tenant_id: int
    title: str
    message: str
    occasion: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    target_ai: bool = True
    delivery_notify_agents: bool = False
    delivery_notify_customers_whatsapp: bool = False


class BroadcastCreate(BaseModel):
    tenant_id: int
    title: str
    message: str
    occasion: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    target_ai: bool = True
    delivery_notify_agents: bool = False
    delivery_notify_customers_whatsapp: bool = False


@router.get("/broadcasts", response_model=List[BroadcastPayload])
async def list_broadcasts(tenant_id: int, db: Session = Depends(get_db)):
    """
    List all broadcasts for a tenant.
    """
    rows = (
        db.query(Broadcast)
        .filter(Broadcast.tenant_id == tenant_id)
        .order_by(Broadcast.starts_at.desc().nullslast())
        .all()
    )
    return [
        BroadcastPayload(
            id=b.id,
            tenant_id=b.tenant_id,
            title=b.title,
            message=b.message,
            occasion=b.occasion,
            starts_at=b.starts_at,
            ends_at=b.ends_at,
            target_ai=bool(getattr(b, "target_ai", True)),
            delivery_notify_agents=bool(getattr(b, "delivery_notify_agents", False)),
            delivery_notify_customers_whatsapp=bool(
                getattr(b, "delivery_notify_customers_whatsapp", False)
            ),
        )
        for b in rows
    ]


@router.post(
    "/broadcasts",
    response_model=BroadcastPayload,
    status_code=status.HTTP_201_CREATED,
)
async def create_broadcast(
    payload: BroadcastCreate,
    db: Session = Depends(get_db),
):
    """
    Create a broadcast. Optionally notify all tenant agents and/or send one WhatsApp text
    per distinct customer phone that already has a WhatsApp conversation in this system.
    """
    if not (
        payload.target_ai
        or payload.delivery_notify_agents
        or payload.delivery_notify_customers_whatsapp
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one target: AI bot, agents, and/or customers (WhatsApp).",
        )

    b = Broadcast(
        tenant_id=payload.tenant_id,
        title=payload.title,
        message=payload.message,
        occasion=payload.occasion,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        created_at=datetime.utcnow(),
        target_ai=payload.target_ai,
        delivery_notify_agents=payload.delivery_notify_agents,
        delivery_notify_customers_whatsapp=payload.delivery_notify_customers_whatsapp,
    )
    db.add(b)
    db.commit()
    db.refresh(b)

    if payload.delivery_notify_agents:
        agents = (
            db.query(Agent).filter(Agent.tenant_id == payload.tenant_id).all()
        )
        msg_line = (payload.title or "").strip() or "Broadcast"
        desc = (payload.message or "").strip()
        if len(desc) > 4000:
            desc = desc[:3997] + "..."
        for ag in agents:
            db.add(
                Notification(
                    tenant_id=payload.tenant_id,
                    agent_id=ag.id,
                    type="system",
                    message=f"Broadcast: {msg_line}"[:500],
                    description=desc or None,
                    from_agent_id=None,
                    conversation_id=None,
                    read=False,
                )
            )
        db.commit()

    if payload.delivery_notify_customers_whatsapp:
        rows = (
            db.query(Customer.phone)
            .join(Conversation, Conversation.customer_id == Customer.id)
            .filter(
                Customer.tenant_id == payload.tenant_id,
                Conversation.channel == "whatsapp",
                Customer.phone.isnot(None),
            )
            .distinct()
            .all()
        )
        phones: set[str] = set()
        for (phone,) in rows:
            n = _normalize_wa_phone(phone)
            if n:
                phones.add(n)

        client = MetaWhatsAppClient()
        if not client.is_configured():
            logger.warning(
                "Broadcast WhatsApp delivery skipped: Meta Cloud API not configured "
                "(META_WHATSAPP_ACCESS_TOKEN / META_WHATSAPP_PHONE_NUMBER_ID)."
            )
        elif phones:
            wa_body = f"*{payload.title.strip()}*\n\n{payload.message.strip()}"
            if len(wa_body) > 4096:
                wa_body = wa_body[:4093] + "..."
            for to_phone in sorted(phones):
                try:
                    await client.send_text_message(to_phone=to_phone, text=wa_body)
                except Exception:
                    logger.exception(
                        "WhatsApp broadcast send failed to=%s", to_phone[-8:]
                    )
                await asyncio.sleep(0.12)

    return BroadcastPayload(
        id=b.id,
        tenant_id=b.tenant_id,
        title=b.title,
        message=b.message,
        occasion=b.occasion,
        starts_at=b.starts_at,
        ends_at=b.ends_at,
        target_ai=bool(b.target_ai),
        delivery_notify_agents=bool(b.delivery_notify_agents),
        delivery_notify_customers_whatsapp=bool(b.delivery_notify_customers_whatsapp),
    )


@router.delete("/broadcasts/{broadcast_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_broadcast(broadcast_id: int, db: Session = Depends(get_db)):
    """
    Delete a broadcast.
    """
    row = db.query(Broadcast).filter(Broadcast.id == broadcast_id).first()
    if not row:
        return
    db.delete(row)
    db.commit()
    return
