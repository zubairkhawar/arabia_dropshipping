from datetime import datetime, timedelta
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from database import get_db
from models import Message, Conversation, Agent

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard_analytics(
    tenant_id: int,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    High-level dashboard analytics used by the admin dashboard.
    Returns:
    - total_messages
    - total_messages_change_percent (vs previous period)
    - total_agents
    - active_agents (online)
    - ai_handled_percent (messages from AI vs total)
    """
    now = datetime.utcnow()
    period_start = now - timedelta(days=days)
    prev_start = period_start - timedelta(days=days)

    # Total messages current period
    total_current = (
        db.query(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.created_at >= period_start,
            Message.created_at <= now,
        )
        .scalar()
        or 0
    )

    # Total messages previous period
    total_prev = (
        db.query(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.created_at >= prev_start,
            Message.created_at < period_start,
        )
        .scalar()
        or 0
    )

    if total_prev == 0:
        total_change_percent = 100.0 if total_current > 0 else 0.0
    else:
        total_change_percent = ((total_current - total_prev) / total_prev) * 100.0

    # AI handled messages share
    ai_messages = (
        db.query(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.sender_type == "ai",
            Message.created_at >= period_start,
            Message.created_at <= now,
        )
        .scalar()
        or 0
    )
    ai_handled_percent = (
        (ai_messages / total_current) * 100.0 if total_current > 0 else 0.0
    )

    # Agent counts
    total_agents = (
        db.query(func.count(Agent.id))
        .filter(Agent.tenant_id == tenant_id)
        .scalar()
        or 0
    )
    active_agents = (
        db.query(func.count(Agent.id))
        .filter(Agent.tenant_id == tenant_id, Agent.status == "online")
        .scalar()
        or 0
    )

    return {
        "total_messages": total_current,
        "total_messages_change_percent": total_change_percent,
        "ai_handled_percent": ai_handled_percent,
        "total_agents": total_agents,
        "active_agents": active_agents,
        "period_days": days,
    }


@router.get("/agent-activity")
async def get_agent_activity(
    tenant_id: int,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Time-series of messages by day, split by sender_type.
    Used for "Agent Activity" chart.
    """
    now = datetime.utcnow()
    start = now - timedelta(days=days)

    # Group by date and sender_type
    rows = (
        db.query(
            func.date_trunc("day", Message.created_at).label("day"),
            Message.sender_type,
            func.count(Message.id).label("count"),
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.created_at >= start,
            Message.created_at <= now,
        )
        .group_by("day", Message.sender_type)
        .order_by("day")
        .all()
    )

    series: Dict[str, Dict[str, int]] = {}
    for day, sender_type, count in rows:
        day_str = day.date().isoformat()
        if day_str not in series:
            series[day_str] = {"customer": 0, "agent": 0, "ai": 0}
        if sender_type in series[day_str]:
            series[day_str][sender_type] = int(count)

    return {"days": series}


@router.get("/language-distribution")
async def get_language_distribution(
    tenant_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Aggregate distribution of languages over recent messages.
    """
    now = datetime.utcnow()
    start = now - timedelta(days=days)

    rows = (
        db.query(Message.language, func.count(Message.id).label("count"))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.created_at >= start,
            Message.created_at <= now,
            Message.language.isnot(None),
        )
        .group_by(Message.language)
        .all()
    )

    total = sum(int(c) for _, c in rows) or 1
    distribution: List[Dict[str, Any]] = []
    for language, count in rows:
        distribution.append(
            {
                "language": language,
                "count": int(count),
                "percent": (int(count) / total) * 100.0,
            }
        )

    return {"languages": distribution, "period_days": days}
