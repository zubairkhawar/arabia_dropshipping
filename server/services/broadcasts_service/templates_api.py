"""
Admin API for WhatsApp message templates (Flow A — template approval lifecycle).

Endpoints (all admin-only, mounted under ``/api/broadcasts``):

    GET    /whatsapp-message-templates                 — list local templates for tenant
    POST   /whatsapp-message-templates                 — create local DRAFT
    POST   /whatsapp-message-templates/{id}/submit     — submit DRAFT to Meta (→ PENDING)
    GET    /whatsapp-message-templates/{id}            — single template
    DELETE /whatsapp-message-templates/{id}            — delete local + Meta (if submitted)
    POST   /whatsapp-message-templates/{id}/resync     — reconcile status from Meta on demand
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from database import get_db
from models import User, WhatsAppTemplate
from services.admin_realtime_service.hub import admin_hub
from services.auth_service.api import get_current_user
from services.whatsapp_service.meta_cloud import MetaWhatsAppClient

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


VALID_CATEGORIES = {"MARKETING", "UTILITY", "AUTHENTICATION"}
VALID_HEADER_FORMATS = {"TEXT", "IMAGE", "VIDEO", "DOCUMENT"}
TEMPLATE_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,512}$")


class TemplateComponent(BaseModel):
    """
    Mirrors Meta's component shape. ``type`` is one of HEADER, BODY, FOOTER, BUTTONS.
    Stored verbatim in the DB and forwarded to Meta on submit.
    """

    type: str
    format: Optional[str] = None  # for HEADER: TEXT|IMAGE|VIDEO|DOCUMENT
    text: Optional[str] = None
    example: Optional[Dict[str, Any]] = None
    buttons: Optional[List[Dict[str, Any]]] = None

    @field_validator("type", mode="before")
    @classmethod
    def upper_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator("format", mode="before")
    @classmethod
    def upper_format(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
        return v


class TemplateCreateIn(BaseModel):
    tenant_id: int
    name: str
    language: str
    category: str
    components: List[TemplateComponent]

    @field_validator("name", mode="before")
    @classmethod
    def slug_name(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        return v.strip().lower()

    @field_validator("category", mode="before")
    @classmethod
    def upper_category(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator("language", mode="before")
    @classmethod
    def trim_language(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v


class TemplateOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    language: str
    category: str
    components: List[Dict[str, Any]]
    body_placeholder_count: int
    status: str
    rejection_reason: Optional[str] = None
    meta_template_id: Optional[str] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_body_placeholders(components: List[Dict[str, Any]]) -> int:
    for c in components:
        if (c.get("type") or "").upper() == "BODY":
            text = c.get("text") or ""
            if not isinstance(text, str):
                return 0
            return len(re.findall(r"\{\{\s*\d+\s*\}\}", text))
    return 0


def _validate_components(components: List[TemplateComponent]) -> None:
    body_seen = False
    for c in components:
        t = (c.type or "").upper()
        if t == "HEADER":
            fmt = (c.format or "").upper()
            if fmt and fmt not in VALID_HEADER_FORMATS:
                raise HTTPException(400, f"Invalid HEADER format '{fmt}'")
            if fmt == "TEXT" and not (c.text or "").strip():
                raise HTTPException(400, "HEADER TEXT requires non-empty text")
        elif t == "BODY":
            body_seen = True
            if not (c.text or "").strip():
                raise HTTPException(400, "BODY component requires text")
        elif t in ("FOOTER", "BUTTONS"):
            pass
        else:
            raise HTTPException(400, f"Unknown component type '{c.type}'")
    if not body_seen:
        raise HTTPException(400, "Template must include a BODY component")


def _require_admin(current_user: User, tenant_id: int) -> None:
    if (current_user.role or "").lower() != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    if int(current_user.tenant_id or 0) != int(tenant_id or 0):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant mismatch")


def _row_to_out(row: WhatsAppTemplate) -> TemplateOut:
    comps = row.components if isinstance(row.components, list) else []
    return TemplateOut(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        language=row.language,
        category=row.category,
        components=comps,
        body_placeholder_count=int(row.body_placeholder_count or 0),
        status=row.status or "DRAFT",
        rejection_reason=row.rejection_reason,
        meta_template_id=row.meta_template_id,
        submitted_at=row.submitted_at,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _push_template_event(row: WhatsAppTemplate) -> None:
    await admin_hub.broadcast_json(
        row.tenant_id,
        {
            "type": "template_status_update",
            "template_id": row.id,
            "name": row.name,
            "language": row.language,
            "status": row.status,
            "rejection_reason": row.rejection_reason,
            "meta_template_id": row.meta_template_id,
        },
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/whatsapp-message-templates", response_model=List[TemplateOut])
async def list_templates(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user, tenant_id)
    rows = (
        db.query(WhatsAppTemplate)
        .filter(WhatsAppTemplate.tenant_id == tenant_id)
        .order_by(WhatsAppTemplate.created_at.desc())
        .all()
    )
    return [_row_to_out(r) for r in rows]


@router.post(
    "/whatsapp-message-templates",
    response_model=TemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    payload: TemplateCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user, payload.tenant_id)
    if not TEMPLATE_NAME_PATTERN.match(payload.name):
        raise HTTPException(400, "Name must be lowercase a-z, 0-9, underscores only")
    if payload.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Category must be one of {sorted(VALID_CATEGORIES)}")
    _validate_components(payload.components)

    existing = (
        db.query(WhatsAppTemplate)
        .filter(
            WhatsAppTemplate.tenant_id == payload.tenant_id,
            WhatsAppTemplate.name == payload.name,
            WhatsAppTemplate.language == payload.language,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(409, "Template with same name+language already exists")

    comps_raw = [c.model_dump(exclude_none=True) for c in payload.components]
    row = WhatsAppTemplate(
        tenant_id=payload.tenant_id,
        name=payload.name,
        language=payload.language,
        category=payload.category,
        components=comps_raw,
        body_placeholder_count=_count_body_placeholders(comps_raw),
        status="DRAFT",
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    await _push_template_event(row)
    return _row_to_out(row)


@router.post(
    "/whatsapp-message-templates/{template_id}/submit",
    response_model=TemplateOut,
)
async def submit_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.id == template_id).first()
    if row is None:
        raise HTTPException(404, "Template not found")
    _require_admin(current_user, row.tenant_id)
    if row.status not in ("DRAFT", "REJECTED"):
        raise HTTPException(
            400,
            f"Template status '{row.status}' cannot be submitted; only DRAFT/REJECTED",
        )

    client = MetaWhatsAppClient()
    if not client.waba_templates_configured():
        raise HTTPException(503, "Meta WABA not configured (token + WABA id required)")
    try:
        resp = await client.create_message_template(
            name=row.name,
            language=row.language,
            category=row.category,
            components=row.components if isinstance(row.components, list) else [],
        )
    except httpx.HTTPStatusError as e:
        body = ""
        try:
            body = e.response.text[:600]
        except Exception:
            pass
        row.status = "REJECTED"
        row.rejection_reason = f"Meta API error: {body}"
        row.reviewed_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        await _push_template_event(row)
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Meta rejected submission: {body}",
        )
    except Exception as exc:
        logger.exception("submit_template failed for id=%s", template_id)
        raise HTTPException(502, f"Meta submission failed: {exc}") from exc

    meta_id = str(resp.get("id") or "").strip() or None
    meta_status = str(resp.get("status") or "PENDING").upper()
    row.meta_template_id = meta_id
    row.status = meta_status if meta_status in {"PENDING", "APPROVED", "REJECTED"} else "PENDING"
    row.rejection_reason = None
    row.submitted_at = datetime.utcnow()
    row.reviewed_at = datetime.utcnow() if row.status != "PENDING" else None
    db.add(row)
    db.commit()
    db.refresh(row)
    await _push_template_event(row)
    return _row_to_out(row)


@router.get("/whatsapp-message-templates/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.id == template_id).first()
    if row is None:
        raise HTTPException(404, "Template not found")
    _require_admin(current_user, row.tenant_id)
    return _row_to_out(row)


@router.delete(
    "/whatsapp-message-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.id == template_id).first()
    if row is None:
        raise HTTPException(404, "Template not found")
    _require_admin(current_user, row.tenant_id)

    if row.meta_template_id and row.status in ("PENDING", "APPROVED", "REJECTED", "PAUSED"):
        client = MetaWhatsAppClient()
        try:
            await client.delete_message_template(row.name)
        except Exception:
            logger.exception("Meta delete_message_template failed for %s", row.name)
    db.delete(row)
    db.commit()
    await admin_hub.broadcast_json(
        row.tenant_id,
        {"type": "template_deleted", "template_id": template_id},
    )
    return None


@router.post(
    "/whatsapp-message-templates/{template_id}/resync",
    response_model=TemplateOut,
)
async def resync_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Force a one-shot fetch from Meta in case the webhook was missed. Not polling —
    only invoked explicitly by an admin clicking 'refresh'.
    """
    row = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.id == template_id).first()
    if row is None:
        raise HTTPException(404, "Template not found")
    _require_admin(current_user, row.tenant_id)
    if not row.meta_template_id:
        raise HTTPException(400, "Template has not been submitted to Meta")
    client = MetaWhatsAppClient()
    try:
        data = await client.get_message_template(row.meta_template_id)
    except Exception as exc:
        logger.exception("resync_template failed for id=%s", template_id)
        raise HTTPException(502, f"Meta lookup failed: {exc}") from exc
    new_status = str(data.get("status") or row.status).upper()
    row.status = new_status
    rej = data.get("rejected_reason")
    if isinstance(rej, str) and rej.strip():
        row.rejection_reason = rej.strip()
    elif new_status == "APPROVED":
        row.rejection_reason = None
    row.reviewed_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    await _push_template_event(row)
    return _row_to_out(row)
