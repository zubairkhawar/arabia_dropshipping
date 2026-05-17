"""
Background send worker for :class:`BroadcastCampaign`.

Drains QUEUED recipients, sends the approved template via Meta, persists wa_message_id
and per-recipient status, and pushes incremental progress over the admin WebSocket hub.

A simple in-process semaphore caps concurrent sends; tune
``BROADCAST_SEND_CONCURRENCY`` if rate limits change.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from database import SessionLocal
from models import BroadcastCampaign, BroadcastRecipient, WhatsAppTemplate
from services.admin_realtime_service.hub import admin_hub
from services.whatsapp_service.meta_cloud import MetaWhatsAppClient

logger = logging.getLogger(__name__)

BROADCAST_SEND_CONCURRENCY = 4  # parallel outbound requests per worker
BROADCAST_BATCH_SIZE = 50        # recipients pulled per DB batch


def enqueue_campaign_send(campaign_id: int, background: BackgroundTasks) -> None:
    """
    Fire-and-forget: registers :func:`_run_campaign` on FastAPI's BackgroundTasks so
    it runs after the HTTP response is sent.
    """
    background.add_task(_run_campaign, campaign_id)


async def _run_campaign(campaign_id: int) -> None:
    db = SessionLocal()
    try:
        c = (
            db.query(BroadcastCampaign)
            .filter(BroadcastCampaign.id == campaign_id)
            .first()
        )
        if c is None:
            logger.warning("send_worker: campaign %s missing", campaign_id)
            return
        t = (
            db.query(WhatsAppTemplate)
            .filter(WhatsAppTemplate.id == c.template_id)
            .first()
        )
        if t is None or (t.status or "").upper() != "APPROVED":
            c.status = "FAILED"
            c.completed_at = datetime.utcnow()
            db.add(c)
            db.commit()
            await _push_campaign(c)
            return

        c.status = "SENDING"
        c.started_at = c.started_at or datetime.utcnow()
        db.add(c)
        db.commit()
        await _push_campaign(c)

        client = MetaWhatsAppClient()
        semaphore = asyncio.Semaphore(BROADCAST_SEND_CONCURRENCY)
        canceled = False

        while not canceled:
            db.refresh(c)
            if c.status == "CANCELED":
                canceled = True
                break
            batch = (
                db.query(BroadcastRecipient)
                .filter(
                    BroadcastRecipient.campaign_id == c.id,
                    BroadcastRecipient.status == "QUEUED",
                )
                .order_by(BroadcastRecipient.id.asc())
                .limit(BROADCAST_BATCH_SIZE)
                .all()
            )
            if not batch:
                break
            await asyncio.gather(
                *(
                    _send_one(client, semaphore, c.tenant_id, c.id, t, r.id)
                    for r in batch
                ),
                return_exceptions=True,
            )
            db.refresh(c)

        # Final tally.
        sent = (
            db.query(BroadcastRecipient)
            .filter(
                BroadcastRecipient.campaign_id == c.id,
                BroadcastRecipient.status.in_(("SENT", "DELIVERED", "READ")),
            )
            .count()
        )
        failed = (
            db.query(BroadcastRecipient)
            .filter(
                BroadcastRecipient.campaign_id == c.id,
                BroadcastRecipient.status == "FAILED",
            )
            .count()
        )
        c.sent_count = sent
        c.failed_count = failed
        if canceled:
            pass  # status already CANCELED
        elif failed == 0:
            c.status = "COMPLETED"
        elif sent == 0:
            c.status = "FAILED"
        else:
            c.status = "COMPLETED"
        c.completed_at = datetime.utcnow()
        db.add(c)
        db.commit()
        await _push_campaign(c)
    except Exception:
        logger.exception("send_worker run_campaign failed (campaign_id=%s)", campaign_id)
    finally:
        db.close()


async def _send_one(
    client: MetaWhatsAppClient,
    semaphore: asyncio.Semaphore,
    tenant_id: int,
    campaign_id: int,
    template: WhatsAppTemplate,
    recipient_id: int,
) -> None:
    async with semaphore:
        local_db = SessionLocal()
        try:
            r = (
                local_db.query(BroadcastRecipient)
                .filter(BroadcastRecipient.id == recipient_id)
                .first()
            )
            if r is None or r.status != "QUEUED":
                return
            variables = r.variables if isinstance(r.variables, list) else []
            try:
                resp = await client.send_template_message(
                    to_phone=r.phone,
                    template_name=template.name,
                    language_code=template.language,
                    body_parameters=[str(v or "") for v in variables],
                )
                wa_id = _extract_wa_message_id(resp)
                r.status = "SENT"
                r.wa_message_id = wa_id
                r.sent_at = datetime.utcnow()
                r.error_code = None
                r.error_message = None
            except httpx.HTTPStatusError as e:
                r.status = "FAILED"
                r.error_code = str(e.response.status_code)
                r.error_message = (e.response.text or "")[:500]
            except Exception as exc:
                r.status = "FAILED"
                r.error_code = "EXC"
                r.error_message = str(exc)[:500]
            local_db.add(r)
            local_db.commit()
            await admin_hub.broadcast_json(
                tenant_id,
                {
                    "type": "recipient_status_update",
                    "campaign_id": campaign_id,
                    "recipient_id": r.id,
                    "phone": r.phone,
                    "status": r.status,
                    "error_message": r.error_message,
                },
            )
            # Refresh campaign counters so the UI can drive a progress bar without polling.
            c = (
                local_db.query(BroadcastCampaign)
                .filter(BroadcastCampaign.id == campaign_id)
                .first()
            )
            if c is not None:
                if r.status == "SENT":
                    c.sent_count = int(c.sent_count or 0) + 1
                else:
                    c.failed_count = int(c.failed_count or 0) + 1
                local_db.add(c)
                local_db.commit()
                await _push_campaign(c)
        except Exception:
            logger.exception("send_one failed (recipient_id=%s)", recipient_id)
        finally:
            local_db.close()


def _extract_wa_message_id(resp: Dict[str, Any]) -> Optional[str]:
    if not isinstance(resp, dict):
        return None
    msgs = resp.get("messages")
    if isinstance(msgs, list) and msgs:
        m0 = msgs[0]
        if isinstance(m0, dict):
            mid = m0.get("id")
            if isinstance(mid, str) and mid.strip():
                return mid.strip()
    return None


async def _push_campaign(c: BroadcastCampaign) -> None:
    await admin_hub.broadcast_json(
        c.tenant_id,
        {
            "type": "campaign_status_update",
            "campaign_id": c.id,
            "status": c.status,
            "sent_count": int(c.sent_count or 0),
            "failed_count": int(c.failed_count or 0),
            "recipient_count": int(c.recipient_count or 0),
        },
    )
