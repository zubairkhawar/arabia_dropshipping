from datetime import datetime, timedelta
from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, case, distinct
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
    - total_conversations (all conversations in the period)
    - total_conversations_change_percent (vs previous period)
    - ai_handled_conversations (conversations handled entirely by AI, no agent assigned)
    - ai_handled_percent (percentage of total conversations handled by AI)
    - total_agents
    - active_agents (online)
    """
    now = datetime.utcnow()
    period_start = now - timedelta(days=days)
    prev_start = period_start - timedelta(days=days)

    # Total conversations current period
    total_conversations_current = (
        db.query(func.count(Conversation.id))
        .filter(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= period_start,
            Conversation.created_at <= now,
        )
        .scalar()
        or 0
    )

    # Total conversations previous period
    total_conversations_prev = (
        db.query(func.count(Conversation.id))
        .filter(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= prev_start,
            Conversation.created_at < period_start,
        )
        .scalar()
        or 0
    )

    if total_conversations_prev == 0:
        total_conversations_change_percent = (
            100.0 if total_conversations_current > 0 else 0.0
        )
    else:
        total_conversations_change_percent = (
            (total_conversations_current - total_conversations_prev)
            / total_conversations_prev
        ) * 100.0

    # AI-handled conversations: conversations where no agent was ever assigned
    ai_handled_conversations = (
        db.query(func.count(Conversation.id))
        .filter(
            Conversation.tenant_id == tenant_id,
            Conversation.agent_id.is_(None),
            Conversation.created_at >= period_start,
            Conversation.created_at <= now,
        )
        .scalar()
        or 0
    )
    ai_handled_percent = (
        (ai_handled_conversations / total_conversations_current) * 100.0
        if total_conversations_current > 0
        else 0.0
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
        "total_conversations": total_conversations_current,
        "total_conversations_change_percent": total_conversations_change_percent,
        "ai_handled_conversations": ai_handled_conversations,
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
    Time-series of daily activity used for the "Agent Activity" chart.
    Returns per-day:
    - conversations_handled: distinct conversations where an agent sent at least one message
    - agent_messages: total agent messages
    - ai_messages: total AI bot messages
    """
    now = datetime.utcnow()
    start = now - timedelta(days=days)

    # Conversations handled by agents per day (distinct conversations with agent replies)
    conv_rows = (
        db.query(
            func.date(Message.created_at).label("day"),
            func.count(distinct(Message.conversation_id)).label("conv_count"),
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.sender_type == "agent",
            Message.created_at >= start,
            Message.created_at <= now,
        )
        .group_by("day")
        .order_by("day")
        .all()
    )

    # Message counts by sender type per day
    msg_rows = (
        db.query(
            func.date(Message.created_at).label("day"),
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

    # Ensure all days in range are present so charts have a stable axis.
    for i in range(days):
        d = (start + timedelta(days=i)).date().isoformat()
        series[d] = {"conversations_handled": 0, "agent_messages": 0, "ai_messages": 0, "customer_messages": 0}

    for day, conv_count in conv_rows:
        day_str = str(day)
        if day_str in series:
            series[day_str]["conversations_handled"] = int(conv_count)

    for day, sender_type, count in msg_rows:
        day_str = str(day)
        if day_str not in series:
            series[day_str] = {"conversations_handled": 0, "agent_messages": 0, "ai_messages": 0, "customer_messages": 0}
        if sender_type == "agent":
            series[day_str]["agent_messages"] = int(count)
        elif sender_type == "ai":
            series[day_str]["ai_messages"] = int(count)
        elif sender_type == "customer":
            series[day_str]["customer_messages"] = int(count)

    return {"days": dict(sorted(series.items(), key=lambda item: item[0]))}


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
