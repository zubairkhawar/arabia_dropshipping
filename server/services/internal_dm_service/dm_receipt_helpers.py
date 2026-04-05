"""Internal DM delivery/read receipts (dm_message_receipts)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from models import DmMessageReceipt, InternalDmConversation, InternalDmMessage


def other_participant_id(conv: InternalDmConversation, sender_agent_id: int) -> int:
    return conv.agent_two_id if conv.agent_one_id == sender_agent_id else conv.agent_one_id


def ensure_dm_message_receipt(db: Session, msg: InternalDmMessage, conversation: InternalDmConversation) -> None:
    peer = other_participant_id(conversation, msg.sender_agent_id)
    exists = (
        db.query(DmMessageReceipt)
        .filter(
            DmMessageReceipt.message_id == msg.id,
            DmMessageReceipt.recipient_agent_id == peer,
        )
        .first()
    )
    if exists is None:
        db.add(DmMessageReceipt(message_id=msg.id, recipient_agent_id=peer))
        db.commit()


def mark_dm_messages_delivered(
    db: Session,
    conversation_id: int,
    recipient_agent_id: int,
    message_ids: List[int],
) -> List[Tuple[int, int, Optional[datetime], Optional[datetime]]]:
    """Recipient marks inbound messages as delivered. Returns rows for WS broadcast."""
    now = datetime.utcnow()
    broadcast: List[Tuple[int, int, Optional[datetime], Optional[datetime]]] = []
    for mid in message_ids:
        m = (
            db.query(InternalDmMessage)
            .filter(
                InternalDmMessage.id == mid,
                InternalDmMessage.conversation_id == conversation_id,
            )
            .first()
        )
        if not m or m.sender_agent_id == recipient_agent_id:
            continue
        row = (
            db.query(DmMessageReceipt)
            .filter(
                DmMessageReceipt.message_id == mid,
                DmMessageReceipt.recipient_agent_id == recipient_agent_id,
            )
            .first()
        )
        if row is None:
            row = DmMessageReceipt(message_id=mid, recipient_agent_id=recipient_agent_id)
            db.add(row)
        changed = False
        if row.delivered_at is None:
            row.delivered_at = now
            changed = True
        if changed:
            db.add(row)
            broadcast.append((mid, recipient_agent_id, row.delivered_at, row.read_at))
    if broadcast:
        db.commit()
    return broadcast


def mark_dm_read_through_receipts(
    db: Session,
    conversation_id: int,
    reader_agent_id: int,
    last_read_message_id: int,
) -> List[Tuple[int, int, Optional[datetime], Optional[datetime]]]:
    now = datetime.utcnow()
    msgs = (
        db.query(InternalDmMessage)
        .filter(
            InternalDmMessage.conversation_id == conversation_id,
            InternalDmMessage.id <= last_read_message_id,
        )
        .all()
    )
    updates: List[Tuple[int, int, Optional[datetime], Optional[datetime]]] = []
    for m in msgs:
        if m.sender_agent_id == reader_agent_id:
            continue
        row = (
            db.query(DmMessageReceipt)
            .filter(
                DmMessageReceipt.message_id == m.id,
                DmMessageReceipt.recipient_agent_id == reader_agent_id,
            )
            .first()
        )
        if row is None:
            row = DmMessageReceipt(message_id=m.id, recipient_agent_id=reader_agent_id)
            db.add(row)
        if row.read_at is None:
            row.read_at = now
            if row.delivered_at is None:
                row.delivered_at = now
            db.add(row)
            updates.append((m.id, reader_agent_id, row.delivered_at, row.read_at))
    if updates:
        db.commit()
    return updates


def dm_receipt_for_sender_view(
    db: Session, message_id: int, sender_agent_id: int
) -> Optional[DmMessageReceipt]:
    """Receipt row is keyed by recipient = peer of sender."""
    m = db.query(InternalDmMessage).filter(InternalDmMessage.id == message_id).first()
    if not m or m.sender_agent_id != sender_agent_id:
        return None
    conv = (
        db.query(InternalDmConversation)
        .filter(InternalDmConversation.id == m.conversation_id)
        .first()
    )
    if not conv:
        return None
    peer = other_participant_id(conv, sender_agent_id)
    return (
        db.query(DmMessageReceipt)
        .filter(
            DmMessageReceipt.message_id == message_id,
            DmMessageReceipt.recipient_agent_id == peer,
        )
        .first()
    )
