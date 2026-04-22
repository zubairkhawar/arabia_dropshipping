"""Structured agent availability for LLM prompts (online counts, schedule, broadcasts)."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models import Agent, Broadcast, TenantSchedule
from services.tenant_schedule_text import format_tenant_schedule_for_customer

_ONLINE_STATUSES = ("online", "busy")


def count_online_agents(db: Session, tenant_id: int) -> int:
    return (
        db.query(Agent)
        .filter(Agent.tenant_id == tenant_id, Agent.status.in_(_ONLINE_STATUSES))
        .count()
    )


def _active_broadcasts(db: Session, tenant_id: int) -> List[Broadcast]:
    now = datetime.utcnow()
    rows = db.query(Broadcast).filter(Broadcast.tenant_id == tenant_id).all()
    active: List[Broadcast] = []
    for b in rows:
        if not getattr(b, "target_ai", True):
            continue
        starts_ok = b.starts_at is None or b.starts_at <= now
        ends_ok = b.ends_at is None or b.ends_at >= now
        if starts_ok and ends_ok:
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


def _iso_day(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def build_agent_availability_payload(
    db: Session,
    tenant_id: int,
    *,
    language: str = "english",
    customer_message: str = "",
) -> Dict[str, Any]:
    n = count_online_agents(db, tenant_id)
    broadcasts = _active_broadcasts(db, tenant_id)
    active_list = [
        {
            "title": b.title,
            "agent_availability_message": b.message,
            "starts_at": _iso_day(b.starts_at),
            "ends_at": _iso_day(b.ends_at),
        }
        for b in broadcasts
    ]
    return {
        "agents_online": n > 0,
        "agents_online_count": n,
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
