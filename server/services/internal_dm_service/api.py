from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, or_, desc
from sqlalchemy.orm import Session

from database import get_db
from models import Agent, User, InternalDmConversation, InternalDmMessage

router = APIRouter()


class DmPeerOut(BaseModel):
    agent_id: int
    name: str


class DmConversationOut(BaseModel):
    id: int
    tenant_id: int
    peer: DmPeerOut
    last_message_at: Optional[datetime] = None


class DmMessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_agent_id: int
    content: str
    created_at: datetime


class FindOrCreateConversationIn(BaseModel):
    tenant_id: int
    agent_id: int
    peer_agent_id: int


class CreateDmMessageIn(BaseModel):
    conversation_id: int
    sender_agent_id: int
    content: str


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def _peer_for(conversation: InternalDmConversation, agent_id: int) -> int:
    return conversation.agent_two_id if conversation.agent_one_id == agent_id else conversation.agent_one_id


def _agent_display_name(db: Session, agent_id: int) -> str:
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        return f"Agent {agent_id}"
    user = db.query(User).filter(User.id == agent.user_id).first()
    if user and user.full_name:
        return user.full_name
    if user and user.email:
        return user.email.split("@")[0]
    return f"Agent {agent_id}"


@router.post("/conversations/find-or-create", response_model=DmConversationOut)
async def find_or_create_conversation(payload: FindOrCreateConversationIn, db: Session = Depends(get_db)):
    if payload.agent_id == payload.peer_agent_id:
        raise HTTPException(status_code=400, detail="Cannot create DM with self")

    one, two = _pair(payload.agent_id, payload.peer_agent_id)
    conversation = (
        db.query(InternalDmConversation)
        .filter(
            InternalDmConversation.tenant_id == payload.tenant_id,
            InternalDmConversation.agent_one_id == one,
            InternalDmConversation.agent_two_id == two,
        )
        .first()
    )
    if not conversation:
        conversation = InternalDmConversation(
            tenant_id=payload.tenant_id,
            agent_one_id=one,
            agent_two_id=two,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    peer_id = _peer_for(conversation, payload.agent_id)
    last_msg = (
        db.query(InternalDmMessage)
        .filter(InternalDmMessage.conversation_id == conversation.id)
        .order_by(desc(InternalDmMessage.created_at))
        .first()
    )
    return DmConversationOut(
        id=conversation.id,
        tenant_id=conversation.tenant_id,
        peer=DmPeerOut(agent_id=peer_id, name=_agent_display_name(db, peer_id)),
        last_message_at=last_msg.created_at if last_msg else conversation.updated_at,
    )


@router.get("/conversations", response_model=List[DmConversationOut])
async def list_conversations(
    tenant_id: int = Query(...),
    agent_id: int = Query(...),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(InternalDmConversation)
        .filter(
            InternalDmConversation.tenant_id == tenant_id,
            or_(
                InternalDmConversation.agent_one_id == agent_id,
                InternalDmConversation.agent_two_id == agent_id,
            ),
        )
        .order_by(desc(InternalDmConversation.updated_at))
        .all()
    )

    result: List[DmConversationOut] = []
    for c in rows:
        peer_id = _peer_for(c, agent_id)
        last_msg = (
            db.query(InternalDmMessage)
            .filter(InternalDmMessage.conversation_id == c.id)
            .order_by(desc(InternalDmMessage.created_at))
            .first()
        )
        result.append(
            DmConversationOut(
                id=c.id,
                tenant_id=c.tenant_id,
                peer=DmPeerOut(agent_id=peer_id, name=_agent_display_name(db, peer_id)),
                last_message_at=last_msg.created_at if last_msg else c.updated_at,
            )
        )
    return result


@router.get("/conversations/{conversation_id}/messages", response_model=List[DmMessageOut])
async def list_messages(
    conversation_id: int,
    agent_id: int = Query(...),
    db: Session = Depends(get_db),
):
    conversation = db.query(InternalDmConversation).filter(InternalDmConversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if agent_id not in (conversation.agent_one_id, conversation.agent_two_id):
        raise HTTPException(status_code=403, detail="Access denied")

    rows = (
        db.query(InternalDmMessage)
        .filter(InternalDmMessage.conversation_id == conversation_id)
        .order_by(InternalDmMessage.created_at.asc())
        .all()
    )
    return [
        DmMessageOut(
            id=m.id,
            conversation_id=m.conversation_id,
            sender_agent_id=m.sender_agent_id,
            content=m.content,
            created_at=m.created_at,
        )
        for m in rows
    ]


@router.post("/messages", response_model=DmMessageOut, status_code=status.HTTP_201_CREATED)
async def create_message(payload: CreateDmMessageIn, db: Session = Depends(get_db)):
    conversation = db.query(InternalDmConversation).filter(InternalDmConversation.id == payload.conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if payload.sender_agent_id not in (conversation.agent_one_id, conversation.agent_two_id):
        raise HTTPException(status_code=403, detail="Access denied")
    text = (payload.content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message content is required")

    msg = InternalDmMessage(
        conversation_id=payload.conversation_id,
        sender_agent_id=payload.sender_agent_id,
        content=text,
        created_at=datetime.utcnow(),
    )
    conversation.updated_at = datetime.utcnow()
    db.add(msg)
    db.add(conversation)
    db.commit()
    db.refresh(msg)
    return DmMessageOut(
        id=msg.id,
        conversation_id=msg.conversation_id,
        sender_agent_id=msg.sender_agent_id,
        content=msg.content,
        created_at=msg.created_at,
    )

