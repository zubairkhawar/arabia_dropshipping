"""
Admin WebSocket hub. One room per tenant — every admin client connected for that
tenant receives broadcast/template lifecycle events. Push-only (server → client).

Event types pushed:
    template_status_update — {type, template_id, name, language, status, rejection_reason}
    campaign_status_update — {type, campaign_id, status, sent_count, failed_count, recipient_count}
    recipient_status_update — {type, campaign_id, recipient_id, phone, status, error_message}
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from fastapi import WebSocket


class AdminRealtimeHub:
    _instance: Optional["AdminRealtimeHub"] = None

    def __new__(cls) -> "AdminRealtimeHub":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._rooms: Dict[int, List[WebSocket]] = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    async def connect(self, websocket: WebSocket, tenant_id: int) -> None:
        async with self._lock:
            self._rooms.setdefault(tenant_id, []).append(websocket)

    async def disconnect(self, websocket: WebSocket, tenant_id: int) -> None:
        async with self._lock:
            lst = self._rooms.get(tenant_id, [])
            self._rooms[tenant_id] = [w for w in lst if w is not websocket]
            if not self._rooms[tenant_id]:
                del self._rooms[tenant_id]

    async def broadcast_json(self, tenant_id: int, payload: Dict[str, Any]) -> None:
        async with self._lock:
            conns = list(self._rooms.get(tenant_id, []))
        if not conns:
            return
        text = json.dumps(payload, default=str)
        stale: List[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception:
                stale.append(ws)
        if stale:
            async with self._lock:
                lst = self._rooms.get(tenant_id, [])
                if lst:
                    self._rooms[tenant_id] = [w for w in lst if w not in stale]
                    if not self._rooms[tenant_id]:
                        del self._rooms[tenant_id]


admin_hub = AdminRealtimeHub()


def push_event_threadsafe(tenant_id: int, payload: Dict[str, Any]) -> None:
    """
    Push from sync contexts (background threads, sync DB callbacks) by scheduling
    the coroutine on the running event loop. No-op if no loop is available.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    if loop is None or not loop.is_running():
        return
    asyncio.run_coroutine_threadsafe(admin_hub.broadcast_json(tenant_id, payload), loop)
