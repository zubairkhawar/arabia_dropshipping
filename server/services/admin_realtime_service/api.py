"""
Admin WebSocket endpoint. Auth via JWT in query param (matches agent portal pattern).
Pushes template/campaign lifecycle events for the admin's tenant.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import User
from services.admin_realtime_service.hub import admin_hub

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.websocket("/ws")
async def admin_realtime_ws(websocket: WebSocket):
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
        if (user.role or "").lower() != "admin":
            await websocket.close(code=4403)
            return
    finally:
        db.close()

    await websocket.accept()
    await admin_hub.connect(websocket, tenant_id)
    try:
        await websocket.send_json({"type": "ready", "tenant_id": tenant_id})
        while True:
            # Server pushes events; we just keep the connection alive and drain pings.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("admin_realtime_ws receive loop failed")
    finally:
        await admin_hub.disconnect(websocket, tenant_id)
