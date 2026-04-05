"""Team channel per-peer delivery/read receipts (team_message_receipts)."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from models import TeamChannelMessage, TeamMembership, TeamMessageReceipt


def _team_member_agent_ids(db: Session, tenant_id: int, team_id: int) -> List[int]:
    rows = (
        db.query(TeamMembership.agent_id)
        .filter(
            TeamMembership.tenant_id == tenant_id,
            TeamMembership.team_id == team_id,
        )
        .all()
    )
    return [r[0] for r in rows]


def recipient_agent_ids_for_team_message(db: Session, msg: TeamChannelMessage) -> List[int]:
    members = _team_member_agent_ids(db, msg.tenant_id, msg.team_id)
    if bool(getattr(msg, "posted_by_admin", False)):
        return members
    sid = msg.sender_agent_id
    if sid is None:
        return members
    return [a for a in members if a != sid]


def ensure_team_message_receipt_rows(db: Session, msg: TeamChannelMessage) -> None:
    for aid in recipient_agent_ids_for_team_message(db, msg):
        exists = (
            db.query(TeamMessageReceipt)
            .filter(
                TeamMessageReceipt.message_id == msg.id,
                TeamMessageReceipt.agent_id == aid,
            )
            .first()
        )
        if exists is None:
            db.add(TeamMessageReceipt(message_id=msg.id, agent_id=aid))
    db.commit()


def mark_team_messages_delivered(
    db: Session,
    tenant_id: int,
    team_id: int,
    recipient_agent_id: int,
    message_ids: List[int],
) -> List[Tuple[int, int, Optional[datetime], Optional[datetime]]]:
    """
    Mark messages as delivered to recipient_agent_id (WS client).
    Returns list of (message_id, agent_id, delivered_at, read_at) for broadcast.
    """
    now = datetime.utcnow()
    broadcast: List[Tuple[int, int, Optional[datetime], Optional[datetime]]] = []
    seen: Set[int] = set()
    for mid in message_ids:
        if mid in seen:
            continue
        seen.add(mid)
        m = (
            db.query(TeamChannelMessage)
            .filter(
                TeamChannelMessage.id == mid,
                TeamChannelMessage.team_id == team_id,
                TeamChannelMessage.tenant_id == tenant_id,
            )
            .first()
        )
        if not m:
            continue
        if not bool(getattr(m, "posted_by_admin", False)) and m.sender_agent_id == recipient_agent_id:
            continue
        row = (
            db.query(TeamMessageReceipt)
            .filter(
                TeamMessageReceipt.message_id == mid,
                TeamMessageReceipt.agent_id == recipient_agent_id,
            )
            .first()
        )
        if row is None:
            row = TeamMessageReceipt(message_id=mid, agent_id=recipient_agent_id)
            db.add(row)
        changed = False
        if row.delivered_at is None:
            row.delivered_at = now
            changed = True
        if changed:
            db.add(row)
        if changed:
            broadcast.append((mid, recipient_agent_id, row.delivered_at, row.read_at))
    if broadcast:
        db.commit()
    return broadcast


def mark_team_read_through_receipts(
    db: Session,
    tenant_id: int,
    team_id: int,
    reader_agent_id: int,
    last_read_message_id: int,
) -> List[Tuple[int, int, Optional[datetime], Optional[datetime]]]:
    """Set read_at on receipts for this reader for messages up to cursor."""
    now = datetime.utcnow()
    msgs = (
        db.query(TeamChannelMessage)
        .filter(
            TeamChannelMessage.tenant_id == tenant_id,
            TeamChannelMessage.team_id == team_id,
            TeamChannelMessage.id <= last_read_message_id,
        )
        .all()
    )
    updates: List[Tuple[int, int, Optional[datetime], Optional[datetime]]] = []
    for m in msgs:
        if not bool(getattr(m, "posted_by_admin", False)) and m.sender_agent_id == reader_agent_id:
            continue
        row = (
            db.query(TeamMessageReceipt)
            .filter(
                TeamMessageReceipt.message_id == m.id,
                TeamMessageReceipt.agent_id == reader_agent_id,
            )
            .first()
        )
        if row is None:
            row = TeamMessageReceipt(message_id=m.id, agent_id=reader_agent_id)
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


def batch_team_receipt_summaries(
    db: Session,
    message_ids: List[int],
) -> Dict[int, Dict[str, int]]:
    """message_id -> {recipient_count, delivered_count, read_count}."""
    if not message_ids:
        return {}
    rows = (
        db.query(TeamMessageReceipt)
        .filter(TeamMessageReceipt.message_id.in_(message_ids))
        .all()
    )
    by_mid: Dict[int, List[TeamMessageReceipt]] = {}
    for r in rows:
        by_mid.setdefault(r.message_id, []).append(r)
    out: Dict[int, Dict[str, int]] = {}
    for mid in message_ids:
        lst = by_mid.get(mid, [])
        out[mid] = {
            "recipient_count": len(lst),
            "delivered_count": sum(1 for x in lst if x.delivered_at is not None),
            "read_count": sum(1 for x in lst if x.read_at is not None),
        }
    return out
