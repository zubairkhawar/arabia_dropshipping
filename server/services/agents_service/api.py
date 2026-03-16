from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db
from models import Agent, User
from services.auth_service.api import get_current_user
from services.auth_service.services import get_password_hash


router = APIRouter()


class AgentOut(BaseModel):
    id: int
    tenant_id: int
    user_id: int
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str] = None
    status: str
    team: Optional[str] = None

    class Config:
        from_attributes = True


class AgentCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    tenant_id: int
    team: Optional[str] = None


class AgentUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    team: Optional[str] = None
    avatar_url: Optional[str] = None


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
    )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    """
    Deactivate an agent safely.
    Keeps Agent row for history, marks user inactive and agent offline.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        return

    user = db.query(User).filter(User.id == agent.user_id).first()
    if user:
        user.is_active = False
        user.updated_at = datetime.utcnow()
        db.add(user)

    agent.status = "offline"
    agent.updated_at = datetime.utcnow()
    db.add(agent)

    db.commit()
    return


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
    )

