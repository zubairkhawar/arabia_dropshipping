from datetime import datetime
from typing import List, Optional
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Agent,
    Tenant,
    User,
    Conversation,
    StoreAgentMapping,
    TeamMembership,
    TeamEvent,
    Notification,
    Team,
    InboxMessageReceipt,
    DmMessageReceipt,
    AgentAttendanceSession,
    TeamMessageReceipt,
    TeamChannelMemberReadState,
    ConversationAgentReadState,
    InternalDmMemberReadState,
    InternalDmConversation,
    InternalDmMessage,
    TeamAsset,
    TeamChannelMessage,
)
from services.auth_service.api import get_current_user, get_current_user_optional
from services.auth_service.services import get_password_hash
from services.agent_routing_service.api import (
    live_customer_conversation_count,
    live_customer_conversation_counts_for_tenant,
)


router = APIRouter()
NAME_PART_RE = re.compile(r"^[A-Za-z]+$")


def _normalize_full_name(value: str) -> str:
    parts = [p for p in value.strip().split(" ") if p]
    if len(parts) < 2:
        raise ValueError("First and last name are required")
    if len(parts) > 2:
        raise ValueError("Only first and last name are allowed")
    if not all(NAME_PART_RE.match(p) for p in parts):
        raise ValueError("Name can only contain alphabetic characters")
    return " ".join(p[:1].upper() + p[1:].lower() for p in parts)


def _normalize_profile_full_name(value: Optional[str]) -> Optional[str]:
    """Lenient name for PATCH (agent self-service profile); allows single word."""
    if value is None:
        return None
    s = " ".join(value.strip().split())
    if not s:
        raise ValueError("Name cannot be empty")
    if len(s) > 120:
        s = s[:120]
    return s


def _validate_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")
    if re.search(r"\s", value):
        raise ValueError("Password must not contain spaces")
    if not re.search(r"[A-Z]", value):
        raise ValueError("Password must include at least one uppercase letter")
    if not re.search(r"[a-z]", value):
        raise ValueError("Password must include at least one lowercase letter")
    if not re.search(r"\d", value):
        raise ValueError("Password must include at least one number")
    if not re.search(r"[^A-Za-z0-9]", value):
        raise ValueError("Password must include at least one special character")
    return value


class AgentOut(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str] = None
    status: str
    team: Optional[str] = None
    max_concurrent_chats: int = 5
    # Open (non-closed) customer threads currently assigned to this agent.
    live_customer_chats: int = 0
    accepting_chats: bool = True
    can_transfer_conversations: bool = True
    # Plaintext login password, kept so tenant admins can view/share credentials
    # from the admin panel across devices. Older agents created before this feature
    # will return None until their password is next reset.
    plaintext_password: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgentPasswordUpdate(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class AgentCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    tenant_id: int
    team: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        return _normalize_full_name(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class AgentUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    team: Optional[str] = None
    avatar_url: Optional[str] = None
    accepting_chats: Optional[bool] = None
    can_transfer_conversations: Optional[bool] = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_profile_full_name(value)


def _caller_is_tenant_admin(
    current_user: Optional[User], tenant_id: int
) -> bool:
    if current_user is None:
        return False
    if (getattr(current_user, "role", "") or "").lower() != "admin":
        return False
    return int(getattr(current_user, "tenant_id", 0) or 0) == int(tenant_id)


@router.get("", response_model=List[AgentOut])
async def list_agents(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    List all agents for a tenant with basic profile info.
    Plaintext passwords are only attached when the caller is a tenant admin.
    """
    rows = (
        db.query(Agent, User)
        .join(User, Agent.user_id == User.id)
        .filter(Agent.tenant_id == tenant_id)
        .all()
    )
    expose_passwords = _caller_is_tenant_admin(current_user, tenant_id)
    count_map = live_customer_conversation_counts_for_tenant(db, tenant_id)
    agents: List[AgentOut] = []
    for agent, user in rows:
        agents.append(
            AgentOut(
                id=agent.id,
                tenant_id=agent.tenant_id,
                user_id=agent.user_id,
                email=user.email,
                full_name=user.full_name,
                avatar_url=getattr(user, "avatar_url", None),
                status=agent.status,
                team=agent.team,
                max_concurrent_chats=int(agent.max_concurrent_chats or 5),
                live_customer_chats=int(count_map.get(agent.id, 0)),
                accepting_chats=bool(getattr(agent, "accepting_chats", True)),
                can_transfer_conversations=bool(
                    getattr(agent, "can_transfer_conversations", True)
                ),
                plaintext_password=(
                    getattr(agent, "plaintext_password", None) if expose_passwords else None
                ),
                created_at=agent.created_at,
            )
        )
    return agents


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    """
    Create a new agent (User with role=agent + Agent row).
    """
    normalized_email = (payload.email or "").strip().lower()
    existing = (
        db.query(User).filter(func.lower(User.email) == normalized_email).first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Email already in use")

    user = User(
        email=normalized_email,
        full_name=payload.full_name,
        tenant_id=payload.tenant_id,
        role="agent",
        hashed_password=get_password_hash(payload.password),
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.flush()

    tenant_row = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
    cap = 5
    if tenant_row is not None:
        tcap = getattr(tenant_row, "max_concurrent_chats_per_agent", None)
        if tcap is not None:
            cap = int(tcap)

    agent = Agent(
        tenant_id=payload.tenant_id,
        user_id=user.id,
        status="offline",
        team=payload.team,
        max_concurrent_chats=cap,
        accepting_chats=True,
        can_transfer_conversations=True,
        plaintext_password=payload.password,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(agent)
    db.flush()
    default_team_name = payload.team
    if payload.team:
        team = (
            db.query(Team)
            .filter(Team.tenant_id == payload.tenant_id, Team.name == payload.team)
            .first()
        )
        if team:
            exists = (
                db.query(TeamMembership)
                .filter(
                    TeamMembership.tenant_id == payload.tenant_id,
                    TeamMembership.team_id == team.id,
                    TeamMembership.agent_id == agent.id,
                )
                .first()
            )
            if not exists:
                db.add(
                    TeamMembership(
                        tenant_id=payload.tenant_id,
                        team_id=team.id,
                        agent_id=agent.id,
                        created_at=datetime.utcnow(),
                    )
                )
                default_team_name = team.name

    welcome_description = "You can switch your availability from Offline to Active when your shift starts."
    if default_team_name:
        welcome_description = (
            f"You are currently assigned to {default_team_name}. "
            "You can switch your availability from Offline to Active when your shift starts."
        )
    welcome_notif = Notification(
        tenant_id=payload.tenant_id,
        agent_id=agent.id,
        type="system_welcome",
        message="Welcome to Arabia Dropship Agent Panel",
        description=welcome_description,
        from_agent_id=None,
        conversation_id=None,
        read=False,
    )
    db.add(welcome_notif)
    db.commit()
    db.refresh(agent)
    db.refresh(welcome_notif)

    from services.agent_portal_service.broadcast import push_notification_event
    from services.agent_portal_service.unread_compute import build_unread_summary_dict

    notif_dict = {
        "id": welcome_notif.id,
        "type": welcome_notif.type,
        "message": welcome_notif.message,
        "description": welcome_notif.description,
        "from_agent_id": welcome_notif.from_agent_id,
        "conversation_id": welcome_notif.conversation_id,
        "created_at": welcome_notif.created_at,
        "read": welcome_notif.read,
    }
    summary = build_unread_summary_dict(db, payload.tenant_id, agent.id)
    await push_notification_event(payload.tenant_id, agent.id, notif_dict, summary)

    return AgentOut(
        id=agent.id,
        tenant_id=agent.tenant_id,
        user_id=agent.user_id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=getattr(user, "avatar_url", None),
        status=agent.status,
        team=agent.team,
        max_concurrent_chats=int(agent.max_concurrent_chats or 5),
        live_customer_chats=live_customer_conversation_count(db, agent.id),
        accepting_chats=bool(getattr(agent, "accepting_chats", True)),
        can_transfer_conversations=bool(
            getattr(agent, "can_transfer_conversations", True)
        ),
        plaintext_password=getattr(agent, "plaintext_password", None),
        created_at=agent.created_at,
    )


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: int,
    payload: AgentUpdate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Update basic agent fields (name, email, team).
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    user = db.query(User).filter(User.id == agent.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    data = payload.model_dump(exclude_unset=True)
    if "can_transfer_conversations" in data:
        if (
            current_user is None
            or (current_user.role or "").lower() != "admin"
            or current_user.tenant_id != agent.tenant_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only tenant admin can change transfer permission",
            )
        agent.can_transfer_conversations = bool(data["can_transfer_conversations"])
        del data["can_transfer_conversations"]
    if "accepting_chats" in data:
        if (
            current_user is None
            or (current_user.role or "").lower() != "admin"
            or current_user.tenant_id != agent.tenant_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only tenant admin can change accepting_chats",
            )
        agent.accepting_chats = bool(data["accepting_chats"])
        del data["accepting_chats"]
    if "email" in data:
        user.email = data["email"]
    if "full_name" in data:
        user.full_name = data["full_name"]
    if "team" in data:
        agent.team = data["team"]
    if "avatar_url" in data:
        user.avatar_url = data["avatar_url"]

    user.updated_at = datetime.utcnow()
    agent.updated_at = datetime.utcnow()

    db.add(user)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    db.refresh(user)

    return AgentOut(
        id=agent.id,
        tenant_id=agent.tenant_id,
        user_id=agent.user_id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=getattr(user, "avatar_url", None),
        status=agent.status,
        team=agent.team,
        max_concurrent_chats=int(agent.max_concurrent_chats or 5),
        live_customer_chats=live_customer_conversation_count(db, agent.id),
        accepting_chats=bool(getattr(agent, "accepting_chats", True)),
        can_transfer_conversations=bool(
            getattr(agent, "can_transfer_conversations", True)
        ),
        plaintext_password=getattr(agent, "plaintext_password", None),
        created_at=agent.created_at,
    )


@router.patch("/{agent_id}/password", response_model=AgentOut)
async def update_agent_password(
    agent_id: int,
    payload: AgentPasswordUpdate,
    db: Session = Depends(get_db),
):
    """
    Admin-only path to change an agent's login password. We store the new bcrypt
    hash for authentication *and* keep the plaintext on the agent row so the admin
    panel can show/copy it from any device.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    user = db.query(User).filter(User.id == agent.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = get_password_hash(payload.password)
    user.updated_at = datetime.utcnow()
    agent.plaintext_password = payload.password
    agent.updated_at = datetime.utcnow()

    db.add(user)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    db.refresh(user)

    return AgentOut(
        id=agent.id,
        tenant_id=agent.tenant_id,
        user_id=agent.user_id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=getattr(user, "avatar_url", None),
        status=agent.status,
        team=agent.team,
        max_concurrent_chats=int(agent.max_concurrent_chats or 5),
        live_customer_chats=live_customer_conversation_count(db, agent.id),
        accepting_chats=bool(getattr(agent, "accepting_chats", True)),
        can_transfer_conversations=bool(
            getattr(agent, "can_transfer_conversations", True)
        ),
        plaintext_password=getattr(agent, "plaintext_password", None),
        created_at=agent.created_at,
    )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    """
    Delete an agent account and revoke access.
    Safely detaches related references first, then removes Agent + User rows.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        return

    user = db.query(User).filter(User.id == agent.user_id).first()
    try:
        display_name = f"Agent {agent.id}"
        if user:
            dn = (user.full_name or user.email or "").strip()
            if dn:
                display_name = dn

        # Team channel history: record removal on each team before membership rows go away.
        memberships = (
            db.query(TeamMembership)
            .filter(TeamMembership.agent_id == agent.id)
            .all()
        )
        # Do not set target_agent_id to this agent — the row is not flushed yet, so the
        # later bulk UPDATE would miss it, and DELETE agent could CASCADE-remove the event.
        # Name for the soft timeline lives only in payload.
        for m in memberships:
            db.add(
                TeamEvent(
                    tenant_id=agent.tenant_id,
                    team_id=m.team_id,
                    event_type="member_removed",
                    actor_agent_id=None,
                    target_agent_id=None,
                    payload={
                        "removed_member_name": display_name,
                        "removed_via": "agent_deleted",
                    },
                    created_at=datetime.utcnow(),
                )
            )

        # Keep conversation history but unassign this deleted agent.
        db.query(Conversation).filter(Conversation.agent_id == agent.id).update(
            {Conversation.agent_id: None}, synchronize_session=False
        )

        # Remove mappings/memberships tied directly to this agent.
        db.query(StoreAgentMapping).filter(StoreAgentMapping.agent_id == agent.id).delete(
            synchronize_session=False
        )
        db.query(TeamMembership).filter(TeamMembership.agent_id == agent.id).delete(
            synchronize_session=False
        )

        # Keep event history; null out references to the deleted agent.
        db.query(TeamEvent).filter(TeamEvent.actor_agent_id == agent.id).update(
            {TeamEvent.actor_agent_id: None}, synchronize_session=False
        )
        db.query(TeamEvent).filter(TeamEvent.target_agent_id == agent.id).update(
            {TeamEvent.target_agent_id: None}, synchronize_session=False
        )

        # Notifications owned by this agent are no longer relevant after account deletion.
        db.query(Notification).filter(Notification.agent_id == agent.id).delete(
            synchronize_session=False
        )
        db.query(Notification).filter(Notification.from_agent_id == agent.id).update(
            {Notification.from_agent_id: None}, synchronize_session=False
        )

        # Delivery / read-state rows all reference agents.id as NOT NULL, so they must
        # be hard-deleted before the agent row can be removed.
        db.query(InboxMessageReceipt).filter(InboxMessageReceipt.agent_id == agent.id).delete(
            synchronize_session=False
        )
        db.query(TeamMessageReceipt).filter(TeamMessageReceipt.agent_id == agent.id).delete(
            synchronize_session=False
        )
        db.query(DmMessageReceipt).filter(
            DmMessageReceipt.recipient_agent_id == agent.id
        ).delete(synchronize_session=False)
        db.query(TeamChannelMemberReadState).filter(
            TeamChannelMemberReadState.agent_id == agent.id
        ).delete(synchronize_session=False)
        db.query(ConversationAgentReadState).filter(
            ConversationAgentReadState.agent_id == agent.id
        ).delete(synchronize_session=False)
        db.query(InternalDmMemberReadState).filter(
            InternalDmMemberReadState.agent_id == agent.id
        ).delete(synchronize_session=False)

        # Attendance sessions — drop the deleted agent's shift history.
        db.query(AgentAttendanceSession).filter(
            AgentAttendanceSession.agent_id == agent.id
        ).delete(synchronize_session=False)

        # Internal DMs: cascade-delete any thread where this agent is a participant,
        # along with their messages and remaining receipts / read states.
        dm_convo_ids = [
            row[0]
            for row in db.query(InternalDmConversation.id)
            .filter(
                (InternalDmConversation.agent_one_id == agent.id)
                | (InternalDmConversation.agent_two_id == agent.id)
            )
            .all()
        ]
        if dm_convo_ids:
            dm_message_ids = [
                row[0]
                for row in db.query(InternalDmMessage.id)
                .filter(InternalDmMessage.conversation_id.in_(dm_convo_ids))
                .all()
            ]
            if dm_message_ids:
                db.query(DmMessageReceipt).filter(
                    DmMessageReceipt.message_id.in_(dm_message_ids)
                ).delete(synchronize_session=False)
            db.query(InternalDmMessage).filter(
                InternalDmMessage.conversation_id.in_(dm_convo_ids)
            ).delete(synchronize_session=False)
            db.query(InternalDmMemberReadState).filter(
                InternalDmMemberReadState.conversation_id.in_(dm_convo_ids)
            ).delete(synchronize_session=False)
            db.query(InternalDmConversation).filter(
                InternalDmConversation.id.in_(dm_convo_ids)
            ).delete(synchronize_session=False)

        # Any DM messages *authored* by this agent in threads where they aren't a
        # participant (shouldn't happen, but guard for data integrity) must also go.
        db.query(InternalDmMessage).filter(
            InternalDmMessage.sender_agent_id == agent.id
        ).delete(synchronize_session=False)

        # Team channel messages / assets have nullable agent refs: preserve history.
        db.query(TeamChannelMessage).filter(
            TeamChannelMessage.sender_agent_id == agent.id
        ).update(
            {TeamChannelMessage.sender_agent_id: None}, synchronize_session=False
        )
        db.query(TeamAsset).filter(TeamAsset.created_by_agent_id == agent.id).update(
            {TeamAsset.created_by_agent_id: None}, synchronize_session=False
        )

        db.delete(agent)
        if user:
            db.delete(user)

        db.commit()
        return
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete agent due to related records: {exc.__class__.__name__}",
        )


@router.get("/me", response_model=AgentOut)
async def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Return agent profile for the currently authenticated user.
    """
    agent = (
        db.query(Agent)
        .filter(Agent.user_id == current_user.id, Agent.tenant_id == current_user.tenant_id)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found for current user")

    return AgentOut(
        id=agent.id,
        tenant_id=agent.tenant_id,
        user_id=agent.user_id,
        email=current_user.email,
        full_name=current_user.full_name,
        avatar_url=getattr(current_user, "avatar_url", None),
        status=agent.status,
        team=agent.team,
        max_concurrent_chats=int(agent.max_concurrent_chats or 5),
        live_customer_chats=live_customer_conversation_count(db, agent.id),
        accepting_chats=bool(getattr(agent, "accepting_chats", True)),
        can_transfer_conversations=bool(
            getattr(agent, "can_transfer_conversations", True)
        ),
        plaintext_password=getattr(agent, "plaintext_password", None),
        created_at=agent.created_at,
    )

