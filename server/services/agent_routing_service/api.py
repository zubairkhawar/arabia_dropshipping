from typing import List, Optional
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database import get_db
from models import Agent, Conversation, Customer, Store, StoreAgentMapping


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


class AssignResponse(BaseModel):
    conversation_id: int
    agent_id: Optional[int]
    reason: str


class TransferRequest(BaseModel):
    conversation_id: int
    target_agent_id: Optional[int] = None
    target_team: Optional[str] = None


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

    agent.status = payload.status.value
    if payload.max_concurrent_chats is not None:
        agent.max_concurrent_chats = payload.max_concurrent_chats
    if payload.team is not None:
        agent.team = payload.team

    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


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
    """Pick a random online agent, optionally filtered by team."""
    query = db.query(Agent).filter(
        Agent.tenant_id == tenant_id,
        Agent.status == AgentStatus.online.value,
    )
    if team:
        query = query.filter(Agent.team == team)

    agents = query.all()
    if not agents:
        return None

    # Use database random ordering for simple load balancing
    agent = (
        query.order_by(func.random())  # type: ignore[arg-type]
        .limit(1)
        .first()
    )
    return agent


@router.post("/assign", response_model=AssignResponse)
async def assign_conversation(payload: AssignRequest, db: Session = Depends(get_db)):
    """
    Assign conversation to an available agent following routing rules:

    1. Old customer → previous agent if exists.
    2. Store mapped to an agent → mapped agent.
    3. Otherwise → random online agent in routed team (if provided) or any team.
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # If conversation already has an agent, keep ownership
    if conversation.agent_id:
        return AssignResponse(
            conversation_id=conversation.id,
            agent_id=conversation.agent_id,
            reason="conversation_already_assigned",
        )

    # Case 1: Old customer → previous agent
    previous_agent = _get_previous_agent_for_customer(
        db, payload.tenant_id, payload.customer_id
    )
    if previous_agent:
        conversation.agent_id = previous_agent.id
        db.add(conversation)
        db.commit()
        return AssignResponse(
            conversation_id=conversation.id,
            agent_id=previous_agent.id,
            reason="previous_agent_for_customer",
        )

    # Case 3: Store-based mapping
    mapped_agent = _get_store_mapped_agent(db, payload.tenant_id, payload.store_id)
    if mapped_agent:
        conversation.agent_id = mapped_agent.id
        db.add(conversation)
        db.commit()
        return AssignResponse(
            conversation_id=conversation.id,
            agent_id=mapped_agent.id,
            reason="store_mapped_agent",
        )

    # Case 2/4: New customer or no mapping → random available agent
    candidate = _get_random_available_agent(
        db, payload.tenant_id, team=payload.routed_team
    )
    if not candidate:
        # No available agent, handler stays with AI
        return AssignResponse(
            conversation_id=conversation.id,
            agent_id=None,
            reason="no_available_agent",
        )

    conversation.agent_id = candidate.id
    db.add(conversation)
    db.commit()

    return AssignResponse(
        conversation_id=conversation.id,
        agent_id=candidate.id,
        reason="random_available_agent",
    )


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

    conversation.agent_id = agent.id
    db.add(conversation)
    db.commit()

    return AssignResponse(
        conversation_id=conversation.id,
        agent_id=agent.id,
        reason="transfer",
    )
