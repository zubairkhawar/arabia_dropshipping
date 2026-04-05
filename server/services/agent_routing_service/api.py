from typing import List, Optional
from enum import Enum
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database import get_db
from models import Agent, Conversation, Customer, Store, StoreAgentMapping, AgentAttendanceSession


router = APIRouter()


class AgentStatus(str, Enum):
    online = "online"
    busy = "busy"
    offline = "offline"


class AgentOut(BaseModel):
    id: int
    tenant_id: int
    status: AgentStatus
    team: Optional[str] = None

    class Config:
        orm_mode = True


class AgentStatusUpdate(BaseModel):
    status: AgentStatus
    max_concurrent_chats: Optional[int] = None
    team: Optional[str] = None


class AssignRequest(BaseModel):
    tenant_id: int
    conversation_id: int
    store_id: int
    customer_id: int
    routed_team: Optional[str] = None  # Team chosen by AI after qualification
    is_existing_customer: bool = False
    prefer_team_first: bool = Field(
        default=False,
        description="When True, try routed_team before previous-agent / store mapping (bot handoff).",
    )


# Hard cap per product spec (also respects Agent.max_concurrent_chats when lower).
MAX_ROUTING_CHATS_PER_AGENT = 7


class AssignResponse(BaseModel):
    conversation_id: int
    agent_id: Optional[int]
    reason: str


class TransferRequest(BaseModel):
    conversation_id: int
    target_agent_id: Optional[int] = None
    target_team: Optional[str] = None


class AttendanceSessionOut(BaseModel):
    start_at: datetime
    end_at: Optional[datetime] = None


class AttendanceDayOut(BaseModel):
    date: str
    total_minutes: int
    sessions: List[AttendanceSessionOut]


class AttendanceResponse(BaseModel):
    agent_id: int
    days: List[AttendanceDayOut]


@router.get("/agents", response_model=List[AgentOut])
async def list_agents(tenant_id: int, db: Session = Depends(get_db)):
    """List all agents with their status for a tenant."""
    agents = db.query(Agent).filter(Agent.tenant_id == tenant_id).all()
    return agents


@router.post("/agents/{agent_id}/status", response_model=AgentOut)
async def update_agent_status(
    agent_id: int,
    payload: AgentStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update agent status (online, busy, offline) and optional team/max chats."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    previous_status = agent.status
    next_status = payload.status.value
    now = datetime.utcnow()
    was_active = previous_status in (
        AgentStatus.online.value,
        AgentStatus.busy.value,
    )
    is_active = next_status in (
        AgentStatus.online.value,
        AgentStatus.busy.value,
    )

    if not was_active and is_active:
        open_session = (
            db.query(AgentAttendanceSession)
            .filter(
                AgentAttendanceSession.tenant_id == agent.tenant_id,
                AgentAttendanceSession.agent_id == agent.id,
                AgentAttendanceSession.ended_at.is_(None),
            )
            .order_by(AgentAttendanceSession.started_at.desc())
            .first()
        )
        if not open_session:
            db.add(
                AgentAttendanceSession(
                    tenant_id=agent.tenant_id,
                    agent_id=agent.id,
                    started_at=now,
                    ended_at=None,
                    created_at=now,
                )
            )

    if was_active and not is_active:
        open_session = (
            db.query(AgentAttendanceSession)
            .filter(
                AgentAttendanceSession.tenant_id == agent.tenant_id,
                AgentAttendanceSession.agent_id == agent.id,
                AgentAttendanceSession.ended_at.is_(None),
            )
            .order_by(AgentAttendanceSession.started_at.desc())
            .first()
        )
        if open_session:
            open_session.ended_at = now
            db.add(open_session)

    agent.status = next_status
    if payload.max_concurrent_chats is not None:
        agent.max_concurrent_chats = payload.max_concurrent_chats
    if payload.team is not None:
        agent.team = payload.team

    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/agents/{agent_id}/attendance", response_model=AttendanceResponse)
async def get_agent_attendance(
    agent_id: int,
    tenant_id: int,
    days: int = 220,
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.id == agent_id, Agent.tenant_id == tenant_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    today = datetime.utcnow().date()
    start_date = today - timedelta(days=max(1, min(days, 400)) - 1)
    start_dt = datetime.combine(start_date, datetime.min.time())

    sessions = (
        db.query(AgentAttendanceSession)
        .filter(
            AgentAttendanceSession.tenant_id == tenant_id,
            AgentAttendanceSession.agent_id == agent_id,
            AgentAttendanceSession.started_at >= start_dt,
        )
        .order_by(AgentAttendanceSession.started_at.asc())
        .all()
    )

    by_day: dict[str, AttendanceDayOut] = {}
    for s in sessions:
        day = s.started_at.date().isoformat()
        if day not in by_day:
            by_day[day] = AttendanceDayOut(date=day, total_minutes=0, sessions=[])
        end_at = s.ended_at or datetime.utcnow()
        minutes = max(0, int((end_at - s.started_at).total_seconds() // 60))
        by_day[day].total_minutes += minutes
        by_day[day].sessions.append(
            AttendanceSessionOut(start_at=s.started_at, end_at=s.ended_at)
        )

    return AttendanceResponse(
        agent_id=agent_id,
        days=list(by_day.values()),
    )


def _get_previous_agent_for_customer(
    db: Session, tenant_id: int, customer_id: int
) -> Optional[Agent]:
    """Find the most recent agent who handled this customer, if any."""
    last_conv = (
        db.query(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Conversation.customer_id == customer_id,
            Conversation.agent_id.isnot(None),
        )
        .order_by(desc(Conversation.updated_at))
        .first()
    )
    if last_conv and last_conv.agent_id:
        return db.query(Agent).filter(Agent.id == last_conv.agent_id).first()
    return None


def _active_assigned_conversations(db: Session, agent_id: int) -> int:
    n = (
        db.query(func.count(Conversation.id))
        .filter(
            Conversation.agent_id == agent_id,
            Conversation.status == "active",
        )
        .scalar()
    )
    return int(n or 0)


def _agent_capacity_limit(agent: Agent) -> int:
    raw = (
        agent.max_concurrent_chats
        if agent.max_concurrent_chats is not None
        else MAX_ROUTING_CHATS_PER_AGENT
    )
    return min(MAX_ROUTING_CHATS_PER_AGENT, max(1, int(raw)))


def _agent_has_capacity(db: Session, agent: Agent) -> bool:
    return _active_assigned_conversations(db, agent.id) < _agent_capacity_limit(agent)


def _get_store_mapped_agent(
    db: Session, tenant_id: int, store_id: int
) -> Optional[Agent]:
    """Return agent mapped to this store, if any."""
    mapping = (
        db.query(StoreAgentMapping)
        .filter(
            StoreAgentMapping.tenant_id == tenant_id,
            StoreAgentMapping.store_id == store_id,
        )
        .first()
    )
    if mapping:
        return db.query(Agent).filter(Agent.id == mapping.agent_id).first()
    return None


def _get_random_available_agent(
    db: Session, tenant_id: int, team: Optional[str] = None
) -> Optional[Agent]:
    """Pick a random online agent under capacity, optionally filtered by team."""
    query = db.query(Agent).filter(
        Agent.tenant_id == tenant_id,
        Agent.status == AgentStatus.online.value,
    )
    if team:
        query = query.filter(Agent.team == team)

    eligible = [a for a in query.all() if _agent_has_capacity(db, a)]
    if not eligible:
        return None
    return random.choice(eligible)


def perform_conversation_assignment(
    db: Session, payload: AssignRequest
) -> Optional[AssignResponse]:
    """
    Core assignment rules. Returns None if conversation does not exist.
    """
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == payload.conversation_id,
            Conversation.tenant_id == payload.tenant_id,
        )
        .first()
    )
    if not conversation:
        return None

    if conversation.agent_id:
        return AssignResponse(
            conversation_id=conversation.id,
            agent_id=conversation.agent_id,
            reason="conversation_already_assigned",
        )

    def _commit(agent: Agent, reason: str) -> AssignResponse:
        conversation.agent_id = agent.id
        db.add(conversation)
        db.commit()
        return AssignResponse(
            conversation_id=conversation.id,
            agent_id=agent.id,
            reason=reason,
        )

    if payload.prefer_team_first and payload.routed_team:
        team_first = _get_random_available_agent(
            db, payload.tenant_id, team=payload.routed_team
        )
        if team_first:
            return _commit(team_first, "bot_routed_team")

    previous_agent = _get_previous_agent_for_customer(
        db, payload.tenant_id, payload.customer_id
    )
    if previous_agent and _agent_has_capacity(db, previous_agent):
        return _commit(previous_agent, "previous_agent_for_customer")

    mapped_agent = _get_store_mapped_agent(db, payload.tenant_id, payload.store_id)
    if mapped_agent and _agent_has_capacity(db, mapped_agent):
        return _commit(mapped_agent, "store_mapped_agent")

    candidate = _get_random_available_agent(
        db, payload.tenant_id, team=payload.routed_team
    )
    if not candidate:
        candidate = _get_random_available_agent(db, payload.tenant_id, team=None)
    if not candidate:
        return AssignResponse(
            conversation_id=conversation.id,
            agent_id=None,
            reason="no_available_agent",
        )

    return _commit(candidate, "random_available_agent")


def assign_from_bot_flow(
    db: Session,
    *,
    tenant_id: int,
    conversation_id: int,
    store_id: int,
    customer_id: int,
    routed_team: Optional[str],
    is_existing_customer: bool = False,
) -> AssignResponse:
    """Assign after customer-bot handoff; prefers the routed team when set."""
    payload = AssignRequest(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        store_id=store_id,
        customer_id=customer_id,
        routed_team=routed_team,
        is_existing_customer=is_existing_customer,
        prefer_team_first=bool(routed_team),
    )
    result = perform_conversation_assignment(db, payload)
    if result is None:
        return AssignResponse(
            conversation_id=conversation_id,
            agent_id=None,
            reason="conversation_not_found",
        )
    return result


@router.post("/assign", response_model=AssignResponse)
async def assign_conversation(payload: AssignRequest, db: Session = Depends(get_db)):
    """
    Assign conversation to an available agent following routing rules:

    1. Old customer → previous agent if exists (when under capacity).
    2. Store mapped to an agent → mapped agent (when under capacity).
    3. Otherwise → random online agent in routed team (if provided) or any team.
    Each agent accepts at most min(7, max_concurrent_chats) active conversations.
    """
    result = perform_conversation_assignment(db, payload)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if result.agent_id is not None:
        from services.agent_portal_service.broadcast import push_unread_summary

        await push_unread_summary(db, payload.tenant_id, result.agent_id)
    return result


@router.post("/transfer", response_model=AssignResponse)
async def transfer_conversation(payload: TransferRequest, db: Session = Depends(get_db)):
    """
    Transfer conversation between agents.

    - If target_agent_id provided → direct transfer.
    - Else if target_team provided → random online agent from that team.
    """
    conversation = db.query(Conversation).filter(Conversation.id == payload.conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if payload.target_agent_id is not None:
        agent = db.query(Agent).filter(Agent.id == payload.target_agent_id).first()
        if not agent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target agent not found")
    else:
        agent = _get_random_available_agent(
            db, tenant_id=conversation.tenant_id, team=payload.target_team
        )
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No available agent to transfer conversation",
            )

    prev_agent_id = conversation.agent_id
    conversation.agent_id = agent.id
    db.add(conversation)
    db.commit()
    from services.agent_portal_service.broadcast import push_unread_summary

    tid = conversation.tenant_id
    await push_unread_summary(db, tid, agent.id)
    if prev_agent_id is not None and prev_agent_id != agent.id:
        await push_unread_summary(db, tid, prev_agent_id)

    return AssignResponse(
        conversation_id=conversation.id,
        agent_id=agent.id,
        reason="transfer",
    )
