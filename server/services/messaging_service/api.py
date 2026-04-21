import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, WebSocket, Request, Depends, HTTPException, status, Query, Body
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Agent,
    Conversation,
    ConversationAgentReadState,
    Customer,
    InboxMessageReceipt,
    Message,
    MessageUserDeletion,
    Notification,
    Store,
    TenantSchedule,
    User,
)
from config import settings
from services.ai_orchestrator_service.services import AIOrchestrator
from langchain_bot import ArabiaLangChainBot
from langchain_bot.conversation_hints import (
    format_recent_context_hint_for_prompt,
    patch_conversation_metadata_with_last_topic,
)
from services.whatsapp_service.meta_cloud import MetaWhatsAppClient
from services.customer_bot_flow import (
    append_handoff_agent_line,
    format_kb_reply,
    lookup_agent_display_name,
    process_customer_bot_message,
    resolve_bot_template,
)
from services.customer_bot_flow.session_reset import release_agent_and_clear_bot_flow
from services.tenant_schedule_text import format_tenant_schedule_line_for_handoff
from services.human_handoff_intent import is_slash_reset_command
from services.agent_routing_service.api import assign_from_bot_flow
from services.intent_detector import IntentDetector
from services.memory_service import (
    ConversationMemory,
    format_memory_block_for_prompt,
    normalize_memory_scope_id,
    record_conversation_turn,
)
from services.agent_portal_service.unread_compute import _inbox_unread_for_conversation
from services.agent_portal_service.broadcast import (
    notify_bot_handoff_assigned,
    push_inbox_message,
    push_inbox_sync_event,
    push_unread_summary,
)
from services.auth_service.api import get_current_user, get_current_user_optional
from services.media_storage.r2 import (
    delete_object,
    enrich_metadata_for_api,
    store_inbound_whatsapp_media,
)
from services.messaging_service.inbox_receipts import (
    ensure_receipt_for_customer_message,
    get_receipt_map,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _already_processed_wa_message(db: Session, wa_message_id: str) -> bool:
    """
    Best-effort webhook idempotency: ignore duplicate inbound WhatsApp message ids.
    """
    mid = (wa_message_id or "").strip()
    if not mid:
        return False
    try:
        row = (
            db.query(Message.id)
            .filter(Message.message_metadata["wa_message_id"].astext == mid)
            .first()
        )
        if row:
            return True
    except Exception:
        # Fallback when JSON path operator is unavailable for the current DB backend.
        pass
    try:
        recent = db.query(Message).order_by(desc(Message.id)).limit(400).all()
        for m in recent:
            meta = m.message_metadata if isinstance(m.message_metadata, dict) else {}
            if str(meta.get("wa_message_id") or "").strip() == mid:
                return True
    except Exception:
        return False
    return False


class ConversationSummary(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    customer_id: int
    customer_phone: Optional[str] = None
    agent_id: Optional[int]
    channel: str
    status: str
    customer_name: Optional[str] = None
    last_message: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    unread_count: int = 0
    is_new_customer: bool = False
    last_handler_agent_name: Optional[str] = None
    transfer_from_agent_id: Optional[int] = None
    transfer_from_agent_name: Optional[str] = None
    transfer_to_agent_id: Optional[int] = None
    transfer_to_agent_name: Optional[str] = None


class ConversationSearchResult(BaseModel):
    id: int
    customer_name: str
    customer_phone: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    match_snippet: Optional[str] = None
    unread_count: int = 0


class ConversationCreate(BaseModel):
    tenant_id: int
    store_id: int
    customer_id: int
    channel: str  # whatsapp, web, portal
    initial_message: Optional[str] = None
    sender_type: Optional[str] = "customer"


class MessageCreate(BaseModel):
    conversation_id: int
    content: str
    sender_type: str  # customer, agent, ai
    channel: str  # whatsapp, web, portal
    reply_to_message_id: Optional[int] = None
    message_metadata: Optional[Dict[str, Any]] = None


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    content: str
    sender_type: str
    sender_id: Optional[int]
    language: Optional[str]
    created_at: datetime
    reply_to_message_id: Optional[int] = None
    edited_at: Optional[datetime] = None
    message_metadata: Optional[Dict[str, Any]] = None
    status: Optional[Dict[str, bool]] = None


class MessageEditIn(BaseModel):
    content: str


class MessageReactionIn(BaseModel):
    emoji: str


class ConversationStatusUpdate(BaseModel):
    status: str  # active | closed | escalated


class ConversationInternalNoteIn(BaseModel):
    note: str = ""


class WhatsAppWebhookPayload(BaseModel):
    """
    Minimal normalized payload for a WhatsApp-style webhook.
    In production you would validate the raw provider payload and signature
    before mapping into this schema.
    """

    from_phone: str
    text: str
    store_code: Optional[str] = None
    conversation_id: Optional[int] = None


def _build_conversation_summary(c: Conversation, unread_count: int = 0) -> ConversationSummary:
    last_msg = c.messages[-1] if c.messages else None
    customer_name = None
    customer_phone = None
    if c.customer and getattr(c.customer, "name", None):
        customer_name = c.customer.name
    if c.customer and getattr(c.customer, "phone", None):
        customer_phone = c.customer.phone

    meta = c.conversation_metadata if isinstance(c.conversation_metadata, dict) else {}
    bot_flow = meta.get("bot_flow") if isinstance(meta.get("bot_flow"), dict) else {}
    # Customer is "new" unless they have been successfully verified through the bot flow.
    is_new_customer = not bool(bot_flow.get("verified"))
    # When agent_id is cleared (send-to-AI / reset), fall back to last_handler from metadata.
    last_handler_meta = meta.get("last_handler") if isinstance(meta.get("last_handler"), dict) else {}
    last_handler_agent_name = (
        last_handler_meta.get("agent_name")
        if isinstance(last_handler_meta.get("agent_name"), str)
        else None
    )
    transfer_meta = meta.get("last_transfer") if isinstance(meta.get("last_transfer"), dict) else {}
    transfer_from_agent_id = transfer_meta.get("from_agent_id")
    transfer_to_agent_id = transfer_meta.get("to_agent_id")

    return ConversationSummary(
        id=c.id,
        tenant_id=c.tenant_id,
        store_id=c.store_id,
        customer_id=c.customer_id,
        customer_phone=customer_phone,
        agent_id=c.agent_id,
        channel=c.channel,
        status=c.status,
        customer_name=customer_name,
        last_message=last_msg.content if last_msg else None,
        last_activity_at=last_msg.created_at if last_msg else c.updated_at,
        unread_count=unread_count,
        is_new_customer=is_new_customer,
        last_handler_agent_name=last_handler_agent_name,
        transfer_from_agent_id=transfer_from_agent_id if isinstance(transfer_from_agent_id, int) else None,
        transfer_from_agent_name=transfer_meta.get("from_agent_name")
        if isinstance(transfer_meta.get("from_agent_name"), str)
        else None,
        transfer_to_agent_id=transfer_to_agent_id if isinstance(transfer_to_agent_id, int) else None,
        transfer_to_agent_name=transfer_meta.get("to_agent_name")
        if isinstance(transfer_meta.get("to_agent_name"), str)
        else None,
    )


def _r2_keys_from_message_metadata(meta: Any) -> List[str]:
    """Collect R2 object keys stored on inbox message metadata (media)."""
    keys: List[str] = []
    if not isinstance(meta, dict):
        return keys
    for k in ("object_key", "thumbnail_object_key"):
        raw = meta.get(k)
        if isinstance(raw, str) and raw.strip():
            keys.append(raw.strip())
    return keys


def _fit_snippet(text: Optional[str], max_len: int = 140) -> Optional[str]:
    if not text:
        return None
    s = " ".join(str(text).split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _filter_hidden_inbox_ids(db: Session, user_id: int, conversation_id: int) -> set[int]:
    mid_rows = db.query(Message.id).filter(Message.conversation_id == conversation_id).all()
    ids = [r[0] for r in mid_rows]
    if not ids:
        return set()
    hidden = (
        db.query(MessageUserDeletion.message_id)
        .filter(
            MessageUserDeletion.user_id == user_id,
            MessageUserDeletion.channel == "inbox",
            MessageUserDeletion.message_id.in_(ids),
        )
        .all()
    )
    return {h[0] for h in hidden}


def _inbox_message_api_dict(
    m: Message,
    conv: Conversation,
    receipt: Optional[InboxMessageReceipt],
    reply_row: Optional[Message],
) -> Dict[str, Any]:
    deleted = bool(m.deleted_for_everyone_at)
    content = "[Message deleted]" if deleted else m.content
    if m.sender_type == "agent":
        delivered = m.wa_delivered_at is not None
        # Meta read status is not yet persisted; use delivered as a temporary read proxy.
        read = delivered
    else:
        delivered = receipt.delivered_at is not None if receipt else False
        read = receipt.read_at is not None if receipt else False
    meta_raw = None if deleted else m.message_metadata
    out: Dict[str, Any] = {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "content": content,
        "sender_type": m.sender_type,
        "sender_id": m.sender_id,
        "language": m.language,
        "created_at": m.created_at,
        "reply_to_message_id": m.reply_to_message_id,
        "edited_at": m.edited_at,
        "deleted_for_everyone_at": m.deleted_for_everyone_at,
        "status": {"sent": True, "delivered": delivered, "read": read},
        "message_metadata": enrich_metadata_for_api(meta_raw) if meta_raw else None,
    }
    if m.reply_to_message_id and reply_row:
        txt = reply_row.content or ""
        out["reply_preview"] = {
            "id": reply_row.id,
            "sender_type": reply_row.sender_type,
            "content": txt[:200] + ("…" if len(txt) > 200 else ""),
        }
    return out


def _extract_reactions_from_meta(meta: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(meta, dict):
        return []
    rows = meta.get("reactions")
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        emoji = r.get("emoji")
        user_id = r.get("userId")
        user_name = r.get("userName")
        reacted_at = r.get("reactedAt")
        if not isinstance(emoji, str) or not emoji.strip():
            continue
        if not isinstance(user_id, str) or not user_id.strip():
            continue
        if not isinstance(user_name, str) or not user_name.strip():
            continue
        if not isinstance(reacted_at, str) or not reacted_at.strip():
            continue
        out.append(
            {
                "emoji": emoji.strip(),
                "userId": user_id.strip(),
                "userName": user_name.strip(),
                "reactedAt": reacted_at.strip(),
            }
        )
    return out


def _upsert_message_reaction(
    meta: Optional[Dict[str, Any]],
    *,
    user_id: str,
    user_name: str,
    emoji: str,
) -> Dict[str, Any]:
    next_meta: Dict[str, Any] = dict(meta) if isinstance(meta, dict) else {}
    reactions = _extract_reactions_from_meta(next_meta)
    reactions = [r for r in reactions if str(r.get("userId")) != user_id]
    if emoji:
        reactions.append(
            {
                "emoji": emoji,
                "userId": user_id,
                "userName": user_name,
                "reactedAt": datetime.utcnow().isoformat(),
            }
        )
    if reactions:
        next_meta["reactions"] = reactions
    elif "reactions" in next_meta:
        next_meta.pop("reactions", None)
    return next_meta


def _serialize_inbox_messages(
    db: Session,
    rows: List[Message],
    conv: Conversation,
    viewer_user_id: Optional[int],
) -> List[Dict[str, Any]]:
    hidden: set[int] = set()
    if viewer_user_id:
        hidden = _filter_hidden_inbox_ids(db, viewer_user_id, conv.id)
    visible = [m for m in rows if m.id not in hidden]
    if not visible:
        return []
    mids = [m.id for m in visible]
    reply_ids = list({m.reply_to_message_id for m in visible if m.reply_to_message_id})
    reply_map: Dict[int, Message] = {}
    if reply_ids:
        for rm in db.query(Message).filter(Message.id.in_(reply_ids)).all():
            reply_map[rm.id] = rm
    rec_map = get_receipt_map(db, mids, conv.agent_id)
    return [
        _inbox_message_api_dict(
            m,
            conv,
            rec_map.get(m.id),
            reply_map.get(m.reply_to_message_id) if m.reply_to_message_id else None,
        )
        for m in visible
    ]


def _message_dict_for_ws(db: Session, m: Message) -> Dict[str, Any]:
    conv = db.query(Conversation).filter(Conversation.id == m.conversation_id).first()
    if not conv:
        return {
            "id": m.id,
            "conversation_id": m.conversation_id,
            "content": m.content,
            "sender_type": m.sender_type,
            "sender_id": m.sender_id,
            "language": m.language,
            "created_at": m.created_at,
            "status": {"sent": True, "delivered": False, "read": False},
            "message_metadata": enrich_metadata_for_api(m.message_metadata),
        }
    rec = get_receipt_map(db, [m.id], conv.agent_id).get(m.id)
    reply_row = None
    if m.reply_to_message_id:
        reply_row = db.query(Message).filter(Message.id == m.reply_to_message_id).first()
    return _inbox_message_api_dict(m, conv, rec, reply_row)


def _parse_meta_whatsapp_inbound(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse Meta webhook: first inbound user message as text, image, or audio.
    """
    if payload.get("object") != "whatsapp_business_account":
        return None
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages") or []
            if not messages:
                continue
            contacts = value.get("contacts") or []
            contact_name = None
            if contacts and isinstance(contacts[0], dict):
                profile = contacts[0].get("profile") or {}
                contact_name = profile.get("name")
            for msg in messages:
                from_phone = msg.get("from")
                wa_message_id = msg.get("id")
                if not from_phone or not wa_message_id:
                    continue
                base = {
                    "from_phone": from_phone,
                    "wa_message_id": wa_message_id,
                    "contact_name": contact_name,
                    "timestamp": msg.get("timestamp"),
                }
                mtype = msg.get("type")
                if mtype == "text":
                    text = (msg.get("text") or {}).get("body", "")
                    if not text:
                        continue
                    return {**base, "kind": "text", "text": text}
                if mtype == "image":
                    img = msg.get("image") or {}
                    mid = img.get("id")
                    if not mid:
                        continue
                    cap = (img.get("caption") or "") if isinstance(img.get("caption"), str) else ""
                    return {**base, "kind": "image", "media_id": str(mid), "caption": cap}
                if mtype == "audio":
                    au = msg.get("audio") or {}
                    mid = au.get("id")
                    if not mid:
                        continue
                    dur_raw = au.get("duration")
                    duration_seconds = None
                    if isinstance(dur_raw, (int, float)):
                        duration_seconds = int(dur_raw)
                    elif isinstance(dur_raw, str) and dur_raw.strip().isdigit():
                        duration_seconds = int(dur_raw.strip())
                    return {
                        **base,
                        "kind": "audio",
                        "media_id": str(mid),
                        "duration_seconds": duration_seconds,
                    }
                if mtype == "document":
                    doc = msg.get("document") or {}
                    mid = doc.get("id")
                    if not mid:
                        continue
                    return {
                        **base,
                        "kind": "document",
                        "media_id": str(mid),
                        "filename": str(doc.get("filename") or "File"),
                    }
                if mtype == "reaction":
                    rxn = msg.get("reaction") or {}
                    target_id = rxn.get("message_id")
                    emoji = rxn.get("emoji")
                    if not isinstance(target_id, str) or not target_id.strip():
                        continue
                    if not isinstance(emoji, str):
                        emoji = ""
                    return {
                        **base,
                        "kind": "reaction",
                        "target_wa_message_id": target_id.strip(),
                        "emoji": emoji.strip(),
                    }
                if mtype == "sticker":
                    st = msg.get("sticker") or {}
                    mid = st.get("id")
                    if not mid:
                        continue
                    return {**base, "kind": "image", "media_id": str(mid), "caption": ""}
    return None


def _get_or_create_default_store(db: Session, tenant_id: int) -> Store:
    store = (
        db.query(Store)
        .filter(Store.tenant_id == tenant_id, Store.is_active.is_(True))
        .order_by(Store.id.asc())
        .first()
    )
    if store:
        return store
    store = Store(
        tenant_id=tenant_id,
        name="WhatsApp Default Store",
        store_code=f"tenant-{tenant_id}-whatsapp-default",
        store_type="custom_api",
        is_active=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def _get_or_create_customer_by_phone(
    db: Session, tenant_id: int, store_id: int, phone: str, name: Optional[str]
) -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.tenant_id == tenant_id, Customer.phone == phone)
        .first()
    )
    if customer:
        if name and not customer.name:
            customer.name = name
            db.add(customer)
            db.commit()
            db.refresh(customer)
        return customer

    customer = Customer(
        tenant_id=tenant_id,
        store_id=store_id,
        phone=phone,
        name=name or f"WhatsApp {phone}",
        customer_data={"source": "meta_whatsapp_cloud"},
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def _get_or_create_active_whatsapp_conversation(
    db: Session, tenant_id: int, store_id: int, customer_id: int
) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Conversation.store_id == store_id,
            Conversation.customer_id == customer_id,
            Conversation.channel == "whatsapp",
            Conversation.status == "active",
        )
        .order_by(desc(Conversation.updated_at))
        .first()
    )
    if conversation:
        return conversation

    # Reuse the latest closed thread for this phone so admin/agent inboxes stay
    # one row per customer (no duplicate active+closed rows after reopen).
    closed = (
        db.query(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Conversation.store_id == store_id,
            Conversation.customer_id == customer_id,
            Conversation.channel == "whatsapp",
            Conversation.status.in_(["closed", "resolved"]),
        )
        .order_by(desc(Conversation.updated_at))
        .first()
    )
    if closed:
        closed.status = "active"
        closed.agent_id = None
        meta = closed.conversation_metadata if isinstance(closed.conversation_metadata, dict) else {}
        meta["reopened_after_close_at"] = datetime.utcnow().isoformat()
        closed.conversation_metadata = meta
        closed.updated_at = datetime.utcnow()
        db.add(closed)
        db.commit()
        db.refresh(closed)
        return closed

    conversation = Conversation(
        tenant_id=tenant_id,
        store_id=store_id,
        customer_id=customer_id,
        channel="whatsapp",
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=List[ConversationSummary])
async def list_conversations(
    tenant_id: int,
    status_param: Optional[str] = None,
    agent_id: Optional[int] = None,
    include_transferred_out_for_agent_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    List conversations for admin/agent inboxes with basic filters.
    """
    query = (
        db.query(Conversation)
        .filter(Conversation.tenant_id == tenant_id)
        .order_by(desc(Conversation.updated_at))
    )
    if status_param:
        query = query.filter(Conversation.status == status_param)

    conversations: List[Conversation] = []
    if agent_id is not None:
        # Always include currently assigned conversations for this agent.
        assigned_query = query.filter(Conversation.agent_id == agent_id)
        assigned = assigned_query.offset(offset).limit(limit).all()
        conversations.extend(assigned)
        # Optionally include conversations this agent transferred out most recently.
        if include_transferred_out_for_agent_id is not None:
            transferred = (
                db.query(Conversation)
                .filter(
                    Conversation.tenant_id == tenant_id,
                    Conversation.agent_id != include_transferred_out_for_agent_id,
                )
                .order_by(desc(Conversation.updated_at))
                .limit(limit * 3)
                .all()
            )
            for c in transferred:
                meta = c.conversation_metadata if isinstance(c.conversation_metadata, dict) else {}
                tx = meta.get("last_transfer") if isinstance(meta.get("last_transfer"), dict) else {}
                from_id = tx.get("from_agent_id")
                if isinstance(from_id, int) and from_id == include_transferred_out_for_agent_id:
                    conversations.append(c)
    else:
        conversations = query.offset(offset).limit(limit).all()

    # De-duplicate + sort newest first.
    dedup: Dict[int, Conversation] = {}
    for c in conversations:
        dedup[c.id] = c
    conversations = sorted(dedup.values(), key=lambda x: x.updated_at or datetime.min, reverse=True)[:limit]

    # Eager-load relationships used in the summary (customer, messages)
    for conv in conversations:
        _ = conv.customer
        _ = conv.messages

    out: List[ConversationSummary] = []
    for c in conversations:
        u = 0
        if agent_id is not None:
            u = _inbox_unread_for_conversation(db, tenant_id, agent_id, c.id)
        out.append(_build_conversation_summary(c, unread_count=u))
    return out


def _conversation_visible_to_agent_inbox(
    conversation: Conversation,
    agent_id: int,
    include_transferred_out_for_agent_id: Optional[int],
) -> bool:
    """Same visibility rules as list_conversations for agent-scoped inbox."""
    if conversation.agent_id is not None and int(conversation.agent_id) == int(agent_id):
        return True
    if (
        include_transferred_out_for_agent_id is not None
        and int(include_transferred_out_for_agent_id) == int(agent_id)
    ):
        meta = conversation.conversation_metadata if isinstance(conversation.conversation_metadata, dict) else {}
        tx = meta.get("last_transfer") if isinstance(meta.get("last_transfer"), dict) else {}
        from_id = tx.get("from_agent_id")
        if isinstance(from_id, int) and from_id == agent_id:
            return True
    return False


@router.get("/conversations/{conversation_id}/summary", response_model=ConversationSummary)
async def get_conversation_inbox_summary(
    conversation_id: int,
    tenant_id: int = Query(...),
    agent_id: Optional[int] = Query(None),
    include_transferred_out_for_agent_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    One row for inbox merge (agent panel): same shape as list_conversations, without loading all threads.
    Returns 404 if the conversation is not visible to this agent (assigned or transferred-out).
    """
    conversation: Conversation | None = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
        .first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    if agent_id is not None:
        if not _conversation_visible_to_agent_inbox(
            conversation,
            agent_id,
            include_transferred_out_for_agent_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
    _ = conversation.customer
    _ = conversation.messages
    u = 0
    if agent_id is not None:
        u = _inbox_unread_for_conversation(db, tenant_id, agent_id, conversation.id)
    # Admin / unscoped callers omit agent_id; unread not computed.
    return _build_conversation_summary(conversation, unread_count=u)


@router.get("/conversations/search", response_model=List[ConversationSearchResult])
async def search_conversations(
    tenant_id: int,
    q: str = Query(..., min_length=1),
    agent_id: Optional[int] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Search conversations by customer name/phone and any message content.
    Returns conversation-level results (not individual messages).
    """
    query_text = (q or "").strip()
    if not query_text:
        return []
    like = f"%{query_text}%"

    base = db.query(Conversation).filter(Conversation.tenant_id == tenant_id)
    if agent_id is not None:
        base = base.filter(Conversation.agent_id == agent_id)
    conversations = base.order_by(desc(Conversation.updated_at)).limit(500).all()

    out: List[ConversationSearchResult] = []
    for c in conversations:
        customer_name = (getattr(c.customer, "name", None) or "").strip() or f"Customer #{c.customer_id}"
        customer_phone = (getattr(c.customer, "phone", None) or "").strip() or None
        name_match = query_text.lower() in customer_name.lower()
        phone_match = bool(customer_phone and query_text.lower() in customer_phone.lower())
        matched_message = (
            db.query(Message)
            .filter(Message.conversation_id == c.id, Message.content.ilike(like))
            .order_by(desc(Message.created_at))
            .first()
        )
        if not (name_match or phone_match or matched_message):
            continue

        snippet = None
        matched_at = c.updated_at
        if matched_message is not None:
            snippet = _fit_snippet(matched_message.content)
            matched_at = matched_message.created_at
        elif name_match or phone_match:
            snippet = _fit_snippet(c.messages[-1].content if c.messages else None)
            matched_at = c.messages[-1].created_at if c.messages else c.updated_at

        unread = _inbox_unread_for_conversation(db, tenant_id, agent_id, c.id) if agent_id is not None else 0
        out.append(
            ConversationSearchResult(
                id=c.id,
                customer_name=customer_name,
                customer_phone=customer_phone,
                last_activity_at=matched_at,
                match_snippet=snippet,
                unread_count=unread,
            )
        )

    out.sort(key=lambda x: x.last_activity_at or datetime.min, reverse=True)
    return out[:limit]


@router.get("/conversations/{conversation_id}", response_model=Dict[str, Any])
async def get_conversation(
    conversation_id: int,
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[int] = Query(
        None, description="Load older messages with id strictly less than this"
    ),
    since: Optional[datetime] = Query(
        None, description="Messages strictly after this time (reconnect gap fill)"
    ),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Get conversation details and a page of messages (latest page by default; older via before_id).
    """
    conversation: Conversation | None = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )

    base = db.query(Message).filter(Message.conversation_id == conversation.id)

    if since is not None:
        rows = (
            base.filter(Message.created_at > since)
            .order_by(Message.created_at.asc())
            .limit(500)
            .all()
        )
        viewer_id = current_user.id if current_user else None
        payload = _serialize_inbox_messages(db, rows, conversation, viewer_id)
        return {
            "conversation": {
                "id": conversation.id,
                "tenant_id": conversation.tenant_id,
                "store_id": conversation.store_id,
                "customer_id": conversation.customer_id,
                "agent_id": conversation.agent_id,
                "channel": conversation.channel,
                "status": conversation.status,
                "created_at": conversation.created_at,
                "updated_at": conversation.updated_at,
                "internal_note": (
                    (conversation.conversation_metadata or {}).get("internal_note")
                    if isinstance(conversation.conversation_metadata, dict)
                    else None
                ),
            },
            "messages": payload,
            "has_more_older": False,
        }

    lim = max(1, min(limit, 200))
    if before_id is not None:
        rows_desc = (
            base.filter(Message.id < before_id)
            .order_by(desc(Message.id))
            .limit(lim)
            .all()
        )
        rows = list(reversed(rows_desc))
        min_id = rows[0].id if rows else before_id
        older = (
            db.query(Message.id)
            .filter(Message.conversation_id == conversation.id, Message.id < min_id)
            .first()
        )
        has_more = older is not None
    else:
        rows_desc = base.order_by(desc(Message.id)).limit(lim).all()
        rows = list(reversed(rows_desc))
        min_id = rows[0].id if rows else None
        has_more = False
        if min_id is not None:
            older = (
                db.query(Message.id)
                .filter(Message.conversation_id == conversation.id, Message.id < min_id)
                .first()
            )
            has_more = older is not None

    viewer_id = current_user.id if current_user else None
    payload = _serialize_inbox_messages(db, rows, conversation, viewer_id)
    return {
        "conversation": {
            "id": conversation.id,
            "tenant_id": conversation.tenant_id,
            "store_id": conversation.store_id,
            "customer_id": conversation.customer_id,
            "agent_id": conversation.agent_id,
            "channel": conversation.channel,
            "status": conversation.status,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "internal_note": (
                (conversation.conversation_metadata or {}).get("internal_note")
                if isinstance(conversation.conversation_metadata, dict)
                else None
            ),
        },
        "messages": payload,
        "has_more_older": has_more,
    }


@router.post(
    "/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new conversation, optionally with an initial message.
    """
    # Ensure customer exists in DB
    customer: Customer | None = (
        db.query(Customer)
        .filter(
            Customer.id == payload.customer_id,
            Customer.tenant_id == payload.tenant_id,
        )
        .first()
    )
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer not found for tenant",
        )

    conversation = Conversation(
        tenant_id=payload.tenant_id,
        store_id=payload.store_id,
        customer_id=payload.customer_id,
        channel=payload.channel,
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(conversation)
    db.flush()  # get conversation.id before creating message

    if payload.initial_message:
        initial_msg = Message(
            conversation_id=conversation.id,
            content=payload.initial_message,
            sender_type=payload.sender_type or "customer",
            sender_id=None,
            created_at=datetime.utcnow(),
        )
        db.add(initial_msg)

    db.commit()
    db.refresh(conversation)

    # Load relationships for summary
    _ = conversation.customer
    _ = conversation.messages

    return _build_conversation_summary(conversation)


@router.get("/conversations/{conversation_id}/internal-note")
async def get_conversation_internal_note(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    conversation: Conversation | None = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    if current_user is not None and current_user.tenant_id != conversation.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    meta = conversation.conversation_metadata if isinstance(conversation.conversation_metadata, dict) else {}
    note = meta.get("internal_note") if isinstance(meta.get("internal_note"), str) else ""
    return {"conversation_id": conversation.id, "note": note}


@router.patch("/conversations/{conversation_id}/internal-note")
async def set_conversation_internal_note(
    conversation_id: int,
    payload: ConversationInternalNoteIn,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    conversation: Conversation | None = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    if current_user is not None and current_user.tenant_id != conversation.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    meta = conversation.conversation_metadata if isinstance(conversation.conversation_metadata, dict) else {}
    note = (payload.note or "").strip()
    if note:
        meta["internal_note"] = note
    else:
        meta.pop("internal_note", None)
    conversation.conversation_metadata = meta
    conversation.updated_at = datetime.utcnow()
    db.add(conversation)
    db.commit()
    return {"conversation_id": conversation.id, "note": note}


@router.post("/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Persist a message in a conversation.
    Frontend uses this for agent messages; AI and customer messages are persisted via ingestion pipelines.
    """
    conversation: Conversation | None = (
        db.query(Conversation)
        .filter(Conversation.id == message.conversation_id)
        .first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    if (
        message.sender_type == "agent"
        and str(conversation.status or "").lower() in {"closed", "resolved"}
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation is closed. Reopen it before sending messages.",
        )

    sender_id: Optional[int] = None
    meta_to_store: Optional[Dict[str, Any]] = None
    if message.message_metadata and isinstance(message.message_metadata, dict):
        meta_to_store = {k: v for k, v in message.message_metadata.items() if k != "media_url"}

    content_stripped = (message.content or "").strip()
    if message.sender_type == "agent":
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        agent = (
            db.query(Agent)
            .filter(Agent.user_id == current_user.id, Agent.tenant_id == conversation.tenant_id)
            .first()
        )
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not an agent",
            )
        if conversation.agent_id != agent.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not assigned to this conversation",
            )
        sender_id = agent.id
    else:
        sender_id = None

    has_media = bool(meta_to_store and meta_to_store.get("object_key"))
    if not content_stripped and not has_media:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content or media (object_key) is required",
        )

    mt = meta_to_store.get("type") if meta_to_store else None
    if message.sender_type == "agent" and mt == "voice":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent-to-customer voice notes are disabled",
        )
    if not content_stripped and has_media:
        if mt == "image":
            content_stripped = "Image"
        elif mt == "voice":
            content_stripped = "Voice message"
        elif mt == "file":
            content_stripped = (meta_to_store.get("filename") if meta_to_store else None) or "Attachment"
        else:
            content_stripped = "Attachment"

    msg = Message(
        conversation_id=message.conversation_id,
        content=content_stripped,
        sender_type=message.sender_type,
        sender_id=sender_id,
        created_at=datetime.utcnow(),
        reply_to_message_id=message.reply_to_message_id,
        message_metadata=meta_to_store,
    )
    conversation.updated_at = datetime.utcnow()

    db.add(msg)
    db.add(conversation)
    db.commit()
    db.refresh(msg)

    if msg.sender_type == "customer":
        ensure_receipt_for_customer_message(db, msg)
        db.commit()

    if conversation.agent_id is not None:
        await push_unread_summary(db, conversation.tenant_id, conversation.agent_id)

    if msg.sender_type == "agent" and (conversation.channel or "").lower() == "whatsapp":
        customer = (
            db.query(Customer).filter(Customer.id == conversation.customer_id).first()
        )
        phone = customer.phone if customer else None
        wa = MetaWhatsAppClient()
        if phone and wa.is_configured():
            try:
                if has_media and meta_to_store and meta_to_store.get("type") == "image":
                    meta_api = enrich_metadata_for_api(meta_to_store) or {}
                    image_url = str(meta_api.get("media_url") or "").strip()
                    caption = "" if content_stripped == "Image" else content_stripped
                    if image_url:
                        wa_resp = await wa.send_image_message(
                            to_phone=str(phone),
                            image_url=image_url,
                            caption=caption,
                        )
                        msgs = wa_resp.get("messages") if isinstance(wa_resp, dict) else None
                        if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
                            out_wa_id = str(msgs[0].get("id") or "").strip()
                            if out_wa_id:
                                meta_next = dict(msg.message_metadata) if isinstance(msg.message_metadata, dict) else {}
                                meta_next["wa_message_id"] = out_wa_id
                                msg.message_metadata = meta_next
                    else:
                        line = caption or "[Image]"
                        wa_resp = await wa.send_text_message(to_phone=str(phone), text=line[:4096])
                        msgs = wa_resp.get("messages") if isinstance(wa_resp, dict) else None
                        if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
                            out_wa_id = str(msgs[0].get("id") or "").strip()
                            if out_wa_id:
                                meta_next = dict(msg.message_metadata) if isinstance(msg.message_metadata, dict) else {}
                                meta_next["wa_message_id"] = out_wa_id
                                msg.message_metadata = meta_next
                else:
                    line = content_stripped
                    if has_media:
                        if meta_to_store and meta_to_store.get("type") == "voice":
                            meta_api = enrich_metadata_for_api(meta_to_store) or {}
                            audio_url = str(meta_api.get("media_url") or "").strip()
                            if audio_url:
                                wa_resp = await wa.send_audio_message(
                                    to_phone=str(phone),
                                    audio_url=audio_url,
                                    mime_type=str(meta_to_store.get("mime_type") or ""),
                                )
                                msgs = wa_resp.get("messages") if isinstance(wa_resp, dict) else None
                                if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
                                    out_wa_id = str(msgs[0].get("id") or "").strip()
                                    if out_wa_id:
                                        meta_next = dict(msg.message_metadata) if isinstance(msg.message_metadata, dict) else {}
                                        meta_next["wa_message_id"] = out_wa_id
                                        msg.message_metadata = meta_next
                                msg.wa_delivered_at = datetime.utcnow()
                                db.add(msg)
                                db.commit()
                                db.refresh(msg)
                                if conversation.agent_id:
                                    await push_inbox_sync_event(
                                        db,
                                        conversation.tenant_id,
                                        conversation.agent_id,
                                        {
                                            "type": "inbox_message_updated",
                                            "conversation_id": conversation.id,
                                            "message": _message_dict_for_ws(db, msg),
                                        },
                                    )
                                return MessageOut(
                                    id=msg.id,
                                    conversation_id=msg.conversation_id,
                                    content=msg.content,
                                    sender_type=msg.sender_type,
                                    sender_id=msg.sender_id,
                                    language=msg.language,
                                    created_at=msg.created_at,
                                    reply_to_message_id=msg.reply_to_message_id,
                                    edited_at=msg.edited_at,
                                    message_metadata=enrich_metadata_for_api(msg.message_metadata),
                                    status={
                                        "sent": True,
                                        "delivered": bool(msg.wa_delivered_at),
                                        "read": bool(msg.wa_delivered_at),
                                    },
                                )
                            line = content_stripped if content_stripped != "Voice message" else "Voice message"
                        elif meta_to_store and meta_to_store.get("type") == "file":
                            line = content_stripped
                    wa_resp = await wa.send_text_message(to_phone=str(phone), text=line[:4096])
                    msgs = wa_resp.get("messages") if isinstance(wa_resp, dict) else None
                    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
                        out_wa_id = str(msgs[0].get("id") or "").strip()
                        if out_wa_id:
                            meta_next = dict(msg.message_metadata) if isinstance(msg.message_metadata, dict) else {}
                            meta_next["wa_message_id"] = out_wa_id
                            msg.message_metadata = meta_next
                msg.wa_delivered_at = datetime.utcnow()
                db.add(msg)
                db.commit()
                db.refresh(msg)
                if conversation.agent_id:
                    await push_inbox_sync_event(
                        db,
                        conversation.tenant_id,
                        conversation.agent_id,
                        {
                            "type": "inbox_message_updated",
                            "conversation_id": conversation.id,
                            "message": _message_dict_for_ws(db, msg),
                        },
                    )
            except Exception:
                logger.exception(
                    "WhatsApp outbound (agent) failed conversation_id=%s",
                    conversation.id,
                )

    return MessageOut(
        id=msg.id,
        conversation_id=msg.conversation_id,
        content=msg.content,
        sender_type=msg.sender_type,
        sender_id=msg.sender_id,
        language=msg.language,
        created_at=msg.created_at,
        reply_to_message_id=msg.reply_to_message_id,
        edited_at=msg.edited_at,
        message_metadata=enrich_metadata_for_api(msg.message_metadata),
        status={
            "sent": True,
            "delivered": bool(msg.wa_delivered_at) if msg.sender_type in ("agent", "ai") else False,
            # Meta "read" webhook is not yet mapped in DB; treat delivered as read fallback for outbound UI.
            "read": bool(msg.wa_delivered_at) if msg.sender_type in ("agent", "ai") else False,
        },
    )


@router.patch("/conversations/{conversation_id}/status", response_model=ConversationSummary)
async def update_conversation_status(
    conversation_id: int,
    payload: ConversationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Update conversation status (active/closed/escalated).
    When the assigned agent closes the chat on WhatsApp, sends the customer a WhatsApp line
    that Arabia Dropbot will continue (requires Bearer token so we know it was the assignee).
    """
    conversation: Conversation | None = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    old_status = (conversation.status or "").lower()
    new_status = (payload.status or "").lower()
    is_closing = new_status in ("closed", "resolved") and old_status not in (
        "closed",
        "resolved",
    )
    assigned_agent_id_before = conversation.agent_id

    is_assigned_agent_closer = False
    if current_user is not None and assigned_agent_id_before is not None:
        if (current_user.role or "").lower() == "agent":
            ag = (
                db.query(Agent)
                .filter(
                    Agent.user_id == current_user.id,
                    Agent.tenant_id == conversation.tenant_id,
                )
                .first()
            )
            if ag is not None and int(ag.id) == int(assigned_agent_id_before):
                is_assigned_agent_closer = True

    conversation.status = payload.status
    conversation.updated_at = datetime.utcnow()
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    _ = conversation.customer
    _ = conversation.messages
    if conversation.agent_id is not None:
        try:
            await push_inbox_sync_event(
                db,
                conversation.tenant_id,
                conversation.agent_id,
                {
                    "type": "inbox_conversation_refresh",
                    "conversation_id": conversation.id,
                    "reason": "conversation_status_updated",
                },
            )
        except Exception:
            logger.exception(
                "status patch: inbox refresh broadcast failed (conversation_id=%s)",
                conversation.id,
            )

    if (
        is_closing
        and is_assigned_agent_closer
        and assigned_agent_id_before is not None
        and (conversation.channel or "").lower() == "whatsapp"
    ):
        customer = db.query(Customer).filter(Customer.id == conversation.customer_id).first()
        phone = customer.phone if customer else None
        wa = MetaWhatsAppClient()
        body_text = (
            "The agent has closed this chat. Arabia Dropbot will continue helping you from here."
        )
        if phone and wa.is_configured():
            try:
                wa_resp = await wa.send_text_message(to_phone=str(phone), text=body_text)
                out_row = Message(
                    conversation_id=conversation.id,
                    content=body_text,
                    sender_type="ai",
                    sender_id=None,
                    created_at=datetime.utcnow(),
                )
                msgs = wa_resp.get("messages") if isinstance(wa_resp, dict) else None
                if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
                    out_wa_id = str(msgs[0].get("id") or "").strip()
                    if out_wa_id:
                        out_row.message_metadata = {"wa_message_id": out_wa_id}
                out_row.wa_delivered_at = datetime.utcnow()
                db.add(out_row)
                conversation.updated_at = datetime.utcnow()
                db.add(conversation)
                db.commit()
                db.refresh(out_row)
                db.refresh(conversation)
                if conversation.agent_id is not None:
                    try:
                        await push_inbox_message(
                            db,
                            conversation.tenant_id,
                            conversation.agent_id,
                            conversation.id,
                            _message_dict_for_ws(db, out_row),
                        )
                    except Exception:
                        logger.exception(
                            "status patch: push close-notify message failed (conversation_id=%s)",
                            conversation.id,
                        )
            except Exception:
                logger.exception(
                    "WhatsApp agent-close notify failed (conversation_id=%s)",
                    conversation.id,
                )

    return _build_conversation_summary(conversation)


@router.post("/conversations/{conversation_id}/send-to-ai", response_model=ConversationSummary)
async def send_conversation_to_ai(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Return ownership of a conversation to AI by clearing assigned agent.
    """
    conversation: Conversation | None = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    transfer_by_name = "Agent"
    if current_user is not None:
        ag = (
            db.query(Agent)
            .filter(Agent.user_id == current_user.id, Agent.tenant_id == conversation.tenant_id)
            .first()
        )
        if ag is not None:
            an = lookup_agent_display_name(db, ag.id)
            if an:
                transfer_by_name = an

    handoff_note = f"{transfer_by_name} transferred this chat to Arabia Dropbot."
    dropbot_greeting = "How may I help further?"

    handoff_msg = Message(
        conversation_id=conversation.id,
        content=handoff_note,
        sender_type="ai",
        sender_id=None,
        created_at=datetime.utcnow(),
    )
    greeting_msg = Message(
        conversation_id=conversation.id,
        content=dropbot_greeting,
        sender_type="ai",
        sender_id=None,
        created_at=datetime.utcnow(),
    )
    db.add(handoff_msg)
    db.add(greeting_msg)

    # Preserve the last handler info in metadata before clearing agent_id,
    # so the admin panel can still show who handled this conversation.
    released_from_agent_id: Optional[int] = None
    if conversation.agent_id is not None:
        released_from_agent_id = conversation.agent_id
        prev_agent = db.query(Agent).filter(Agent.id == conversation.agent_id).first()
        meta = conversation.conversation_metadata if isinstance(conversation.conversation_metadata, dict) else {}
        prev_label = (
            lookup_agent_display_name(db, prev_agent.id)
            if prev_agent
            else None
        ) or transfer_by_name
        meta["last_handler"] = {
            "agent_id": conversation.agent_id,
            "agent_name": prev_label,
            "at": datetime.utcnow().isoformat(),
        }
        # Flag so downstream routing (_get_previous_agent_for_customer) and
        # audits can recognise this was an explicit "send back to bot" action.
        meta["released_to_ai_at"] = datetime.utcnow().isoformat()
        conversation.conversation_metadata = meta

    conversation.agent_id = None
    # Back on the bot: must be active so admin "AI Bot" bucket shows this thread
    # (not "Closed"). Closed is only after an agent resolves the chat.
    conversation.status = "active"
    conversation.updated_at = datetime.utcnow()
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    # Tell the previous agent (and any other tab viewing this thread) to
    # refresh so the UI stops showing them as the assignee / active handler.
    if released_from_agent_id is not None:
        try:
            await push_inbox_sync_event(
                db,
                conversation.tenant_id,
                released_from_agent_id,
                {
                    "type": "inbox_conversation_refresh",
                    "conversation_id": conversation.id,
                    "reason": "released_to_ai",
                },
            )
        except Exception:
            logger.exception(
                "send-to-ai: failed to broadcast refresh (conversation_id=%s, agent_id=%s)",
                conversation.id,
                released_from_agent_id,
            )

    if (conversation.channel or "").lower() == "whatsapp":
        customer = db.query(Customer).filter(Customer.id == conversation.customer_id).first()
        phone = customer.phone if customer else None
        wa = MetaWhatsAppClient()
        if phone and wa.is_configured():
            try:
                wa_resp_1 = await wa.send_text_message(to_phone=str(phone), text=handoff_note)
                handoff_msg.wa_delivered_at = datetime.utcnow()
                msgs1 = wa_resp_1.get("messages") if isinstance(wa_resp_1, dict) else None
                if isinstance(msgs1, list) and msgs1 and isinstance(msgs1[0], dict):
                    out_wa_id_1 = str(msgs1[0].get("id") or "").strip()
                    if out_wa_id_1:
                        handoff_msg.message_metadata = {"wa_message_id": out_wa_id_1}

                wa_resp_2 = await wa.send_text_message(to_phone=str(phone), text=dropbot_greeting)
                greeting_msg.wa_delivered_at = datetime.utcnow()
                msgs2 = wa_resp_2.get("messages") if isinstance(wa_resp_2, dict) else None
                if isinstance(msgs2, list) and msgs2 and isinstance(msgs2[0], dict):
                    out_wa_id_2 = str(msgs2[0].get("id") or "").strip()
                    if out_wa_id_2:
                        greeting_msg.message_metadata = {"wa_message_id": out_wa_id_2}
                db.add(handoff_msg)
                db.add(greeting_msg)
                db.commit()
            except Exception:
                logger.exception(
                    "WhatsApp send-to-ai handoff failed (conversation_id=%s)",
                    conversation.id,
                )

    _ = conversation.customer
    _ = conversation.messages
    return _build_conversation_summary(conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_permanently(
    conversation_id: int,
    tenant_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Permanently remove a customer inbox thread (admin only): DB rows, receipts, notifications,
    read state, and R2 media keys referenced on messages.
    """
    role = (current_user.role or "").lower()
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    if int(current_user.tenant_id) != int(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")

    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    msgs = db.query(Message).filter(Message.conversation_id == conversation_id).all()
    msg_ids = [m.id for m in msgs]
    for m in msgs:
        for key in _r2_keys_from_message_metadata(m.message_metadata):
            delete_object(key)

    if msg_ids:
        db.query(InboxMessageReceipt).filter(InboxMessageReceipt.message_id.in_(msg_ids)).delete(
            synchronize_session=False
        )
        db.query(MessageUserDeletion).filter(MessageUserDeletion.message_id.in_(msg_ids)).delete(
            synchronize_session=False
        )
        db.query(Message).filter(Message.reply_to_message_id.in_(msg_ids)).update(
            {Message.reply_to_message_id: None},
            synchronize_session=False,
        )
        db.query(Message).filter(Message.conversation_id == conversation_id).delete(
            synchronize_session=False
        )

    db.query(Notification).filter(Notification.conversation_id == conversation_id).delete(
        synchronize_session=False
    )
    db.query(ConversationAgentReadState).filter(
        ConversationAgentReadState.tenant_id == tenant_id,
        ConversationAgentReadState.conversation_id == conversation_id,
    ).delete(synchronize_session=False)

    db.query(Conversation).filter(Conversation.id == conversation_id).delete(synchronize_session=False)
    db.commit()

    agent_rows = db.query(Agent.id).filter(Agent.tenant_id == tenant_id).all()
    for (aid,) in agent_rows:
        try:
            await push_inbox_sync_event(
                db,
                tenant_id,
                aid,
                {
                    "type": "conversation_deleted",
                    "conversation_id": conversation_id,
                },
            )
        except Exception:
            logger.exception(
                "conversation_deleted broadcast failed (conversation_id=%s agent_id=%s)",
                conversation_id,
                aid,
            )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/messages/{message_id}", response_model=MessageOut)
async def patch_inbox_message(
    message_id: int,
    payload: MessageEditIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = db.query(Message).filter(Message.id == message_id).first()
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    conv = db.query(Conversation).filter(Conversation.id == m.conversation_id).first()
    if not conv or conv.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if m.deleted_for_everyone_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message was deleted")
    text = (payload.content or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Content required")
    role = (current_user.role or "").lower()
    ag = (
        db.query(Agent)
        .filter(Agent.user_id == current_user.id, Agent.tenant_id == conv.tenant_id)
        .first()
    )
    allowed = role == "admin" or (
        ag is not None and m.sender_type == "agent" and m.sender_id == ag.id
    )
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit this message")
    m.content = text
    m.edited_at = datetime.utcnow()
    db.add(m)
    db.commit()
    db.refresh(m)
    if conv.agent_id:
        rec = get_receipt_map(db, [m.id], conv.agent_id).get(m.id)
        reply_row = None
        if m.reply_to_message_id:
            reply_row = db.query(Message).filter(Message.id == m.reply_to_message_id).first()
        msg_dict = _inbox_message_api_dict(m, conv, rec, reply_row)
        await push_inbox_sync_event(
            db,
            conv.tenant_id,
            conv.agent_id,
            {"type": "inbox_message_updated", "conversation_id": conv.id, "message": msg_dict},
        )
    return MessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        content=m.content,
        sender_type=m.sender_type,
        sender_id=m.sender_id,
        language=m.language,
        created_at=m.created_at,
        reply_to_message_id=m.reply_to_message_id,
        edited_at=m.edited_at,
        message_metadata=enrich_metadata_for_api(m.message_metadata),
    )


@router.post("/messages/{message_id}/reaction", response_model=MessageOut)
async def set_inbox_message_reaction(
    message_id: int,
    payload: MessageReactionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = db.query(Message).filter(Message.id == message_id).first()
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    conv = db.query(Conversation).filter(Conversation.id == m.conversation_id).first()
    if not conv or conv.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if m.deleted_for_everyone_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message was deleted")
    agent = (
        db.query(Agent)
        .filter(Agent.user_id == current_user.id, Agent.tenant_id == conv.tenant_id)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an agent")
    emoji = (payload.emoji or "").strip()
    m.message_metadata = _upsert_message_reaction(
        m.message_metadata,
        user_id=str(agent.id),
        user_name=(lookup_agent_display_name(db, agent.id) or "Agent"),
        emoji=emoji,
    )
    db.add(m)
    db.commit()
    db.refresh(m)

    if (conv.channel or "").lower() == "whatsapp":
        customer = db.query(Customer).filter(Customer.id == conv.customer_id).first()
        phone = customer.phone if customer else None
        wa = MetaWhatsAppClient()
        target_wa_message_id = None
        if isinstance(m.message_metadata, dict):
            raw_id = m.message_metadata.get("wa_message_id")
            if isinstance(raw_id, str):
                target_wa_message_id = raw_id.strip()
        if phone and target_wa_message_id and wa.is_configured():
            try:
                await wa.send_reaction_message(
                    to_phone=str(phone),
                    target_message_id=target_wa_message_id,
                    emoji=emoji,
                )
            except Exception:
                logger.exception(
                    "WhatsApp reaction send failed conversation_id=%s message_id=%s",
                    conv.id,
                    m.id,
                )

    if conv.agent_id:
        await push_inbox_sync_event(
            db,
            conv.tenant_id,
            conv.agent_id,
            {
                "type": "inbox_message_updated",
                "conversation_id": conv.id,
                "message": _message_dict_for_ws(db, m),
            },
        )
    return MessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        content=m.content,
        sender_type=m.sender_type,
        sender_id=m.sender_id,
        language=m.language,
        created_at=m.created_at,
        reply_to_message_id=m.reply_to_message_id,
        edited_at=m.edited_at,
        message_metadata=enrich_metadata_for_api(m.message_metadata),
    )


@router.delete("/messages/{message_id}/for-me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inbox_for_me(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = db.query(Message).filter(Message.id == message_id).first()
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    conv = db.query(Conversation).filter(Conversation.id == m.conversation_id).first()
    if not conv or conv.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    exists = (
        db.query(MessageUserDeletion)
        .filter(
            MessageUserDeletion.message_id == message_id,
            MessageUserDeletion.user_id == current_user.id,
            MessageUserDeletion.channel == "inbox",
        )
        .first()
    )
    if not exists:
        db.add(
            MessageUserDeletion(
                channel="inbox",
                message_id=message_id,
                user_id=current_user.id,
                deleted_by_role=(current_user.role or "").lower(),
            )
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/messages/{message_id}/for-everyone", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inbox_for_everyone(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = db.query(Message).filter(Message.id == message_id).first()
    if not m:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    conv = db.query(Conversation).filter(Conversation.id == m.conversation_id).first()
    if not conv or conv.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if m.deleted_for_everyone_at:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    role = (current_user.role or "").lower()
    ag = (
        db.query(Agent)
        .filter(Agent.user_id == current_user.id, Agent.tenant_id == conv.tenant_id)
        .first()
    )
    allowed = False
    if role == "admin":
        allowed = True
    elif ag and m.sender_type == "agent" and m.sender_id == ag.id:
        if (datetime.utcnow() - m.created_at).total_seconds() <= 300:
            allowed = True
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete this message for everyone"
        )
    prev_meta = m.message_metadata or {}
    ok = prev_meta.get("object_key")
    if isinstance(ok, str) and ok:
        delete_object(ok)
    prev = m.content or ""
    meta = dict(prev_meta)
    meta["deleted_original_content"] = prev
    m.message_metadata = meta
    m.content = "[Message deleted]"
    m.deleted_for_everyone_at = datetime.utcnow()
    db.add(m)
    db.commit()
    if conv.agent_id:
        await push_inbox_sync_event(
            db,
            conv.tenant_id,
            conv.agent_id,
            {
                "type": "MESSAGE_DELETED",
                "conversation_id": conv.id,
                "message_id": m.id,
            },
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/whatsapp/webhook")
async def whatsapp_webhook_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Meta Cloud API webhook verification.
    """
    expected = settings.meta_whatsapp_verify_token
    if hub_mode == "subscribe" and expected and hub_verify_token == expected:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Meta Cloud API webhook receiver:
    - parse inbound text message
    - persist inbound message to conversation
    - generate AI reply with LangChain bot
    - send outbound reply via Meta Cloud API
    - persist outbound AI reply
    """
    body = await request.json()
    inbound = _parse_meta_whatsapp_inbound(body)
    if not inbound:
        # Non-message webhooks (delivery/read/status) are valid and should ACK.
        return {"status": "ignored"}

    from_phone = inbound["from_phone"]
    if not from_phone:
        return {"status": "ignored"}

    # Reject stale webhook retries (Meta retries failed webhooks for hours).
    # Messages older than 2 minutes are almost certainly retries from a prior crash.
    _wa_ts = inbound.get("timestamp")
    if _wa_ts is not None:
        try:
            age_seconds = time.time() - int(_wa_ts)
            if age_seconds > 120:
                logger.info(
                    "WhatsApp webhook stale (%.0fs old, wa_id=%s) — ignoring",
                    age_seconds,
                    inbound.get("wa_message_id", "?"),
                )
                return {"status": "ignored", "reason": "stale_webhook"}
        except (ValueError, TypeError):
            pass

    if inbound.get("kind") == "reaction":
        tenant_id = 1
        store = _get_or_create_default_store(db, tenant_id=tenant_id)
        customer = _get_or_create_customer_by_phone(
            db,
            tenant_id=tenant_id,
            store_id=store.id,
            phone=from_phone,
            name=inbound.get("contact_name"),
        )
        conversation = _get_or_create_active_whatsapp_conversation(
            db,
            tenant_id=tenant_id,
            store_id=store.id,
            customer_id=customer.id,
        )
        target_wa_message_id = str(inbound.get("target_wa_message_id") or "").strip()
        if not target_wa_message_id:
            return {"status": "ignored"}
        rows = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(desc(Message.created_at))
            .all()
        )
        target_msg = None
        for row in rows:
            meta = row.message_metadata if isinstance(row.message_metadata, dict) else {}
            if str(meta.get("wa_message_id") or "").strip() == target_wa_message_id:
                target_msg = row
                break
        if not target_msg:
            return {"status": "ok", "conversation_id": conversation.id, "ignored": "target_not_found"}
        customer_label = customer.name or "Customer"
        target_msg.message_metadata = _upsert_message_reaction(
            target_msg.message_metadata,
            user_id=f"wa:{from_phone}",
            user_name=customer_label,
            emoji=str(inbound.get("emoji") or "").strip(),
        )
        db.add(target_msg)
        db.commit()
        db.refresh(target_msg)
        if conversation.agent_id:
            await push_inbox_sync_event(
                db,
                tenant_id,
                conversation.agent_id,
                {
                    "type": "inbox_message_updated",
                    "conversation_id": conversation.id,
                    "message": _message_dict_for_ws(db, target_msg),
                },
            )
        return {"status": "ok", "conversation_id": conversation.id, "kind": "reaction"}

    msg_meta: Optional[Dict[str, Any]] = None
    kind = inbound.get("kind")
    if kind == "text":
        text = inbound.get("text") or ""
        if not str(text).strip():
            return {"status": "ignored"}
    elif kind == "image":
        text = (inbound.get("caption") or "").strip() or "Image"
        try:
            wa_dl = MetaWhatsAppClient()
            if wa_dl.is_configured():
                raw, mime = await wa_dl.download_media(inbound["media_id"])
                msg_meta = store_inbound_whatsapp_media(raw, "image", mime)
        except Exception:
            logger.exception("Inbound WhatsApp image download/R2 failed")
    elif kind == "audio":
        text = "Voice message"
        try:
            wa_dl = MetaWhatsAppClient()
            if wa_dl.is_configured():
                raw, mime = await wa_dl.download_media(inbound["media_id"])
                msg_meta = store_inbound_whatsapp_media(raw, "audio", mime)
                if isinstance(msg_meta, dict):
                    d = inbound.get("duration_seconds")
                    if isinstance(d, int) and d > 0:
                        msg_meta["duration_seconds"] = d
        except Exception:
            logger.exception("Inbound WhatsApp audio download/R2 failed")
    elif kind == "document":
        text = (inbound.get("filename") or "File").strip() or "File"
        try:
            wa_dl = MetaWhatsAppClient()
            if wa_dl.is_configured():
                raw, mime = await wa_dl.download_media(inbound["media_id"])
                msg_meta = store_inbound_whatsapp_media(raw, "audio", mime)
                if isinstance(msg_meta, dict):
                    msg_meta["type"] = "file"
                    msg_meta["filename"] = str(inbound.get("filename") or "File")
        except Exception:
            logger.exception("Inbound WhatsApp document download/R2 failed")
    else:
        return {"status": "ignored"}
    wa_message_id = str(inbound.get("wa_message_id") or "").strip()
    if wa_message_id:
        base_meta = dict(msg_meta) if isinstance(msg_meta, dict) else {}
        base_meta["wa_message_id"] = wa_message_id
        msg_meta = base_meta

    tenant_id = 1
    store = _get_or_create_default_store(db, tenant_id=tenant_id)
    customer = _get_or_create_customer_by_phone(
        db,
        tenant_id=tenant_id,
        store_id=store.id,
        phone=from_phone,
        name=inbound.get("contact_name"),
    )
    conversation = _get_or_create_active_whatsapp_conversation(
        db,
        tenant_id=tenant_id,
        store_id=store.id,
        customer_id=customer.id,
    )

    if wa_message_id and _already_processed_wa_message(db, wa_message_id):
        return {
            "status": "ignored",
            "conversation_id": conversation.id,
            "reason": "duplicate_wa_message_id",
        }

    orchestrator = AIOrchestrator()
    bot = ArabiaLangChainBot(db=db)

    if conversation.agent_id:
        detected_language = await orchestrator.detect_language(text)
        if is_slash_reset_command(text):
            release_agent_and_clear_bot_flow(conversation)
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
        else:
            customer_msg = Message(
                conversation_id=conversation.id,
                content=text,
                sender_type="customer",
                sender_id=None,
                language=detected_language,
                created_at=datetime.utcnow(),
                message_metadata=msg_meta,
            )
            db.add(customer_msg)
            conversation.updated_at = datetime.utcnow()
            db.add(conversation)
            db.commit()
            db.refresh(customer_msg)
            ensure_receipt_for_customer_message(db, customer_msg)
            db.commit()
            await push_inbox_message(
                db,
                tenant_id,
                conversation.agent_id,
                conversation.id,
                _message_dict_for_ws(db, customer_msg),
            )
            return {
                "status": "ok",
                "conversation_id": conversation.id,
                "skipped": "human_agent",
                "reply_text": "",
                "language": detected_language,
                "escalate": False,
                "meta_response": None,
            }

    if kind in {"image", "audio", "document"}:
        detected_language = await orchestrator.detect_language(text)
        unsupported_text = (
            "I can only handle text messages right now. "
            "For images, files, or voice notes, please talk to support by choosing option 3."
        )
        customer_msg = Message(
            conversation_id=conversation.id,
            content=text,
            sender_type="customer",
            sender_id=None,
            language=detected_language,
            created_at=datetime.utcnow(),
            message_metadata=msg_meta,
        )
        ai_msg = Message(
            conversation_id=conversation.id,
            content=unsupported_text,
            sender_type="ai",
            sender_id=None,
            language=detected_language,
            created_at=datetime.utcnow(),
        )
        db.add(customer_msg)
        db.add(ai_msg)
        conversation.updated_at = datetime.utcnow()
        db.add(conversation)
        db.commit()
        db.refresh(customer_msg)
        db.refresh(ai_msg)
        ensure_receipt_for_customer_message(db, customer_msg)
        db.commit()
        if conversation.agent_id:
            await push_inbox_message(
                db,
                tenant_id,
                conversation.agent_id,
                conversation.id,
                _message_dict_for_ws(db, customer_msg),
            )
        wa_response: Dict[str, Any] | None = None
        client = MetaWhatsAppClient()
        if client.is_configured():
            try:
                wa_response = await client.send_text_message(to_phone=from_phone, text=unsupported_text)
                ai_msg.wa_delivered_at = datetime.utcnow()
                db.add(ai_msg)
                db.commit()
                db.refresh(ai_msg)
            except Exception:
                logger.exception("WhatsApp unsupported-media reply failed (conversation_id=%s)", conversation.id)
                wa_response = {"error": "meta_send_failed"}
        else:
            wa_response = {"error": "meta_not_configured"}
        return {
            "status": "ok",
            "conversation_id": conversation.id,
            "reply_text": unsupported_text,
            "language": detected_language,
            "escalate": False,
            "meta_response": wa_response,
        }

    # Early-commit customer message to close webhook dedup race window.
    # Without this, Meta retries that arrive during LLM processing pass the
    # _already_processed_wa_message check and generate duplicate replies.
    customer_msg = Message(
        conversation_id=conversation.id,
        content=text,
        sender_type="customer",
        sender_id=None,
        language="english",
        created_at=datetime.utcnow(),
        message_metadata=msg_meta,
    )
    db.add(customer_msg)
    db.commit()
    db.refresh(customer_msg)

    flow = await process_customer_bot_message(
        db=db,
        conversation=conversation,
        user_message=text,
        tenant_id=tenant_id,
        orchestrator=orchestrator,
        phone=from_phone,
        channel="whatsapp",
    )

    if flow.merge_metadata:
        conversation.conversation_metadata = flow.merge_metadata

    detected_language = await orchestrator.detect_language(text)
    bf_lang = (flow.merge_metadata.get("bot_flow") or {}).get("lang")
    if isinstance(bf_lang, str) and bf_lang.strip():
        detected_language = bf_lang
    customer_msg.language = detected_language

    mem_id = normalize_memory_scope_id(from_phone, conversation)
    memory_block = (
        format_memory_block_for_prompt(ConversationMemory.get_all_context(mem_id))
        if mem_id
        else None
    )

    if not flow.handled:
        flow_state = flow.merge_metadata.get("bot_flow") if isinstance(flow.merge_metadata, dict) else None
        customer_context = await orchestrator.fetch_customer_context(
            phone=from_phone,
            message_text=text,
            bot_flow=flow_state,
        )
        recent_orders = customer_context.get("recent_orders") or []
        customer_ctx = customer_context.get("customer") or {}
        _meta = (
            conversation.conversation_metadata
            if isinstance(conversation.conversation_metadata, dict)
            else {}
        )
        _recent_hint = format_recent_context_hint_for_prompt(_meta)
        reply_text = await bot.generate_reply(
            tenant_id=tenant_id,
            user_message=text,
            channel="whatsapp",
            language=detected_language,
            customer_context=customer_ctx,
            recent_orders=recent_orders,
            fetch_context=customer_context,
            bot_flow=flow_state,
            conversation_id=conversation.id,
            exclude_history_message_id=customer_msg.id,
            recent_context_hint=_recent_hint,
            memory_context=memory_block,
        )
        conversation.conversation_metadata = patch_conversation_metadata_with_last_topic(
            conversation.conversation_metadata,
            text,
            customer_context,
            flow_state,
        )
    elif flow.use_ai:
        flow_state = flow.merge_metadata.get("bot_flow") if isinstance(flow.merge_metadata, dict) else None
        if flow.skip_store_api:
            customer_ctx = {}
            recent_orders = []
        else:
            customer_context = await orchestrator.fetch_customer_context(
                phone=from_phone,
                message_text=text,
                bot_flow=flow_state,
            )
            recent_orders = customer_context.get("recent_orders") or []
            customer_ctx = customer_context.get("customer") or {}
        _meta2 = (
            conversation.conversation_metadata
            if isinstance(conversation.conversation_metadata, dict)
            else {}
        )
        _recent_hint2 = format_recent_context_hint_for_prompt(_meta2)
        _fc = customer_context if not flow.skip_store_api else None
        _bf = (
            flow_state
            if not flow.skip_store_api
            else (
                flow.merge_metadata.get("bot_flow")
                if isinstance(flow.merge_metadata, dict)
                else None
            )
        )
        reply_text = await bot.generate_reply(
            tenant_id=tenant_id,
            user_message=flow.ai_user_message,
            channel="whatsapp",
            language=detected_language,
            customer_context=customer_ctx,
            recent_orders=recent_orders,
            fetch_context=_fc,
            bot_flow=_bf,
            conversation_id=conversation.id,
            exclude_history_message_id=customer_msg.id,
            recent_context_hint=_recent_hint2,
            memory_context=memory_block,
        )
        conversation.conversation_metadata = patch_conversation_metadata_with_last_topic(
            conversation.conversation_metadata,
            flow.ai_user_message,
            _fc,
            _bf,
        )
        if flow.skip_store_api and bot.last_reply_used_kb:
            reply_text = format_kb_reply(bf_lang or detected_language, reply_text)
    else:
        reply_text = flow.reply_text

    if flow.assign_team:
        bf = flow.merge_metadata.get("bot_flow") or {}
        kind = bf.get("customer_kind")
        assign_result = assign_from_bot_flow(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            store_id=store.id,
            customer_id=customer.id,
            routed_team=flow.assign_team,
            is_existing_customer=(kind == "existing" or bool(bf.get("verified"))),
        )
        db.refresh(conversation)
        if assign_result.agent_id is not None and assign_result.reason != "conversation_already_assigned":
            aname = lookup_agent_display_name(db, assign_result.agent_id)
            if aname:
                reply_text = append_handoff_agent_line(
                    bf_lang or detected_language,
                    reply_text,
                    aname,
                )
            await notify_bot_handoff_assigned(
                db,
                tenant_id,
                assign_result.agent_id,
                conversation.id,
                customer.id,
                store.id,
            )
        elif assign_result.agent_id is None and assign_result.reason == "no_available_agent":
            extra = resolve_bot_template(
                bf_lang or detected_language, "handoff_unavailable"
            )
            if extra:
                schedule_line = ""
                sched = (
                    db.query(TenantSchedule)
                    .filter(TenantSchedule.tenant_id == tenant_id)
                    .first()
                )
                if sched and sched.working_days and sched.start_time and sched.end_time:
                    _lang = bf_lang or detected_language
                    schedule_line = format_tenant_schedule_line_for_handoff(
                        _lang,
                        sched.working_days,
                        sched.start_time,
                        sched.end_time,
                    )
                try:
                    extra = extra.format(schedule=schedule_line)
                except (KeyError, IndexError):
                    extra = extra.replace("{schedule}", schedule_line)
                reply_text = f"{(reply_text or '').strip()}\n\n{extra}".strip()

    if not (reply_text or "").strip():
        reply_text = resolve_bot_template(bf_lang or detected_language, "fallback")

    if mem_id and (reply_text or "").strip():
        _, _ui = IntentDetector.detect_topic_and_intent(text)
        record_conversation_turn(mem_id, text, reply_text, user_intent=_ui)

    # customer_msg was early-committed above for dedup; update final language
    customer_msg.language = detected_language
    ai_messages: list[Message] = []
    wa_images = getattr(flow, "whatsapp_image_outbound", None) or []
    if isinstance(wa_images, list):
        for item in wa_images:
            if not isinstance(item, dict):
                continue
            img_url = str(item.get("image_url") or "").strip()
            if not img_url:
                continue
            cap = str(item.get("caption") or "").strip() or "Image"
            ai_messages.append(
                Message(
                    conversation_id=conversation.id,
                    content=cap,
                    sender_type="ai",
                    sender_id=None,
                    language=detected_language,
                    created_at=datetime.utcnow(),
                    message_metadata={"type": "image", "media_url": img_url},
                )
            )
    ai_msg = Message(
        conversation_id=conversation.id,
        content=reply_text,
        sender_type="ai",
        sender_id=None,
        language=detected_language,
        created_at=datetime.utcnow(),
    )
    db.add(customer_msg)
    for m in ai_messages:
        db.add(m)
    db.add(ai_msg)
    conversation.updated_at = datetime.utcnow()
    db.add(conversation)
    db.commit()
    db.refresh(customer_msg)
    for m in ai_messages:
        db.refresh(m)
    db.refresh(ai_msg)
    ensure_receipt_for_customer_message(db, customer_msg)
    db.commit()

    if conversation.agent_id:
        await push_inbox_message(
            db,
            tenant_id,
            conversation.agent_id,
            conversation.id,
            _message_dict_for_ws(db, customer_msg),
        )
        await push_inbox_message(
            db,
            tenant_id,
            conversation.agent_id,
            conversation.id,
            _message_dict_for_ws(db, ai_msg),
        )
        for m in ai_messages:
            await push_inbox_message(
                db,
                tenant_id,
                conversation.agent_id,
                conversation.id,
                _message_dict_for_ws(db, m),
            )

    wa_response: Dict[str, Any] | None = None
    client = MetaWhatsAppClient()
    wa_images = getattr(flow, "whatsapp_image_outbound", None) or []
    _wa_tail_raw = getattr(flow, "whatsapp_text_after_images", None)
    wa_tail_parts: List[str] = []
    if isinstance(_wa_tail_raw, list):
        for _p in _wa_tail_raw:
            s = str(_p or "").strip()
            if s:
                wa_tail_parts.append(s)
    elif _wa_tail_raw:
        s = str(_wa_tail_raw).strip()
        if s:
            wa_tail_parts.append(s)

    if reply_text or wa_images:
        if not client.is_configured():
            logger.warning(
                "WhatsApp reply not sent: Meta Cloud API env missing. "
                "Set META_WHATSAPP_ACCESS_TOKEN and META_WHATSAPP_PHONE_NUMBER_ID on the host."
            )
            wa_response = {"error": "meta_not_configured"}
        else:
            try:
                wa_response = None
                if isinstance(wa_images, list) and wa_images:
                    # --- Phase 1: POST every image, wait for each to be ACKed
                    # by Meta before moving on. Sequential awaits make our
                    # outbound order deterministic; a tiny yield between
                    # sends keeps the gallery visually tidy on the client.
                    image_sends_attempted = 0
                    image_sends_succeeded = 0
                    for idx, item in enumerate(wa_images):
                        if not isinstance(item, dict):
                            continue
                        img_url = str(item.get("image_url") or "").strip()
                        if not img_url:
                            continue
                        cap = str(item.get("caption") or "").strip() or None
                        if idx > 0:
                            try:
                                await asyncio.sleep(0.15)
                            except Exception:
                                pass
                        image_sends_attempted += 1
                        try:
                            wa_response = await client.send_image_message(
                                to_phone=from_phone,
                                image_url=img_url,
                                caption=cap,
                            )
                            image_sends_succeeded += 1
                        except Exception:
                            logger.exception(
                                "WhatsApp send_image_message failed (conversation_id=%s) url=%s",
                                conversation.id,
                                img_url[:160],
                            )
                            wa_response = {"error": "meta_image_send_failed"}
                    # --- Phase 2: trailing text. Only fires after every
                    # image POST above has been awaited. We add a short
                    # breathing room before the FIRST text so Meta has time
                    # to finalise delivery of the last image bubble — this
                    # prevents the text from racing ahead of the last image
                    # on the recipient's phone.
                    logger.info(
                        "WhatsApp bot reply: conversation_id=%s images_sent=%d/%d tail_parts=%d",
                        conversation.id,
                        image_sends_succeeded,
                        image_sends_attempted,
                        len(wa_tail_parts),
                    )
                    if image_sends_succeeded and wa_tail_parts:
                        try:
                            await asyncio.sleep(0.5)
                        except Exception:
                            pass
                    for _pi, _part in enumerate(wa_tail_parts):
                        if _pi > 0:
                            try:
                                await asyncio.sleep(0.1)
                            except Exception:
                                pass
                        wa_response = await client.send_text_message(
                            to_phone=from_phone, text=_part[:4096]
                        )
                elif (reply_text or "").strip():
                    wa_response = await client.send_text_message(to_phone=from_phone, text=reply_text)
                if wa_response is None and (reply_text or "").strip():
                    wa_response = await client.send_text_message(to_phone=from_phone, text=reply_text)
                logger.info(
                    "WhatsApp outbound sent to=%s conversation_id=%s",
                    from_phone[-6:] if from_phone else "?",
                    conversation.id,
                )
                ai_msg.wa_delivered_at = datetime.utcnow()
                msgs = (
                    wa_response.get("messages")
                    if isinstance(wa_response, dict)
                    else None
                )
                if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
                    out_wa_id = str(msgs[0].get("id") or "").strip()
                    if out_wa_id:
                        ai_meta = dict(ai_msg.message_metadata) if isinstance(ai_msg.message_metadata, dict) else {}
                        ai_meta["wa_message_id"] = out_wa_id
                        ai_msg.message_metadata = ai_meta
                db.add(ai_msg)
                db.commit()
                db.refresh(ai_msg)
            except Exception:
                logger.exception(
                    "WhatsApp outbound send failed (conversation_id=%s)",
                    conversation.id,
                )
                wa_response = {"error": "meta_send_failed"}

    escalate = flow.escalate or await orchestrator.should_escalate(text)
    return {
        "status": "ok",
        "conversation_id": conversation.id,
        "reply_text": reply_text,
        "language": detected_language,
        "escalate": escalate,
        "meta_response": wa_response,
    }


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: int):
    """
    WebSocket endpoint for real-time messaging.
    For now this is a simple echo-style placeholder.
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(data)
    except Exception:
        await websocket.close()
