"""
Redis-backed active attendance session pointer per agent.

Key: attendance:session:{agent_id}
Value: JSON { session_id, agent_id, tenant_id, start_time } (ISO UTC Z)
TTL: refreshed on heartbeat (idle timeout without heartbeat → key expires).

Uses redis_url independently of conversation_memory_enabled so attendance works
when conversation memory is disabled.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, Optional

from config import settings

logger = logging.getLogger(__name__)

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover
    redis = None  # type: ignore

_client: Any = None
_failed: bool = False


def _datetime_utc_iso_z(v: datetime) -> str:
    aware = (
        v.replace(tzinfo=dt_timezone.utc)
        if v.tzinfo is None
        else v.astimezone(dt_timezone.utc)
    )
    return aware.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _redis_client() -> Optional[Any]:
    global _client, _failed
    if not bool(getattr(settings, "attendance_redis_enabled", True)):
        return None
    if redis is None:
        return None
    if _failed:
        return None
    if _client is not None:
        return _client
    try:
        c = redis.from_url(settings.redis_url, decode_responses=True)
        c.ping()
        _client = c
        return _client
    except Exception as exc:  # noqa: BLE001
        logger.warning("Attendance Redis unavailable (%s)", exc)
        _failed = True
        return None


def attendance_redis_available() -> bool:
    return _redis_client() is not None


def attendance_session_key(agent_id: int) -> str:
    return f"attendance:session:{int(agent_id)}"


def attendance_idle_ttl_seconds() -> int:
    return max(60, int(getattr(settings, "attendance_idle_ttl_seconds", 900) or 900))


def get_attendance_session_payload(agent_id: int) -> Optional[Dict[str, Any]]:
    r = _redis_client()
    if not r:
        return None
    raw = r.get(attendance_session_key(agent_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def set_attendance_session_redis(
    agent_id: int,
    tenant_id: int,
    session_id: int,
    started_at: datetime,
) -> None:
    r = _redis_client()
    if not r:
        return
    payload = {
        "session_id": int(session_id),
        "agent_id": int(agent_id),
        "tenant_id": int(tenant_id),
        "start_time": _datetime_utc_iso_z(started_at),
    }
    r.setex(
        attendance_session_key(agent_id),
        attendance_idle_ttl_seconds(),
        json.dumps(payload),
    )


def delete_attendance_session_redis(agent_id: int) -> None:
    r = _redis_client()
    if r:
        r.delete(attendance_session_key(agent_id))


def refresh_attendance_session_redis_ttl(agent_id: int) -> bool:
    """Extend idle TTL if the session key exists. Returns True if key was present."""
    r = _redis_client()
    if not r:
        return False
    k = attendance_session_key(agent_id)
    if not r.exists(k):
        return False
    r.expire(k, attendance_idle_ttl_seconds())
    return True


def rewrite_attendance_session_ttl(agent_id: int) -> bool:
    """
    Reset TTL from now while keeping the same value (EXPIRE semantics).
    Returns False if key missing.
    """
    r = _redis_client()
    if not r:
        return False
    k = attendance_session_key(agent_id)
    raw = r.get(k)
    if not raw:
        return False
    r.setex(k, attendance_idle_ttl_seconds(), raw)
    return True
