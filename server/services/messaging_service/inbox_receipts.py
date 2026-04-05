"""Inbox message delivery/read receipts for assigned agents."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from models import Conversation, InboxMessageReceipt, Message


def ensure_receipt_for_customer_message(db: Session, msg: Message) -> None:
    if msg.sender_type != "customer":
        return
    conv = db.query(Conversation).filter(Conversation.id == msg.conversation_id).first()
    if not conv or not conv.agent_id:
        return
    exists = (
        db.query(InboxMessageReceipt)
        .filter(
            InboxMessageReceipt.message_id == msg.id,
            InboxMessageReceipt.agent_id == conv.agent_id,
        )
        .first()
    )
    if exists:
        return
    db.add(InboxMessageReceipt(message_id=msg.id, agent_id=conv.agent_id))


def mark_delivered(db: Session, message_ids: Iterable[int], agent_id: int) -> None:
    now = datetime.utcnow()
    for mid in message_ids:
        row = (
            db.query(InboxMessageReceipt)
            .filter(
                InboxMessageReceipt.message_id == mid,
                InboxMessageReceipt.agent_id == agent_id,
            )
            .first()
        )
        if row and row.delivered_at is None:
            row.delivered_at = now
            db.add(row)


def mark_read_through(db: Session, conversation_id: int, agent_id: int, last_read_message_id: int) -> None:
    now = datetime.utcnow()
    rows: List[Message] = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.sender_type == "customer",
            Message.id <= last_read_message_id,
        )
        .all()
    )
    for m in rows:
        rec = (
            db.query(InboxMessageReceipt)
            .filter(
                InboxMessageReceipt.message_id == m.id,
                InboxMessageReceipt.agent_id == agent_id,
            )
            .first()
        )
        if rec and rec.read_at is None:
            rec.read_at = now
            db.add(rec)


def get_receipt_map(db: Session, message_ids: List[int], agent_id: Optional[int]) -> dict[int, InboxMessageReceipt]:
    if not message_ids or not agent_id:
        return {}
    rows = (
        db.query(InboxMessageReceipt)
        .filter(
            InboxMessageReceipt.message_id.in_(message_ids),
            InboxMessageReceipt.agent_id == agent_id,
        )
        .all()
    )
    return {r.message_id: r for r in rows}
