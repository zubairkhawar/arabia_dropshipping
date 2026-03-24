from datetime import datetime
from typing import List, Optional
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Agent,
    User,
    Conversation,
    StoreAgentMapping,
    TeamMembership,
    TeamEvent,
    Notification,
)
from services.auth_service.api import get_current_user
from services.auth_service.services import get_password_hash


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
    created_at: datetime

    class Config:
        from_attributes = True


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

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _normalize_full_name(value)


@router.get("", response_model=List[AgentOut])
async def list_agents(tenant_id: int, db: Session = Depends(get_db)):
    """
    List all agents for a tenant with basic profile info.
    """
    rows = (
        db.query(Agent, User)
        .join(User, Agent.user_id == User.id)
        .filter(Agent.tenant_id == tenant_id)
        .all()
    )
    agents: List[AgentOut] = []
    for agent, user in rows:
        agents.append(
            AgentOut(
                id=agent.id,
                tenant_id=agent.tenant_id,
                user_id=agent.user_id,
                email=user.email,
                full_name=user.full_name,
                status=agent.status,
                team=agent.team,
                created_at=agent.created_at,
            )
        )
    return agents


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    """
    Create a new agent (User with role=agent + Agent row).
    """
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already in use")

    user = User(
        email=payload.email,
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

    agent = Agent(
        tenant_id=payload.tenant_id,
        user_id=user.id,
        status="offline",
        team=payload.team,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    return AgentOut(
        id=agent.id,
        tenant_id=agent.tenant_id,
        user_id=agent.user_id,
        email=user.email,
        full_name=user.full_name,
        status=agent.status,
        team=agent.team,
        created_at=agent.created_at,
    )


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db)):
    """
    Update basic agent fields (name, email, team).
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    user = db.query(User).filter(User.id == agent.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.email is not None:
        user.email = payload.email
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.team is not None:
        agent.team = payload.team

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
        status=agent.status,
        team=agent.team,
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

        db.delete(agent)
        if user:
            db.delete(user)

        db.commit()
        return
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to delete agent due to related records",
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
        status=agent.status,
        team=agent.team,
        created_at=agent.created_at,
    )

