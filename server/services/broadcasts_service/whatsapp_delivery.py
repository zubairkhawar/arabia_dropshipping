"""
Helpers for customer WhatsApp broadcast delivery (24h session vs template).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from models import Customer, Message, Order

WHATSAPP_SESSION_HOURS = 24


def last_customer_message_at(db: Session, conversation_id: int) -> Optional[datetime]:
    m = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.sender_type == "customer",
        )
        .order_by(Message.created_at.desc())
        .first()
    )
    if not m or not m.created_at:
        return None
    return m.created_at


def customer_in_whatsapp_session_window(
    db: Session,
    conversation_id: int,
    *,
    hours: int = WHATSAPP_SESSION_HOURS,
) -> bool:
    """True if the last inbound customer message on this thread is within ``hours``."""
    ts = last_customer_message_at(db, conversation_id)
    if not ts:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return ts >= cutoff


def latest_order_number_for_customer(
    db: Session, tenant_id: int, customer_id: int
) -> str:
    o = (
        db.query(Order)
        .filter(Order.tenant_id == tenant_id, Order.customer_id == customer_id)
        .order_by(Order.created_at.desc())
        .first()
    )
    if not o:
        return ""
    return (o.order_number or "").strip()


def expand_whatsapp_template_tokens(
    db: Session,
    tenant_id: int,
    customer: Customer,
    raw_parameters: Optional[List[Any]],
) -> List[str]:
    """
    Expand ``{customer_name}``, ``{order_id}``, ``{order_number}`` in each template body slot.
    """
    name = (customer.name or customer.email or "Customer").strip() or "Customer"
    oid = latest_order_number_for_customer(db, tenant_id, customer.id)
    repl: dict[str, str] = {
        "{customer_name}": name,
        "{order_id}": oid,
        "{order_number}": oid,
    }
    out: List[str] = []
    for raw in raw_parameters or []:
        s = str(raw)
        for k, v in repl.items():
            s = s.replace(k, v)
        out.append(s)
    return out


def count_named_body_placeholders(components: Any) -> int:
    """Count ``{{1}}``-style placeholders in the BODY component text (Meta format)."""
    if not isinstance(components, list):
        return 0
    for c in components:
        if not isinstance(c, dict):
            continue
        if str(c.get("type") or "").upper() != "BODY":
            continue
        text = str(c.get("text") or "")
        return len(re.findall(r"\{\{\s*\d+\s*\}\}", text))
    return 0
