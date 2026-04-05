"""
In-process WebSocket hub for team channel rooms (one server instance).
For horizontal scaling, replace with Redis pub/sub.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple

from fastapi import WebSocket


class TeamChannelHub:
    _instance: Optional["TeamChannelHub"] = None

    def __new__(cls) -> "TeamChannelHub":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._rooms: Dict[str, List[Tuple[WebSocket, Dict[str, Any]]]] = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    @staticmethod
    def room_key(tenant_id: int, team_id: int) -> str:
        return f"{tenant_id}:{team_id}"

    async def connect(self, websocket: WebSocket, tenant_id: int, team_id: int, meta: Dict[str, Any]) -> None:
        key = self.room_key(tenant_id, team_id)
        async with self._lock:
            self._rooms.setdefault(key, []).append((websocket, meta))

    async def disconnect(self, websocket: WebSocket, tenant_id: int, team_id: int) -> None:
        key = self.room_key(tenant_id, team_id)
        async with self._lock:
            lst = self._rooms.get(key, [])
            self._rooms[key] = [(w, m) for w, m in lst if w is not websocket]
            if not self._rooms[key]:
                del self._rooms[key]

    async def broadcast_json(
        self,
        tenant_id: int,
        team_id: int,
        payload: Dict[str, Any],
        *,
        exclude: Optional[WebSocket] = None,
    ) -> None:
        key = self.room_key(tenant_id, team_id)
        async with self._lock:
            conns = list(self._rooms.get(key, []))
        stale: List[WebSocket] = []
        for ws, _meta in conns:
            if exclude is not None and ws is exclude:
                continue
            try:
                await ws.send_text(json.dumps(payload, default=str))
            except Exception:
                stale.append(ws)
        if stale:
            async with self._lock:
                lst = self._rooms.get(key, [])
                if lst:
                    self._rooms[key] = [(w, m) for w, m in lst if w not in stale]
                    if not self._rooms[key]:
                        del self._rooms[key]


hub = TeamChannelHub()
