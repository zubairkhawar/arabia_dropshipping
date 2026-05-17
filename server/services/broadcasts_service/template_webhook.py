"""
Handles Meta WhatsApp webhook ``message_template_status_update`` (template approval
lifecycle) and ``messages`` ``statuses`` (per-recipient delivery state for broadcasts).

Wired from :func:`services.messaging_service.api.whatsapp_webhook` so the existing
single webhook URL keeps serving both inbound messages and these events.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from models import BroadcastCampaign, BroadcastRecipient, WhatsAppTemplate
from services.admin_realtime_service.hub import admin_hub

logger = logging.getLogger(__name__)


_STATUS_MAP = {
    "APPROVED": "APPROVED",
    "REJECTED": "REJECTED",
    "PENDING": "PENDING",
    "PAUSED": "PAUSED",
    "DISABLED": "DISABLED",
    "FLAGGED": "PAUSED",
    "PENDING_DELETION": "DISABLED",
}


async def handle_template_status_value(db: Session, value: Dict[str, Any]) -> bool:
    """
    Handle one ``change.value`` from a ``message_template_status_update`` payload.
    Returns True if a template row was updated.
    """
    name = str(value.get("message_template_name") or "").strip().lower()
    language = str(value.get("message_template_language") or "").strip()
    event = str(value.get("event") or "").strip().upper()
    reason = value.get("reason")
    meta_id = value.get("message_template_id")
    if not name:
        return False
    q = db.query(WhatsAppTemplate).filter(WhatsAppTemplate.name == name)
    if language:
        q = q.filter(WhatsAppTemplate.language == language)
    row = q.first()
    if row is None:
        logger.info(
            "template webhook for unknown template name=%s lang=%s event=%s",
            name,
            language,
            event,
        )
        return False
    mapped = _STATUS_MAP.get(event, event or "PENDING")
    row.status = mapped
    row.reviewed_at = datetime.utcnow()
    if mapped == "REJECTED" and isinstance(reason, str) and reason.strip():
        row.rejection_reason = reason.strip()
    elif mapped == "APPROVED":
        row.rejection_reason = None
    if meta_id and not row.meta_template_id:
        row.meta_template_id = str(meta_id)
    db.add(row)
    db.commit()
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
    return True


async def handle_messages_statuses(db: Session, statuses: List[Dict[str, Any]]) -> int:
    """
    Update :class:`BroadcastRecipient` rows when Meta posts delivery state for
    template-broadcast messages. Returns the number of recipients updated.
    """
    if not statuses:
        return 0
    updated = 0
    for s in statuses:
        wa_id = str(s.get("id") or "").strip()
        status_val = str(s.get("status") or "").strip().upper()
        if not wa_id or not status_val:
            continue
        recipient = (
            db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.wa_message_id == wa_id)
            .first()
        )
        if recipient is None:
            continue
        if status_val == "DELIVERED":
            recipient.status = "DELIVERED"
        elif status_val == "READ":
            recipient.status = "READ"
        elif status_val == "FAILED":
            recipient.status = "FAILED"
            err = s.get("errors")
            if isinstance(err, list) and err:
                first = err[0] if isinstance(err[0], dict) else {}
                code = first.get("code")
                title = first.get("title") or first.get("error_data", {}).get("details")
                recipient.error_code = str(code) if code is not None else recipient.error_code
                if isinstance(title, str):
                    recipient.error_message = title
        else:
            continue
        db.add(recipient)
        db.commit()
        campaign = (
            db.query(BroadcastCampaign)
            .filter(BroadcastCampaign.id == recipient.campaign_id)
            .first()
        )
        if campaign is not None:
            await admin_hub.broadcast_json(
                campaign.tenant_id,
                {
                    "type": "recipient_status_update",
                    "campaign_id": campaign.id,
                    "recipient_id": recipient.id,
                    "phone": recipient.phone,
                    "status": recipient.status,
                    "error_message": recipient.error_message,
                },
            )
        updated += 1
    return updated


async def dispatch_meta_webhook_extras(db: Session, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inspect a Meta webhook body for template + delivery-status events and apply them.
    Inbound user messages are handled separately by the existing pipeline.
    """
    template_updates = 0
    status_updates = 0
    if not isinstance(body, dict):
        return {"template_updates": 0, "status_updates": 0}
    for entry in body.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            field = (change.get("field") or "").strip().lower()
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            if field == "message_template_status_update":
                if await handle_template_status_value(db, value):
                    template_updates += 1
            elif field == "messages":
                statuses = value.get("statuses")
                if isinstance(statuses, list):
                    status_updates += await handle_messages_statuses(db, statuses)
    return {"template_updates": template_updates, "status_updates": status_updates}
