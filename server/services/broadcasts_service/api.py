import asyncio
import logging
import re
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
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


def _coerce_broadcast_datetime(v: Any) -> Any:
    """
    Accept HTML ``datetime-local`` (no seconds), empty strings, and ISO strings for JSON bodies.
    """
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # "YYYY-MM-DDTHH:mm" from <input type="datetime-local" /> — add seconds for strict parsers
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", s):
            return f"{s}:00"
        return s
    return v


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

    @field_validator("tenant_id", mode="before")
    @classmethod
    def coerce_tenant_id(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
        return v

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def coerce_datetimes(cls, v: Any) -> Any:
        return _coerce_broadcast_datetime(v)

    @field_validator("occasion", mode="before")
    @classmethod
    def occasion_blank(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v


class BroadcastUpdate(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    occasion: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    target_ai: Optional[bool] = None
    delivery_notify_agents: Optional[bool] = None
    delivery_notify_customers_whatsapp: Optional[bool] = None

    @field_validator("starts_at", "ends_at", mode="before")
    @classmethod
    def coerce_datetimes(cls, v: Any) -> Any:
        return _coerce_broadcast_datetime(v)

    @field_validator("occasion", mode="before")
    @classmethod
    def occasion_blank(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v


class WhatsAppRecipientCountOut(BaseModel):
    count: int


@router.get("/broadcasts/whatsapp-recipient-count", response_model=WhatsAppRecipientCountOut)
async def whatsapp_recipient_count(tenant_id: int, db: Session = Depends(get_db)):
    """
    Distinct customer phones with an existing WhatsApp conversation for this tenant
    (same pool used when sending a broadcast to customers).
    """
    rows = (
        db.query(Customer.phone)
        .join(Conversation, Conversation.customer_id == Customer.id)
        .filter(
            Customer.tenant_id == tenant_id,
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
    return WhatsAppRecipientCountOut(count=len(phones))


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
        pending_notifs: List[Notification] = []
        for ag in agents:
            n = Notification(
                tenant_id=payload.tenant_id,
                agent_id=ag.id,
                type="broadcast",
                message=f"Broadcast: {msg_line}"[:500],
                description=desc or None,
                from_agent_id=None,
                conversation_id=None,
                read=False,
            )
            db.add(n)
            pending_notifs.append(n)
        db.commit()
        from services.agent_portal_service.broadcast import push_notification_event
        from services.agent_portal_service.unread_compute import build_unread_summary_dict

        for n in pending_notifs:
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
            summary = build_unread_summary_dict(db, payload.tenant_id, n.agent_id)
            await push_notification_event(payload.tenant_id, n.agent_id, notif_dict, summary)

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


@router.patch("/broadcasts/{broadcast_id}", response_model=BroadcastPayload)
async def update_broadcast(
    broadcast_id: int,
    payload: BroadcastUpdate,
    db: Session = Depends(get_db),
):
    """
    Update an existing broadcast (does not re-send agent notifications or WhatsApp).
    """
    row = db.query(Broadcast).filter(Broadcast.id == broadcast_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broadcast not found")

    data = payload.model_dump(exclude_unset=True)
    for key, val in data.items():
        setattr(row, key, val)

    db.add(row)
    db.commit()
    db.refresh(row)

    return BroadcastPayload(
        id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        message=row.message,
        occasion=row.occasion,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        target_ai=bool(row.target_ai),
        delivery_notify_agents=bool(row.delivery_notify_agents),
        delivery_notify_customers_whatsapp=bool(row.delivery_notify_customers_whatsapp),
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
