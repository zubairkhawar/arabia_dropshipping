"""Structured agent availability for LLM prompts (online counts, schedule, broadcasts)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from models import Agent, Broadcast, TenantSchedule
from services.broadcasts_service.broadcast_agent_lock import (
    broadcast_covers_now,
    utc_naive_to_pkt_iso,
)
from services.tenant_schedule_text import format_tenant_schedule_for_customer

_ONLINE_STATUSES = ("online", "busy")


def count_online_agents(db: Session, tenant_id: int) -> int:
    return (
        db.query(Agent)
        .filter(Agent.tenant_id == tenant_id, Agent.status.in_(_ONLINE_STATUSES))
        .count()
    )


def _active_ai_broadcasts(db: Session, tenant_id: int) -> List[Broadcast]:
    """Broadcasts with target_ai that cover ``now`` (agents unavailable for handoff)."""
    now = datetime.utcnow()
    rows = (
        db.query(Broadcast)
        .filter(Broadcast.tenant_id == tenant_id)
        .all()
    )
    active: List[Broadcast] = []
    for b in rows:
        if broadcast_covers_now(b, now):
            active.append(b)
    return active


def _schedule_text(db: Session, tenant_id: int, language: str) -> str:
    sched = (
        db.query(TenantSchedule).filter(TenantSchedule.tenant_id == tenant_id).first()
    )
    if not sched:
        return "No configured agent schedule."
    lang = (language or "english").strip().lower()
    return format_tenant_schedule_for_customer(
        lang,
        working_days=sched.working_days,
        start_time=sched.start_time,
        end_time=sched.end_time,
    )


def build_agent_availability_payload(
    db: Session,
    tenant_id: int,
    *,
    language: str = "english",
    customer_message: str = "",
) -> Dict[str, Any]:
    n_online = count_online_agents(db, tenant_id)
    blocking = _active_ai_broadcasts(db, tenant_id)
    lock_active = len(blocking) > 0

    if lock_active:
        agents_online = False
        agents_online_count = 0
    else:
        agents_online = n_online > 0
        agents_online_count = n_online

    active_list = [
        {
            "title": b.title,
            "agent_availability_message": b.message,
            "starts_at": utc_naive_to_pkt_iso(b.starts_at),
            "ends_at": utc_naive_to_pkt_iso(b.ends_at),
            "agents_unavailable": True,
        }
        for b in blocking
    ]
    return {
        "agents_online": agents_online,
        "agents_online_count": agents_online_count,
        "agents_unavailable_due_to_broadcast": lock_active,
        "current_schedule": _schedule_text(db, tenant_id, language),
        "active_broadcasts": active_list,
        "customer_message": (customer_message or "").strip(),
    }


def format_agent_availability_json_for_prompt(
    db: Session,
    tenant_id: int,
    *,
    language: str = "english",
    customer_message: str = "",
) -> str:
    payload = build_agent_availability_payload(
        db,
        tenant_id,
        language=language,
        customer_message=customer_message,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)
