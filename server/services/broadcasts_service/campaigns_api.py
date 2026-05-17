"""
Admin API for customer broadcast campaigns. Uses an APPROVED WhatsAppTemplate and a
recipient source (CSV upload or existing AI-bot customers). Send is dispatched to a
background task; per-recipient progress streams via the admin WebSocket hub.

Endpoints (all admin-only, mounted under ``/api/broadcasts``):

    GET    /campaigns                        — list campaigns for tenant
    GET    /campaigns/{id}                   — single campaign with status
    GET    /campaigns/{id}/recipients        — paginated recipient delivery report
    POST   /campaigns                        — create from JSON (AI_CUSTOMERS source)
    POST   /campaigns/upload-csv             — create from CSV upload (multipart)
    POST   /campaigns/{id}/start             — trigger background send worker
    POST   /campaigns/{id}/cancel            — mark CANCELED (in-flight sends finish)
    DELETE /campaigns/{id}                   — delete DRAFT/COMPLETED/FAILED/CANCELED
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from database import get_db
from models import (
    BroadcastCampaign,
    BroadcastRecipient,
    Conversation,
    Customer,
    User,
    WhatsAppTemplate,
)
from services.auth_service.api import get_current_user
from services.broadcasts_service.send_worker import enqueue_campaign_send

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


VALID_SOURCES = {"CSV", "AI_CUSTOMERS"}
MAX_CSV_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CSV_ROWS = 50_000


class RecipientIn(BaseModel):
    phone: str
    name: Optional[str] = None
    variables: Optional[List[str]] = None


class CampaignCreateIn(BaseModel):
    tenant_id: int
    title: str
    template_id: int
    recipient_source: str  # AI_CUSTOMERS only via this endpoint; CSV uses upload-csv
    scheduled_at: Optional[datetime] = None
    # When AI_CUSTOMERS, body params come from these per-source variables:
    default_variables: Optional[List[str]] = None
    # Optional: only AI customers contacted on/after this date.
    ai_customers_since: Optional[datetime] = None

    @field_validator("recipient_source", mode="before")
    @classmethod
    def upper_src(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().upper()
        return v


class CampaignOut(BaseModel):
    id: int
    tenant_id: int
    title: str
    template_id: int
    template_name: str
    template_language: str
    recipient_source: str
    recipient_count: int
    sent_count: int
    failed_count: int
    status: str
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class RecipientOut(BaseModel):
    id: int
    phone: str
    name: Optional[str] = None
    status: str
    wa_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None


class RecipientPage(BaseModel):
    total: int
    items: List[RecipientOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_admin(current_user: User, tenant_id: int) -> None:
    if (current_user.role or "").lower() != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    if int(current_user.tenant_id or 0) != int(tenant_id or 0):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant mismatch")


def _normalize_phone(raw: str) -> str:
    if not raw:
        return ""
    s = re.sub(r"[\s\-()]", "", raw.strip())
    s = s.lstrip("+")
    return s


def _campaign_to_out(c: BroadcastCampaign, t: WhatsAppTemplate) -> CampaignOut:
    return CampaignOut(
        id=c.id,
        tenant_id=c.tenant_id,
        title=c.title,
        template_id=c.template_id,
        template_name=t.name if t else "",
        template_language=t.language if t else "",
        recipient_source=c.recipient_source,
        recipient_count=int(c.recipient_count or 0),
        sent_count=int(c.sent_count or 0),
        failed_count=int(c.failed_count or 0),
        status=c.status,
        scheduled_at=c.scheduled_at,
        started_at=c.started_at,
        completed_at=c.completed_at,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _approved_template_or_400(db: Session, template_id: int, tenant_id: int) -> WhatsAppTemplate:
    t = (
        db.query(WhatsAppTemplate)
        .filter(
            WhatsAppTemplate.id == template_id,
            WhatsAppTemplate.tenant_id == tenant_id,
        )
        .first()
    )
    if t is None:
        raise HTTPException(404, "Template not found")
    if (t.status or "").upper() != "APPROVED":
        raise HTTPException(
            400,
            f"Template status is '{t.status}'. Only APPROVED templates can be broadcast.",
        )
    return t


def _resolve_ai_customers(
    db: Session,
    tenant_id: int,
    since: Optional[datetime],
) -> List[Dict[str, Any]]:
    """All distinct WhatsApp customers (one row per phone) for this tenant."""
    q = (
        db.query(Customer.id, Customer.phone, Customer.name)
        .join(Conversation, Conversation.customer_id == Customer.id)
        .filter(
            Customer.tenant_id == tenant_id,
            Conversation.channel == "whatsapp",
            Customer.phone.isnot(None),
        )
    )
    if since is not None:
        q = q.filter(Conversation.updated_at >= since)
    seen: Dict[str, Dict[str, Any]] = {}
    for _id, phone, name in q.distinct().all():
        norm = _normalize_phone(phone or "")
        if not norm or norm in seen:
            continue
        seen[norm] = {"phone": norm, "name": name}
    return list(seen.values())


def _create_recipients(
    db: Session,
    campaign_id: int,
    rows: List[Dict[str, Any]],
    default_variables: Optional[List[str]],
    expected_var_count: int,
) -> int:
    """Bulk-insert recipients, deduping on phone within the campaign."""
    inserted = 0
    seen_phones: set[str] = set()
    for row in rows:
        phone = _normalize_phone(str(row.get("phone") or ""))
        if not phone or phone in seen_phones:
            continue
        seen_phones.add(phone)
        name = row.get("name")
        if isinstance(name, str):
            name = name.strip() or None
        else:
            name = None
        per_vars = row.get("variables")
        if not isinstance(per_vars, list):
            per_vars = list(default_variables or [])
        # Fill in {{1}} = name if exactly one placeholder and no explicit vars.
        if expected_var_count == 1 and not per_vars and name:
            per_vars = [name]
        # Pad / truncate to the template's placeholder count.
        if expected_var_count:
            per_vars = (per_vars + [""] * expected_var_count)[:expected_var_count]
        else:
            per_vars = []
        db.add(
            BroadcastRecipient(
                campaign_id=campaign_id,
                phone=phone,
                name=name,
                variables=per_vars,
                status="QUEUED",
            )
        )
        inserted += 1
    db.commit()
    return inserted


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/campaigns", response_model=List[CampaignOut])
async def list_campaigns(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user, tenant_id)
    rows = (
        db.query(BroadcastCampaign)
        .filter(BroadcastCampaign.tenant_id == tenant_id)
        .order_by(BroadcastCampaign.created_at.desc())
        .all()
    )
    out: List[CampaignOut] = []
    for c in rows:
        t = (
            db.query(WhatsAppTemplate)
            .filter(WhatsAppTemplate.id == c.template_id)
            .first()
        )
        out.append(_campaign_to_out(c, t))  # type: ignore[arg-type]
    return out


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id).first()
    if c is None:
        raise HTTPException(404, "Campaign not found")
    _require_admin(current_user, c.tenant_id)
    t = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.id == c.template_id).first()
    return _campaign_to_out(c, t)  # type: ignore[arg-type]


@router.get("/campaigns/{campaign_id}/recipients", response_model=RecipientPage)
async def list_recipients(
    campaign_id: int,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id).first()
    if c is None:
        raise HTTPException(404, "Campaign not found")
    _require_admin(current_user, c.tenant_id)
    limit = max(1, min(500, int(limit or 100)))
    offset = max(0, int(offset or 0))
    q = (
        db.query(BroadcastRecipient)
        .filter(BroadcastRecipient.campaign_id == campaign_id)
        .order_by(BroadcastRecipient.id.asc())
    )
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    items = [
        RecipientOut(
            id=r.id,
            phone=r.phone,
            name=r.name,
            status=r.status,
            wa_message_id=r.wa_message_id,
            error_code=r.error_code,
            error_message=r.error_message,
            sent_at=r.sent_at,
        )
        for r in rows
    ]
    return RecipientPage(total=total, items=items)


@router.post(
    "/campaigns",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign_from_source(
    payload: CampaignCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user, payload.tenant_id)
    if payload.recipient_source not in VALID_SOURCES:
        raise HTTPException(400, f"recipient_source must be one of {sorted(VALID_SOURCES)}")
    if payload.recipient_source == "CSV":
        raise HTTPException(400, "Use POST /campaigns/upload-csv for CSV source")
    t = _approved_template_or_400(db, payload.template_id, payload.tenant_id)

    rows = _resolve_ai_customers(db, payload.tenant_id, payload.ai_customers_since)
    if not rows:
        raise HTTPException(400, "No AI-bot customers match the filter")

    c = BroadcastCampaign(
        tenant_id=payload.tenant_id,
        title=payload.title.strip(),
        template_id=t.id,
        recipient_source="AI_CUSTOMERS",
        recipient_count=0,
        status="DRAFT",
        scheduled_at=payload.scheduled_at,
        created_by_user_id=current_user.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    inserted = _create_recipients(
        db,
        c.id,
        rows,
        payload.default_variables,
        int(t.body_placeholder_count or 0),
    )
    c.recipient_count = inserted
    db.add(c)
    db.commit()
    db.refresh(c)
    return _campaign_to_out(c, t)


@router.post(
    "/campaigns/upload-csv",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign_from_csv(
    tenant_id: int = Form(...),
    title: str = Form(...),
    template_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user, tenant_id)
    t = _approved_template_or_400(db, template_id, tenant_id)
    body = await file.read()
    if not body:
        raise HTTPException(400, "Empty CSV")
    if len(body) > MAX_CSV_BYTES:
        raise HTTPException(400, "CSV exceeds 10 MB limit")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = body.decode("latin-1")
        except Exception:
            raise HTTPException(400, "CSV must be UTF-8 or Latin-1")
    reader = csv.DictReader(io.StringIO(text))
    fields = [f.lower().strip() for f in (reader.fieldnames or [])]
    if "phone" not in fields:
        raise HTTPException(400, "CSV must include a 'phone' column")
    var_cols = sorted(
        [f for f in fields if f.startswith("var") and f[3:].isdigit()],
        key=lambda x: int(x[3:]),
    )
    rows: List[Dict[str, Any]] = []
    for i, raw in enumerate(reader):
        if i >= MAX_CSV_ROWS:
            raise HTTPException(400, f"CSV exceeds {MAX_CSV_ROWS} rows")
        if not raw:
            continue
        norm_row = {(k or "").lower().strip(): v for k, v in raw.items() if k}
        phone = norm_row.get("phone")
        if not phone:
            continue
        variables = [str(norm_row.get(v, "") or "") for v in var_cols] if var_cols else None
        rows.append(
            {
                "phone": phone,
                "name": norm_row.get("name"),
                "variables": variables,
            }
        )
    if not rows:
        raise HTTPException(400, "CSV had no usable rows (need phone column)")

    c = BroadcastCampaign(
        tenant_id=tenant_id,
        title=title.strip(),
        template_id=t.id,
        recipient_source="CSV",
        recipient_count=0,
        status="DRAFT",
        created_by_user_id=current_user.id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    inserted = _create_recipients(
        db,
        c.id,
        rows,
        None,
        int(t.body_placeholder_count or 0),
    )
    c.recipient_count = inserted
    db.add(c)
    db.commit()
    db.refresh(c)
    return _campaign_to_out(c, t)


@router.post("/campaigns/{campaign_id}/start", response_model=CampaignOut)
async def start_campaign(
    campaign_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id).first()
    if c is None:
        raise HTTPException(404, "Campaign not found")
    _require_admin(current_user, c.tenant_id)
    if c.status not in ("DRAFT", "FAILED"):
        raise HTTPException(400, f"Cannot start campaign in status '{c.status}'")
    if int(c.recipient_count or 0) <= 0:
        raise HTTPException(400, "Campaign has no recipients")
    t = _approved_template_or_400(db, c.template_id, c.tenant_id)

    c.status = "QUEUED"
    c.started_at = datetime.utcnow()
    db.add(c)
    db.commit()
    db.refresh(c)
    enqueue_campaign_send(c.id, background)
    return _campaign_to_out(c, t)


@router.post("/campaigns/{campaign_id}/cancel", response_model=CampaignOut)
async def cancel_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id).first()
    if c is None:
        raise HTTPException(404, "Campaign not found")
    _require_admin(current_user, c.tenant_id)
    if c.status in ("COMPLETED", "CANCELED"):
        raise HTTPException(400, f"Campaign is already {c.status}")
    c.status = "CANCELED"
    c.completed_at = datetime.utcnow()
    db.add(c)
    db.commit()
    db.refresh(c)
    t = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.id == c.template_id).first()
    return _campaign_to_out(c, t)  # type: ignore[arg-type]


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.query(BroadcastCampaign).filter(BroadcastCampaign.id == campaign_id).first()
    if c is None:
        raise HTTPException(404, "Campaign not found")
    _require_admin(current_user, c.tenant_id)
    if c.status in ("QUEUED", "SENDING"):
        raise HTTPException(400, "Cancel the campaign first")
    db.query(BroadcastRecipient).filter(BroadcastRecipient.campaign_id == c.id).delete()
    db.delete(c)
    db.commit()
    return None
