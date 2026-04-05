from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import or_, desc
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from models import (
    Agent,
    InternalDmConversation,
    InternalDmMessage,
    InternalDmMemberReadState,
    MessageUserDeletion,
    User,
)
from services.auth_service.api import get_current_user, get_current_user_optional
from services.internal_dm_service.dm_hub import hub

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
    reply_to_message_id: Optional[int] = None
    edited_at: Optional[datetime] = None
    deleted_for_everyone_at: Optional[datetime] = None


class DmMessagesPage(BaseModel):
    messages: List[DmMessageOut]
    has_more_older: bool


class FindOrCreateConversationIn(BaseModel):
    tenant_id: int
    agent_id: int
    peer_agent_id: int


class CreateDmMessageIn(BaseModel):
    conversation_id: int
    sender_agent_id: int
    content: str
    reply_to_message_id: Optional[int] = None


class PatchDmMessageIn(BaseModel):
    tenant_id: int
    conversation_id: int
    content: str


class DmReadStateIn(BaseModel):
    tenant_id: int
    agent_id: int
    last_read_message_id: int


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def _peer_for(conversation: InternalDmConversation, agent_id: int) -> int:
    return conversation.agent_two_id if conversation.agent_one_id == agent_id else conversation.agent_one_id


def _decode_websocket_user(token: str, db: Session) -> Optional[User]:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        email = payload.get("sub")
        if not email:
            return None
        return (
            db.query(User)
            .filter(User.email == email, User.is_active.is_(True))
            .first()
        )
    except JWTError:
        return None


def _dm_message_to_out(m: InternalDmMessage) -> DmMessageOut:
    deleted = bool(m.deleted_for_everyone_at)
    text = "[Message deleted]" if deleted else m.content
    return DmMessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        sender_agent_id=m.sender_agent_id,
        content=text,
        created_at=m.created_at,
        reply_to_message_id=m.reply_to_message_id,
        edited_at=m.edited_at,
        deleted_for_everyone_at=m.deleted_for_everyone_at,
    )


def _hidden_dm_message_ids(db: Session, user_id: int, mids: List[int]) -> set[int]:
    if not mids:
        return set()
    rows = (
        db.query(MessageUserDeletion.message_id)
        .filter(
            MessageUserDeletion.user_id == user_id,
            MessageUserDeletion.channel == "dm",
            MessageUserDeletion.message_id.in_(mids),
        )
        .all()
    )
    return {x[0] for x in rows}


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


@router.get("/conversations/{conversation_id}/messages", response_model=DmMessagesPage)
async def list_messages(
    conversation_id: int,
    agent_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[int] = Query(None, description="Load older messages with id strictly less than this"),
    since: Optional[datetime] = Query(None, description="Messages strictly after this time (reconnect gap fill)"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    conversation = db.query(InternalDmConversation).filter(InternalDmConversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if agent_id not in (conversation.agent_one_id, conversation.agent_two_id):
        raise HTTPException(status_code=403, detail="Access denied")

    base = db.query(InternalDmMessage).filter(InternalDmMessage.conversation_id == conversation_id)

    def _filter_hidden(raw: List[InternalDmMessage]) -> List[InternalDmMessage]:
        if current_user is None or not raw:
            return raw
        if current_user.tenant_id != conversation.tenant_id:
            return raw
        ag = (
            db.query(Agent)
            .filter(Agent.user_id == current_user.id, Agent.tenant_id == conversation.tenant_id)
            .first()
        )
        if not ag or ag.id != agent_id:
            return raw
        hidden = _hidden_dm_message_ids(db, current_user.id, [m.id for m in raw])
        return [m for m in raw if m.id not in hidden]

    if since is not None:
        rows = (
            base.filter(InternalDmMessage.created_at > since)
            .order_by(InternalDmMessage.created_at.asc())
            .limit(500)
            .all()
        )
        rows = _filter_hidden(rows)
        return DmMessagesPage(messages=[_dm_message_to_out(m) for m in rows], has_more_older=False)

    lim = max(1, min(limit, 200))
    if before_id is not None:
        rows_desc = (
            base.filter(InternalDmMessage.id < before_id)
            .order_by(desc(InternalDmMessage.id))
            .limit(lim)
            .all()
        )
        rows = list(reversed(rows_desc))
        rows = _filter_hidden(rows)
        min_id = rows[0].id if rows else before_id
        older = (
            db.query(InternalDmMessage.id)
            .filter(
                InternalDmMessage.conversation_id == conversation_id,
                InternalDmMessage.id < min_id,
            )
            .first()
        )
        return DmMessagesPage(
            messages=[_dm_message_to_out(m) for m in rows], has_more_older=older is not None
        )

    rows_desc = base.order_by(desc(InternalDmMessage.id)).limit(lim).all()
    rows = list(reversed(rows_desc))
    rows = _filter_hidden(rows)
    min_id = rows[0].id if rows else None
    older = None
    if min_id is not None:
        older = (
            db.query(InternalDmMessage.id)
            .filter(
                InternalDmMessage.conversation_id == conversation_id,
                InternalDmMessage.id < min_id,
            )
            .first()
        )
    return DmMessagesPage(messages=[_dm_message_to_out(m) for m in rows], has_more_older=older is not None)


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
    reply_to_id = payload.reply_to_message_id
    if reply_to_id is not None:
        parent = (
            db.query(InternalDmMessage)
            .filter(
                InternalDmMessage.id == reply_to_id,
                InternalDmMessage.conversation_id == payload.conversation_id,
            )
            .first()
        )
        if not parent:
            raise HTTPException(status_code=400, detail="Invalid reply_to_message_id")

    msg = InternalDmMessage(
        conversation_id=payload.conversation_id,
        sender_agent_id=payload.sender_agent_id,
        content=text,
        created_at=datetime.utcnow(),
        reply_to_message_id=reply_to_id,
    )
    conversation.updated_at = datetime.utcnow()
    db.add(msg)
    db.add(conversation)
    db.commit()
    db.refresh(msg)
    out = _dm_message_to_out(msg)
    await hub.broadcast_json(
        conversation.tenant_id,
        conversation.id,
        {"type": "NEW_DM_MESSAGE", "message": out.model_dump(mode="json")},
    )
    from services.agent_portal_service.broadcast import push_refresh_unread

    for aid in (conversation.agent_one_id, conversation.agent_two_id):
        if aid != payload.sender_agent_id:
            await push_refresh_unread(db, conversation.tenant_id, aid)
    return out


@router.patch("/messages/{message_id}", response_model=DmMessageOut)
async def patch_dm_message(
    message_id: int,
    payload: PatchDmMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    ag = (
        db.query(Agent)
        .filter(Agent.user_id == current_user.id, Agent.tenant_id == payload.tenant_id)
        .first()
    )
    if not ag:
        raise HTTPException(status_code=403, detail="Forbidden")
    conversation = (
        db.query(InternalDmConversation)
        .filter(InternalDmConversation.id == payload.conversation_id)
        .first()
    )
    if not conversation or conversation.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if ag.id not in (conversation.agent_one_id, conversation.agent_two_id):
        raise HTTPException(status_code=403, detail="Access denied")
    row = (
        db.query(InternalDmMessage)
        .filter(
            InternalDmMessage.id == message_id,
            InternalDmMessage.conversation_id == payload.conversation_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    if row.deleted_for_everyone_at:
        raise HTTPException(status_code=400, detail="Message was deleted")
    if row.sender_agent_id != ag.id:
        raise HTTPException(status_code=403, detail="Cannot edit this message")
    new_text = (payload.content or "").strip()
    if not new_text:
        raise HTTPException(status_code=400, detail="Message content is required")
    row.content = new_text
    row.edited_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    out = _dm_message_to_out(row)
    await hub.broadcast_json(
        conversation.tenant_id,
        conversation.id,
        {"type": "DM_MESSAGE_UPDATED", "message": out.model_dump(mode="json")},
    )
    return out


@router.delete("/messages/{message_id}/for-me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dm_message_for_me(
    message_id: int,
    tenant_id: int = Query(...),
    conversation_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    ag = db.query(Agent).filter(Agent.user_id == current_user.id, Agent.tenant_id == tenant_id).first()
    if not ag:
        raise HTTPException(status_code=403, detail="Forbidden")
    conversation = (
        db.query(InternalDmConversation)
        .filter(InternalDmConversation.id == conversation_id, InternalDmConversation.tenant_id == tenant_id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if ag.id not in (conversation.agent_one_id, conversation.agent_two_id):
        raise HTTPException(status_code=403, detail="Access denied")
    row = (
        db.query(InternalDmMessage)
        .filter(InternalDmMessage.id == message_id, InternalDmMessage.conversation_id == conversation_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    exists = (
        db.query(MessageUserDeletion)
        .filter(
            MessageUserDeletion.message_id == message_id,
            MessageUserDeletion.user_id == current_user.id,
            MessageUserDeletion.channel == "dm",
        )
        .first()
    )
    if not exists:
        db.add(
            MessageUserDeletion(
                channel="dm",
                message_id=message_id,
                user_id=current_user.id,
                deleted_by_role=(current_user.role or "").lower(),
            )
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/messages/{message_id}/for-everyone", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dm_message_for_everyone(
    message_id: int,
    tenant_id: int = Query(...),
    conversation_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    ag = db.query(Agent).filter(Agent.user_id == current_user.id, Agent.tenant_id == tenant_id).first()
    if not ag:
        raise HTTPException(status_code=403, detail="Forbidden")
    conversation = (
        db.query(InternalDmConversation)
        .filter(InternalDmConversation.id == conversation_id, InternalDmConversation.tenant_id == tenant_id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if ag.id not in (conversation.agent_one_id, conversation.agent_two_id):
        raise HTTPException(status_code=403, detail="Access denied")
    row = (
        db.query(InternalDmMessage)
        .filter(InternalDmMessage.id == message_id, InternalDmMessage.conversation_id == conversation_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    if row.deleted_for_everyone_at:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if row.sender_agent_id != ag.id:
        raise HTTPException(status_code=403, detail="Cannot delete this message for everyone")
    if (datetime.utcnow() - row.created_at).total_seconds() > 300:
        raise HTTPException(status_code=403, detail="Cannot delete this message for everyone")
    row.content = "[Message deleted]"
    row.deleted_for_everyone_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    out = _dm_message_to_out(row)
    await hub.broadcast_json(
        conversation.tenant_id,
        conversation.id,
        {"type": "DM_MESSAGE_UPDATED", "message": out.model_dump(mode="json")},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)




@router.post("/conversations/{conversation_id}/read-state")
async def upsert_dm_read_state(
    conversation_id: int,
    payload: DmReadStateIn,
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(InternalDmConversation).filter(InternalDmConversation.id == conversation_id).first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if payload.tenant_id != conversation.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant mismatch")
    if payload.agent_id not in (conversation.agent_one_id, conversation.agent_two_id):
        raise HTTPException(status_code=403, detail="Access denied")
    row = (
        db.query(InternalDmMemberReadState)
        .filter(
            InternalDmMemberReadState.tenant_id == payload.tenant_id,
            InternalDmMemberReadState.conversation_id == conversation_id,
            InternalDmMemberReadState.agent_id == payload.agent_id,
        )
        .first()
    )
    v = max(0, payload.last_read_message_id)
    if row is None:
        row = InternalDmMemberReadState(
            tenant_id=payload.tenant_id,
            conversation_id=conversation_id,
            agent_id=payload.agent_id,
            last_read_message_id=v,
        )
        db.add(row)
    else:
        row.last_read_message_id = max(row.last_read_message_id, v)
        db.add(row)
    db.commit()
    from services.agent_portal_service.broadcast import push_refresh_unread

    await push_refresh_unread(db, payload.tenant_id, payload.agent_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.websocket("/ws/conversation/{conversation_id}")
async def internal_dm_websocket(websocket: WebSocket, conversation_id: int):
    qp = websocket.query_params
    try:
        tenant_id = int(qp.get("tenant_id") or "0")
    except (TypeError, ValueError):
        await websocket.close(code=4400)
        return
    token = (qp.get("token") or "").strip()
    agent_id_raw = (qp.get("agent_id") or "").strip()
    if tenant_id < 1 or not token or not agent_id_raw:
        await websocket.close(code=4400)
        return
    try:
        agent_id = int(agent_id_raw, 10)
    except ValueError:
        await websocket.close(code=4400)
        return

    db = SessionLocal()
    try:
        user = _decode_websocket_user(token, db)
        if user is None or user.tenant_id != tenant_id:
            await websocket.close(code=4401)
            return
        ag = (
            db.query(Agent)
            .filter(Agent.user_id == user.id, Agent.tenant_id == tenant_id)
            .first()
        )
        if not ag or ag.id != agent_id:
            await websocket.close(code=4403)
            return
        conversation = (
            db.query(InternalDmConversation)
            .filter(InternalDmConversation.id == conversation_id, InternalDmConversation.tenant_id == tenant_id)
            .first()
        )
        if not conversation:
            await websocket.close(code=4404)
            return
        if agent_id not in (conversation.agent_one_id, conversation.agent_two_id):
            await websocket.close(code=4403)
            return
    finally:
        db.close()

    await websocket.accept()
    meta = {"agent_id": agent_id}
    await hub.connect(websocket, tenant_id, conversation_id, meta)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(websocket, tenant_id, conversation_id)

