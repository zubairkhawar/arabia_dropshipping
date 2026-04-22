"""
When an agent goes offline, return all their non-closed assigned conversations to the bot.

Mirrors the customer-visible and DB effects of an explicit agent close, but with a distinct
system line so support can tell accidental disconnect from a deliberate close.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Agent, Conversation, Customer, Message
from services.agent_portal_service.broadcast import push_inbox_message, push_inbox_sync_event
from services.customer_bot_flow import lookup_agent_display_name
from services.customer_bot_flow.session_reset import normalize_bot_flow_after_human_handoff_end
from services.media_storage.r2 import enrich_metadata_for_api
from services.whatsapp_service.meta_cloud import MetaWhatsAppClient

logger = logging.getLogger(__name__)

OFFLINE_HANDOVER_TEXT = (
    "The agent went offline. Arabia Dropbot will continue helping you from here."
)


def _message_dict_minimal_for_inbox_ws(m: Message) -> dict:
    """WS payload for a freshly inserted row (no receipt rows yet)."""
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "content": m.content,
        "sender_type": m.sender_type,
        "sender_id": m.sender_id,
        "language": m.language,
        "created_at": m.created_at,
        "reply_to_message_id": m.reply_to_message_id,
        "edited_at": m.edited_at,
        "deleted_for_everyone_at": m.deleted_for_everyone_at,
        "status": {"sent": True, "delivered": False, "read": False},
        "message_metadata": enrich_metadata_for_api(m.message_metadata),
    }


def _live_assigned_conversations(db: Session, agent: Agent) -> List[Conversation]:
    return (
        db.query(Conversation)
        .filter(
            Conversation.agent_id == agent.id,
            Conversation.tenant_id == agent.tenant_id,
            func.lower(func.coalesce(Conversation.status, "")).notin_(
                ["closed", "resolved"]
            ),
        )
        .all()
    )


async def release_live_conversations_when_agent_went_offline(db: Session, agent: Agent) -> int:
    """
    Close every active/escalated conversation still assigned to this agent: clear assignment,
    set status closed, reset bot flow to conversational, persist handover line, notify inbox WS,
    and send WhatsApp when applicable.

    Returns how many conversations were updated.
    """
    convs = _live_assigned_conversations(db, agent)
    if not convs:
        return 0

    updated = 0
    for conversation in convs:
        assigned_agent_id_before = conversation.agent_id
        if assigned_agent_id_before is None:
            continue

        normalize_bot_flow_after_human_handoff_end(conversation)

        meta = (
            conversation.conversation_metadata
            if isinstance(conversation.conversation_metadata, dict)
            else {}
        )
        prev_agent = db.query(Agent).filter(Agent.id == assigned_agent_id_before).first()
        label = (
            lookup_agent_display_name(db, int(assigned_agent_id_before))
            if prev_agent
            else None
        ) or "Agent"
        meta = {
            **meta,
            "last_handler": {
                "agent_id": int(assigned_agent_id_before),
                "agent_name": label,
                "at": datetime.utcnow().isoformat(),
            },
            "awaiting_first_customer_after_agent_close": True,
        }
        conversation.conversation_metadata = meta
        conversation.agent_id = None
        conversation.status = "closed"
        conversation.updated_at = datetime.utcnow()
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        notice = Message(
            conversation_id=conversation.id,
            content=OFFLINE_HANDOVER_TEXT,
            sender_type="ai",
            sender_id=None,
            created_at=datetime.utcnow(),
            message_metadata={"system_event": "agent_went_offline"},
        )
        db.add(notice)
        conversation.updated_at = datetime.utcnow()
        db.add(conversation)
        db.commit()
        db.refresh(notice)
        db.refresh(conversation)

        try:
            await push_inbox_message(
                db,
                conversation.tenant_id,
                int(assigned_agent_id_before),
                conversation.id,
                _message_dict_minimal_for_inbox_ws(notice),
            )
        except Exception:
            logger.exception(
                "agent offline release: inbox_message push failed (conversation_id=%s)",
                conversation.id,
            )

        try:
            await push_inbox_sync_event(
                db,
                conversation.tenant_id,
                int(assigned_agent_id_before),
                {
                    "type": "inbox_conversation_refresh",
                    "conversation_id": conversation.id,
                    "reason": "agent_went_offline",
                },
            )
        except Exception:
            logger.exception(
                "agent offline release: inbox refresh broadcast failed (conversation_id=%s)",
                conversation.id,
            )

        if (conversation.channel or "").lower() == "whatsapp":
            customer = (
                db.query(Customer).filter(Customer.id == conversation.customer_id).first()
            )
            phone = customer.phone if customer else None
            wa = MetaWhatsAppClient()
            if phone and wa.is_configured():
                try:
                    wa_resp = await wa.send_text_message(
                        to_phone=str(phone), text=OFFLINE_HANDOVER_TEXT
                    )
                    row_meta = dict(notice.message_metadata or {})
                    msgs = wa_resp.get("messages") if isinstance(wa_resp, dict) else None
                    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
                        out_wa_id = str(msgs[0].get("id") or "").strip()
                        if out_wa_id:
                            row_meta["wa_message_id"] = out_wa_id
                    notice.message_metadata = row_meta
                    notice.wa_delivered_at = datetime.utcnow()
                    db.add(notice)
                    conversation.updated_at = datetime.utcnow()
                    db.add(conversation)
                    db.commit()
                    db.refresh(notice)
                except Exception:
                    logger.exception(
                        "WhatsApp agent-offline notify failed (conversation_id=%s)",
                        conversation.id,
                    )

        updated += 1

    return updated
