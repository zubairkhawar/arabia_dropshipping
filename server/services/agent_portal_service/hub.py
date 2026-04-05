"""
Single WebSocket per logged-in agent (tenant_id + agent_id room).
Push: unread_summary, inbox_message, notification, refresh_unread.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import WebSocket


class AgentPortalHub:
    _instance: Optional["AgentPortalHub"] = None

    def __new__(cls) -> "AgentPortalHub":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._rooms: Dict[str, List[Tuple[WebSocket, Dict[str, Any]]]] = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    @staticmethod
    def room_key(tenant_id: int, agent_id: int) -> str:
        return f"{tenant_id}:{agent_id}"

    async def connect(self, websocket: WebSocket, tenant_id: int, agent_id: int) -> None:
        key = self.room_key(tenant_id, agent_id)
        async with self._lock:
            self._rooms.setdefault(key, []).append((websocket, {}))

    async def disconnect(self, websocket: WebSocket, tenant_id: int, agent_id: int) -> None:
        key = self.room_key(tenant_id, agent_id)
        async with self._lock:
            lst = self._rooms.get(key, [])
            self._rooms[key] = [(w, m) for w, m in lst if w is not websocket]
            if not self._rooms[key]:
                del self._rooms[key]

    async def broadcast_json(self, tenant_id: int, agent_id: int, payload: Dict[str, Any]) -> None:
        key = self.room_key(tenant_id, agent_id)
        async with self._lock:
            conns = list(self._rooms.get(key, []))
        stale: List[WebSocket] = []
        text = json.dumps(payload, default=str)
        for ws, _ in conns:
            try:
                await ws.send_text(text)
            except Exception:
                stale.append(ws)
        if stale:
            async with self._lock:
                lst = self._rooms.get(key, [])
                if lst:
                    self._rooms[key] = [(w, m) for w, m in lst if w not in stale]
                    if not self._rooms[key]:
                        del self._rooms[key]


hub = AgentPortalHub()
