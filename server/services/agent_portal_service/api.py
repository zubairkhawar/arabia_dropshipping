import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from models import User
from services.auth_service.api import get_current_user
from services.agent_portal_service.hub import hub
from services.agent_portal_service.unread_compute import (
    build_unread_summary_dict,
    resolve_agent_id_for_user,
)

router = APIRouter()


class UnreadSummaryOut(BaseModel):
    inbox: int
    team_channel: int
    dm: int


class InboxReadStateIn(BaseModel):
    tenant_id: int
    conversation_id: int
    last_read_message_id: int


def _decode_ws_user(token: str, db: Session) -> Optional[User]:
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


@router.get("/unread-summary", response_model=UnreadSummaryOut)
async def get_unread_summary(
    tenant_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    role = (current_user.role or "").lower()
    if role != "agent":
        raise HTTPException(status_code=403, detail="Agents only")
    ag_id = resolve_agent_id_for_user(db, tenant_id, current_user.id)
    if not ag_id:
        raise HTTPException(status_code=403, detail="Not an agent")
    data = build_unread_summary_dict(db, tenant_id, ag_id)
    return UnreadSummaryOut(**data)


@router.post("/inbox/read-state")
async def upsert_inbox_read_state(
    payload: InboxReadStateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    role = (current_user.role or "").lower()
    if role != "agent":
        raise HTTPException(status_code=403, detail="Agents only")
    ag_id = resolve_agent_id_for_user(db, payload.tenant_id, current_user.id)
    if not ag_id:
        raise HTTPException(status_code=403, detail="Not an agent")

    from models import Conversation, ConversationAgentReadState

    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == payload.conversation_id,
            Conversation.tenant_id == payload.tenant_id,
            Conversation.agent_id == ag_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    row = (
        db.query(ConversationAgentReadState)
        .filter(
            ConversationAgentReadState.tenant_id == payload.tenant_id,
            ConversationAgentReadState.conversation_id == payload.conversation_id,
            ConversationAgentReadState.agent_id == ag_id,
        )
        .first()
    )
    v = max(0, payload.last_read_message_id)
    if row is None:
        row = ConversationAgentReadState(
            tenant_id=payload.tenant_id,
            conversation_id=payload.conversation_id,
            agent_id=ag_id,
            last_read_message_id=v,
        )
        db.add(row)
    else:
        row.last_read_message_id = max(row.last_read_message_id, v)
        db.add(row)

    from services.messaging_service.inbox_receipts import mark_read_through

    mark_read_through(db, payload.conversation_id, ag_id, v)
    db.commit()

    from services.agent_portal_service.broadcast import push_unread_summary

    await push_unread_summary(db, payload.tenant_id, ag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.websocket("/ws")
async def agent_portal_websocket(websocket: WebSocket):
    qp = websocket.query_params
    try:
        tenant_id = int(qp.get("tenant_id") or "0")
    except (TypeError, ValueError):
        await websocket.close(code=4400)
        return
    token = (qp.get("token") or "").strip()
    if tenant_id < 1 or not token:
        await websocket.close(code=4400)
        return

    db = SessionLocal()
    try:
        user = _decode_ws_user(token, db)
        if user is None or user.tenant_id != tenant_id:
            await websocket.close(code=4401)
            return
        role = (user.role or "").lower()
        if role != "agent":
            await websocket.close(code=4403)
            return
        ag_id = resolve_agent_id_for_user(db, tenant_id, user.id)
        if not ag_id:
            await websocket.close(code=4403)
            return
    finally:
        db.close()

    await websocket.accept()
    await hub.connect(websocket, tenant_id, ag_id)
    db2 = SessionLocal()
    try:
        snap = build_unread_summary_dict(db2, tenant_id, ag_id)
        await websocket.send_json({"type": "unread_summary", **snap})
    finally:
        db2.close()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                body: Any = json.loads(raw)
            except Exception:
                continue
            if not isinstance(body, dict):
                continue
            if body.get("type") == "delivery_ack" and body.get("channel") == "inbox":
                ids_raw = body.get("message_ids") or []
                mids = [int(x) for x in ids_raw if str(x).isdigit()]
                if not mids:
                    continue
                db_ack = SessionLocal()
                try:
                    from services.messaging_service.inbox_receipts import mark_delivered

                    mark_delivered(db_ack, mids, ag_id)
                    db_ack.commit()
                finally:
                    db_ack.close()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(websocket, tenant_id, ag_id)
