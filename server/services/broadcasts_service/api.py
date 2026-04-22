import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Agent, Broadcast, Conversation, Customer, Notification
from services.broadcasts_service.whatsapp_delivery import (
    count_named_body_placeholders,
    customer_in_whatsapp_session_window,
    expand_whatsapp_template_tokens,
)
from services.broadcasts_service.broadcast_agent_lock import (
    broadcast_covers_now,
    enforce_tenant_agents_offline_for_broadcast_async,
)
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
    whatsapp_template_name: Optional[str] = None
    whatsapp_template_language: Optional[str] = None
    whatsapp_template_body_parameters: Optional[List[str]] = None


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
    whatsapp_template_name: Optional[str] = None
    whatsapp_template_language: Optional[str] = None
    whatsapp_template_body_parameters: Optional[List[str]] = None

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

    @field_validator("whatsapp_template_name", "whatsapp_template_language", mode="before")
    @classmethod
    def whatsapp_blank_strings(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("whatsapp_template_body_parameters", mode="before")
    @classmethod
    def whatsapp_body_params(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, list):
            return ["" if x is None else str(x) for x in v]
        return v

    @model_validator(mode="after")
    def clear_whatsapp_template_if_no_name(self):
        if not (self.whatsapp_template_name or "").strip():
            object.__setattr__(self, "whatsapp_template_name", None)
            object.__setattr__(self, "whatsapp_template_language", None)
            object.__setattr__(self, "whatsapp_template_body_parameters", None)
        return self

    @model_validator(mode="after")
    def broadcast_datetimes_to_naive_utc(self):
        for field in ("starts_at", "ends_at"):
            dt = getattr(self, field, None)
            if dt is None:
                continue
            if dt.tzinfo is not None:
                object.__setattr__(
                    self,
                    field,
                    dt.astimezone(timezone.utc).replace(tzinfo=None),
                )
        return self


class BroadcastUpdate(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    occasion: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    target_ai: Optional[bool] = None
    delivery_notify_agents: Optional[bool] = None
    delivery_notify_customers_whatsapp: Optional[bool] = None
    whatsapp_template_name: Optional[str] = None
    whatsapp_template_language: Optional[str] = None
    whatsapp_template_body_parameters: Optional[List[str]] = None

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

    @field_validator("whatsapp_template_name", "whatsapp_template_language", mode="before")
    @classmethod
    def whatsapp_blank_strings(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("whatsapp_template_body_parameters", mode="before")
    @classmethod
    def whatsapp_body_params(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, list):
            return ["" if x is None else str(x) for x in v]
        return v

    @model_validator(mode="after")
    def broadcast_datetimes_to_naive_utc(self):
        for field in ("starts_at", "ends_at"):
            dt = getattr(self, field, None)
            if dt is None:
                continue
            if dt.tzinfo is not None:
                object.__setattr__(
                    self,
                    field,
                    dt.astimezone(timezone.utc).replace(tzinfo=None),
                )
        return self


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


class WhatsAppTemplateOut(BaseModel):
    name: str
    language: str
    status: Optional[str] = None
    category: Optional[str] = None
    body_placeholder_count: int = 0


def _meta_template_row_language(row: dict) -> str:
    lang = row.get("language")
    if isinstance(lang, str) and lang.strip():
        return lang.strip()
    if isinstance(lang, dict):
        c = lang.get("code") or lang.get("locale")
        if isinstance(c, str) and c.strip():
            return c.strip()
    return ""


def _stored_whatsapp_body_params(b: Any) -> Optional[List[str]]:
    raw = getattr(b, "whatsapp_template_body_parameters", None)
    if raw is None:
        return None
    if isinstance(raw, list):
        return ["" if x is None else str(x) for x in raw]
    return None


def broadcast_payload_from_model(b: Broadcast) -> BroadcastPayload:
    return BroadcastPayload(
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
        whatsapp_template_name=getattr(b, "whatsapp_template_name", None),
        whatsapp_template_language=getattr(b, "whatsapp_template_language", None),
        whatsapp_template_body_parameters=_stored_whatsapp_body_params(b),
    )


@router.get("/broadcasts/whatsapp-templates", response_model=List[WhatsAppTemplateOut])
async def list_whatsapp_broadcast_templates():
    """Approved WhatsApp message templates from Meta (WABA) for customer broadcasts."""
    client = MetaWhatsAppClient()
    if not client.waba_templates_configured():
        return []
    raw = await client.list_message_templates()
    out: List[WhatsAppTemplateOut] = []
    for row in raw:
        st = str(row.get("status") or "").upper()
        if st and st != "APPROVED":
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        lang = _meta_template_row_language(row)
        if not lang:
            lang = "en_US"
        out.append(
            WhatsAppTemplateOut(
                name=name,
                language=lang,
                status=row.get("status") if isinstance(row.get("status"), str) else None,
                category=row.get("category") if isinstance(row.get("category"), str) else None,
                body_placeholder_count=count_named_body_placeholders(row.get("components")),
            )
        )
    out.sort(key=lambda x: (x.name.lower(), x.language.lower()))
    return out


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
    return [broadcast_payload_from_model(b) for b in rows]


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

    if payload.target_ai and not (payload.message or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent availability message is required when AI bot is selected.",
        )

    eff_message = (payload.message or "").strip()
    if not eff_message:
        eff_message = (payload.title or "").strip() or "."

    tpl_lang = (payload.whatsapp_template_language or "").strip() or None
    if (payload.whatsapp_template_name or "").strip() and not tpl_lang:
        tpl_lang = "en_US"

    b = Broadcast(
        tenant_id=payload.tenant_id,
        title=payload.title,
        message=eff_message,
        occasion=payload.occasion,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        created_at=datetime.utcnow(),
        target_ai=payload.target_ai,
        delivery_notify_agents=payload.delivery_notify_agents,
        delivery_notify_customers_whatsapp=payload.delivery_notify_customers_whatsapp,
        whatsapp_template_name=payload.whatsapp_template_name,
        whatsapp_template_language=tpl_lang,
        whatsapp_template_body_parameters=payload.whatsapp_template_body_parameters,
    )
    db.add(b)
    db.commit()
    db.refresh(b)

    if payload.target_ai and broadcast_covers_now(b, datetime.utcnow()):
        if await enforce_tenant_agents_offline_for_broadcast_async(db, payload.tenant_id):
            db.commit()
            db.refresh(b)

    if payload.delivery_notify_agents:
        agents = (
            db.query(Agent).filter(Agent.tenant_id == payload.tenant_id).all()
        )
        msg_line = (payload.title or "").strip() or "Broadcast"
        desc = eff_message
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
        grouped = (
            db.query(
                Customer.id,
                Customer.phone,
                func.max(Conversation.id).label("conv_id"),
            )
            .join(Conversation, Conversation.customer_id == Customer.id)
            .filter(
                Customer.tenant_id == payload.tenant_id,
                Conversation.channel == "whatsapp",
                Customer.phone.isnot(None),
            )
            .group_by(Customer.id, Customer.phone)
            .all()
        )

        client = MetaWhatsAppClient()
        tpl_name = (payload.whatsapp_template_name or "").strip() or None
        tpl_lang_send = tpl_lang or "en_US"
        tpl_params = list(payload.whatsapp_template_body_parameters or [])

        if not client.is_configured():
            logger.warning(
                "Broadcast WhatsApp delivery skipped: Meta Cloud API not configured "
                "(META_WHATSAPP_ACCESS_TOKEN / META_WHATSAPP_PHONE_NUMBER_ID)."
            )
        elif grouped:
            wa_body = f"*{payload.title.strip()}*\n\n{eff_message}"
            if len(wa_body) > 4096:
                wa_body = wa_body[:4093] + "..."
            for customer_id, phone_raw, conv_id in grouped:
                to_phone = _normalize_wa_phone(phone_raw)
                if not to_phone or conv_id is None:
                    continue
                cust = db.query(Customer).filter(Customer.id == customer_id).first()
                if not cust:
                    continue
                in_win = customer_in_whatsapp_session_window(db, int(conv_id))
                try:
                    if in_win or not tpl_name:
                        await client.send_text_message(to_phone=to_phone, text=wa_body)
                    else:
                        expanded = expand_whatsapp_template_tokens(
                            db, payload.tenant_id, cust, tpl_params
                        )
                        await client.send_template_message(
                            to_phone=to_phone,
                            template_name=tpl_name,
                            language_code=tpl_lang_send,
                            body_parameters=expanded,
                        )
                except Exception:
                    logger.exception(
                        "WhatsApp broadcast send failed to=%s", to_phone[-8:]
                    )
                await asyncio.sleep(0.12)

    return broadcast_payload_from_model(b)


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
    merged_target_ai = data["target_ai"] if "target_ai" in data else bool(row.target_ai)
    merged_message = (data["message"] if "message" in data else (row.message or "")) or ""
    if merged_target_ai and not merged_message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent availability message is required when AI bot is selected.",
        )

    for key, val in data.items():
        setattr(row, key, val)

    if getattr(row, "whatsapp_template_name", None) in (None, ""):
        row.whatsapp_template_name = None
        row.whatsapp_template_language = None
        row.whatsapp_template_body_parameters = None
    elif getattr(row, "whatsapp_template_name", None) and not (
        getattr(row, "whatsapp_template_language", None) or ""
    ).strip():
        row.whatsapp_template_language = "en_US"

    db.add(row)
    db.commit()
    db.refresh(row)

    if bool(getattr(row, "target_ai", True)) and broadcast_covers_now(row, datetime.utcnow()):
        if await enforce_tenant_agents_offline_for_broadcast_async(db, int(row.tenant_id)):
            db.commit()
            db.refresh(row)

    return broadcast_payload_from_model(row)


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
