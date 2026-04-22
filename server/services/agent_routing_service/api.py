from typing import Dict, List, Optional
from enum import Enum
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from datetime import timezone as dt_timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database import get_db
from models import Agent, Conversation, Customer, Store, StoreAgentMapping, AgentAttendanceSession, Tenant
from services.auth_service.api import get_current_user
from services.auth_service.models import User as AuthUser
from services.customer_bot_flow import lookup_agent_display_name
from services.whatsapp_service.meta_cloud import MetaWhatsAppClient


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
        from_attributes = True


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


# Upper sanity bound; per-agent limit comes from Agent.max_concurrent_chats (tenant-synced).
MAX_ROUTING_CHATS_PER_AGENT = 100


class AssignResponse(BaseModel):
    conversation_id: int
    agent_id: Optional[int]
    reason: str


class TransferRequest(BaseModel):
    conversation_id: int
    target_agent_id: Optional[int] = None
    target_team: Optional[str] = None
    customer_message: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Same text as the inbox transfer notice; sent to WhatsApp when channel is WhatsApp.",
    )


def _datetime_utc_iso_z(v: Optional[datetime]) -> Optional[str]:
    """Serialize naive DB UTC instants with explicit Z for correct client parsing."""
    if v is None:
        return None
    aware = v.replace(tzinfo=dt_timezone.utc) if v.tzinfo is None else v.astimezone(dt_timezone.utc)
    return aware.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


class AttendanceSessionOut(BaseModel):
    start_at: datetime
    end_at: Optional[datetime] = None

    @field_serializer("start_at")
    def _ser_start_at(self, v: datetime) -> str:
        return _datetime_utc_iso_z(v) or ""

    @field_serializer("end_at")
    def _ser_end_at(self, v: Optional[datetime]) -> Optional[str]:
        return _datetime_utc_iso_z(v)


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
            # Check if a session was closed within the last 30 seconds (page refresh
            # artifact: pagehide fires offline beacon, then onopen fires online again).
            # Reopen that session instead of creating a new 0-second one.
            refresh_cutoff = now - timedelta(seconds=30)
            recent_closed = (
                db.query(AgentAttendanceSession)
                .filter(
                    AgentAttendanceSession.tenant_id == agent.tenant_id,
                    AgentAttendanceSession.agent_id == agent.id,
                    AgentAttendanceSession.ended_at >= refresh_cutoff,
                )
                .order_by(AgentAttendanceSession.ended_at.desc())
                .first()
            )
            if recent_closed:
                # Page refresh — reopen the existing session, discard the gap.
                recent_closed.ended_at = None
                db.add(recent_closed)
            else:
                db.add(
                    AgentAttendanceSession(
                        tenant_id=agent.tenant_id,
                        agent_id=agent.id,
                        started_at=now,
                        ended_at=None,
                        created_at=now,
                    )
                )

    if not is_active:
        # Close ALL open attendance sessions when going offline (or already offline).
        # This also cleans up dangling sessions from crashes/disconnects.
        open_sessions = (
            db.query(AgentAttendanceSession)
            .filter(
                AgentAttendanceSession.tenant_id == agent.tenant_id,
                AgentAttendanceSession.agent_id == agent.id,
                AgentAttendanceSession.ended_at.is_(None),
            )
            .all()
        )
        for open_session in open_sessions:
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


@router.post("/agents/{agent_id}/heartbeat")
async def agent_heartbeat(
    agent_id: int,
    db: Session = Depends(get_db),
):
    """
    Lightweight keepalive from the agent portal (sent every ~30 minutes while the tab is
    visible and the agent is online).  Ensures the open attendance session stays alive so a
    forgotten-open tab doesn't produce a wildly inflated session once the stale auto-close
    kicks in — the session is either actively receiving heartbeats (agent is still there) or
    it will be capped at 8 hours by the stale-session cleanup.

    Also recovers a missing open session: if the agent's DB status is online/busy but no
    open session exists (e.g. session was accidentally closed), a new one is created.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    now = datetime.utcnow()
    is_active = agent.status in (AgentStatus.online.value, AgentStatus.busy.value)
    if is_active:
        open_session = (
            db.query(AgentAttendanceSession)
            .filter(
                AgentAttendanceSession.tenant_id == agent.tenant_id,
                AgentAttendanceSession.agent_id == agent.id,
                AgentAttendanceSession.ended_at.is_(None),
            )
            .first()
        )
        if not open_session:
            # Session missing for an active agent — recreate it.
            db.add(
                AgentAttendanceSession(
                    tenant_id=agent.tenant_id,
                    agent_id=agent.id,
                    started_at=now,
                    ended_at=None,
                    created_at=now,
                )
            )
            db.commit()

    return {"ok": True}


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

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    tz_name = (
        (tenant.display_timezone if tenant and getattr(tenant, "display_timezone", None) else None)
        or "Asia/Karachi"
    )
    try:
        tenant_tz = ZoneInfo(tz_name)
    except Exception:
        tenant_tz = ZoneInfo("Asia/Karachi")

    now = datetime.utcnow()
    today = now.date()
    start_date = today - timedelta(days=max(1, min(days, 400)) - 1)
    start_dt = datetime.combine(start_date, datetime.min.time())

    # Auto-close stale sessions (open for > 8 hours).
    # This prevents runaway durations from crashed browsers / forgotten tabs.
    stale_cutoff = now - timedelta(hours=8)
    stale_sessions = (
        db.query(AgentAttendanceSession)
        .filter(
            AgentAttendanceSession.tenant_id == tenant_id,
            AgentAttendanceSession.agent_id == agent_id,
            AgentAttendanceSession.ended_at.is_(None),
            AgentAttendanceSession.started_at < stale_cutoff,
        )
        .all()
    )
    if stale_sessions:
        for ss in stale_sessions:
            # Cap stale session at 8 hours from its start
            ss.ended_at = ss.started_at + timedelta(hours=8)
            db.add(ss)
        db.commit()

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
        end_at = s.ended_at or now
        duration_secs = (end_at - s.started_at).total_seconds()
        # Skip sub-minute sessions: these are almost always page-refresh artifacts
        # (pagehide fires the offline beacon before the page reloads). Only skip
        # sessions that are fully closed — an open session is still accumulating time.
        if s.ended_at is not None and duration_secs < 60:
            continue
        start_utc = s.started_at.replace(tzinfo=dt_timezone.utc)
        local_start = start_utc.astimezone(tenant_tz)
        day = local_start.date().isoformat()
        if day not in by_day:
            by_day[day] = AttendanceDayOut(date=day, total_minutes=0, sessions=[])
        minutes = max(0, int(duration_secs // 60))
        by_day[day].total_minutes += minutes
        by_day[day].sessions.append(
            AttendanceSessionOut(start_at=s.started_at, end_at=s.ended_at)
        )

    # Sort days chronologically (most recent first for display).
    sorted_days = sorted(by_day.values(), key=lambda d: d.date, reverse=True)

    return AttendanceResponse(
        agent_id=agent_id,
        days=sorted_days,
    )


def _get_previous_agent_for_customer(
    db: Session,
    tenant_id: int,
    customer_id: int,
    *,
    exclude_conversation_id: Optional[int] = None,
) -> Optional[Agent]:
    """Find the most recent agent who handled this customer, if any.

    Respects the "send back to AI" signal: if the customer's most recent
    conversation (other than the one currently being routed) has no agent
    assigned, it means an agent/admin explicitly released them to the bot —
    we should NOT silently re-route them to an older agent in that case.
    """
    q = db.query(Conversation).filter(
        Conversation.tenant_id == tenant_id,
        Conversation.customer_id == customer_id,
    )
    if exclude_conversation_id is not None:
        q = q.filter(Conversation.id != exclude_conversation_id)
    last_conv = q.order_by(desc(Conversation.updated_at)).first()
    if last_conv is None:
        return None
    if last_conv.agent_id is None:
        # Most recent prior conversation has no agent → customer was
        # intentionally sent back to the bot. Don't reuse any older agent.
        return None
    return db.query(Agent).filter(Agent.id == last_conv.agent_id).first()


def live_customer_conversation_count(db: Session, agent_id: int) -> int:
    """
    Conversations assigned to this agent that still count toward capacity:
    not closed or resolved (case-insensitive). Escalated and other open states count.
    """
    status_open = func.coalesce(func.lower(Conversation.status), "active").notin_(
        ["closed", "resolved"]
    )
    n = (
        db.query(func.count(Conversation.id))
        .filter(Conversation.agent_id == agent_id, status_open)
        .scalar()
    )
    return int(n or 0)


def live_customer_conversation_counts_for_tenant(db: Session, tenant_id: int) -> Dict[int, int]:
    """Per-agent live counts for admin dashboards (same rules as routing capacity)."""
    status_open = func.coalesce(func.lower(Conversation.status), "active").notin_(
        ["closed", "resolved"]
    )
    rows = (
        db.query(Conversation.agent_id, func.count(Conversation.id))
        .filter(
            Conversation.tenant_id == tenant_id,
            Conversation.agent_id.isnot(None),
            status_open,
        )
        .group_by(Conversation.agent_id)
        .all()
    )
    return {int(aid): int(c) for aid, c in rows}


def _active_assigned_conversations(db: Session, agent_id: int) -> int:
    return live_customer_conversation_count(db, agent_id)


def _agent_capacity_limit(agent: Agent) -> int:
    raw = agent.max_concurrent_chats if agent.max_concurrent_chats is not None else 5
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
        Agent.status.in_((AgentStatus.online.value, AgentStatus.busy.value)),
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
        db,
        payload.tenant_id,
        payload.customer_id,
        exclude_conversation_id=conversation.id,
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
    Each agent accepts at most max_concurrent_chats open conversations (not closed/resolved; 1–100, tenant default).
    """
    result = perform_conversation_assignment(db, payload)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if result.agent_id is not None:
        from services.agent_portal_service.broadcast import push_inbox_sync_event, push_unread_summary

        await push_unread_summary(db, payload.tenant_id, result.agent_id)
        await push_inbox_sync_event(
            db,
            payload.tenant_id,
            result.agent_id,
            {
                "type": "inbox_conversation_refresh",
                "conversation_id": result.conversation_id,
                "reason": "routing_assign",
            },
        )
    return result


@router.post("/transfer", response_model=AssignResponse)
async def transfer_conversation(
    payload: TransferRequest,
    db: Session = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """
    Transfer conversation between agents.

    - If target_agent_id provided → direct transfer.
    - Else if target_team provided → random online agent from that team.

    Caller must be tenant admin, or the currently assigned agent with transfer permission enabled.
    """
    conversation = db.query(Conversation).filter(Conversation.id == payload.conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if current_user.tenant_id != conversation.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")

    role = (current_user.role or "").lower()
    caller_agent_name = "Agent"
    if role == "admin":
        pass
    elif role == "agent":
        caller_agent = (
            db.query(Agent)
            .filter(Agent.user_id == current_user.id, Agent.tenant_id == conversation.tenant_id)
            .first()
        )
        if not caller_agent:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent profile not found")
        if conversation.agent_id is None or conversation.agent_id != caller_agent.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the assigned agent can transfer this conversation",
            )
        if not bool(getattr(caller_agent, "can_transfer_conversations", True)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Transfer is disabled for your account",
            )
        caller_agent_name = lookup_agent_display_name(db, caller_agent.id) or "Agent"
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to transfer")

    if payload.target_agent_id is not None:
        agent = db.query(Agent).filter(Agent.id == payload.target_agent_id).first()
        if not agent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target agent not found")
        if agent.tenant_id != conversation.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target agent is not in this tenant",
            )
    else:
        agent = _get_random_available_agent(
            db, tenant_id=conversation.tenant_id, team=payload.target_team
        )
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No available agent to transfer conversation",
            )

    if agent.id == conversation.agent_id:
        return AssignResponse(
            conversation_id=conversation.id,
            agent_id=agent.id,
            reason="transfer_noop",
        )

    if not _agent_has_capacity(db, agent):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Target agent is at maximum concurrent conversations",
        )

    prev_agent_id = conversation.agent_id
    prev_agent = db.query(Agent).filter(Agent.id == prev_agent_id).first() if prev_agent_id else None
    if role == "admin" and prev_agent is not None:
        caller_agent_name = lookup_agent_display_name(db, prev_agent.id) or "Agent"

    conversation.agent_id = agent.id
    meta = conversation.conversation_metadata if isinstance(conversation.conversation_metadata, dict) else {}
    meta["last_transfer"] = {
        "from_agent_id": prev_agent_id,
        "from_agent_name": caller_agent_name,
        "to_agent_id": agent.id,
        "to_agent_name": lookup_agent_display_name(db, agent.id) or f"Agent {agent.id}",
        "at": datetime.utcnow().isoformat(),
    }
    conversation.conversation_metadata = meta
    conversation.updated_at = datetime.utcnow()
    db.add(conversation)
    db.commit()
    from services.agent_portal_service.broadcast import push_unread_summary, push_inbox_sync_event

    tid = conversation.tenant_id
    await push_unread_summary(db, tid, agent.id)
    await push_inbox_sync_event(
        db,
        tid,
        agent.id,
        {"type": "inbox_conversation_refresh", "conversation_id": conversation.id},
    )
    if prev_agent_id is not None and prev_agent_id != agent.id:
        await push_unread_summary(db, tid, prev_agent_id)
        await push_inbox_sync_event(
            db,
            tid,
            prev_agent_id,
            {"type": "inbox_conversation_refresh", "conversation_id": conversation.id},
        )
    # Backward-compatible transfer event for clients listening specifically for transfer actions.
    await push_inbox_sync_event(
        db,
        tid,
        agent.id,
        {"type": "conversation_transferred", "conversation_id": conversation.id},
    )
    if prev_agent_id is not None and prev_agent_id != agent.id:
        await push_inbox_sync_event(
            db,
            tid,
            prev_agent_id,
            {"type": "conversation_transferred", "conversation_id": conversation.id},
        )

    # Notify customer on WhatsApp (same wording as inbox system line when provided).
    if (conversation.channel or "").lower() == "whatsapp":
        customer = db.query(Customer).filter(Customer.id == conversation.customer_id).first()
        phone = customer.phone if customer else None
        wa = MetaWhatsAppClient()
        if phone and wa.is_configured():
            to_name = lookup_agent_display_name(db, agent.id) or f"Agent {agent.id}"
            if payload.customer_message and payload.customer_message.strip():
                transfer_note = payload.customer_message.strip()
            else:
                transfer_note = f"Conversation transferred to {to_name} by {caller_agent_name}."
            try:
                await wa.send_text_message(to_phone=str(phone), text=transfer_note[:4096])
            except Exception:
                # Keep transfer successful even if WhatsApp notification fails.
                pass

    return AssignResponse(
        conversation_id=conversation.id,
        agent_id=agent.id,
        reason="transfer",
    )
