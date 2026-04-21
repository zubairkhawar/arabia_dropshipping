"""
Monitoring helpers for Redis conversation memory.

Keys use TTL and expire automatically; this module is for optional stats/logging.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def log_memory_stats(redis_client: Optional[Any] = None) -> None:
    """
    Log coarse Redis stats when available (e.g. daily background task or cron).

    Uses INFO memory + keyspace (no SCAN — safe on large instances).
    """
    try:
        from services.memory_service import _get_redis

        r = redis_client or _get_redis()
        if not r:
            logger.info("memory_stats: Redis not configured or unreachable")
            return
        mem_info = r.info("memory")
        used_h = mem_info.get("used_memory_human", mem_info.get("used_memory", "?"))
        peak_h = mem_info.get("used_memory_peak_human", mem_info.get("used_memory_peak", "?"))

        ks = r.info("keyspace") or {}
        key_lines = []
        for dbname, meta in ks.items():
            if isinstance(meta, dict):
                nkeys = meta.get("keys", "?")
                expires = meta.get("expires", "?")
                key_lines.append(f"{dbname} keys={nkeys} expires={expires}")
            else:
                key_lines.append(f"{dbname}: {meta}")
        ks_summary = "; ".join(key_lines) if key_lines else "no keyspace data"

        logger.info(
            "memory_stats: used=%s peak=%s | keyspace: %s",
            used_h,
            peak_h,
            ks_summary,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory_stats: failed: %s", exc)


async def log_memory_stats_async(redis_client: Optional[Any] = None) -> None:
    """Async wrapper for callers that prefer await."""
    log_memory_stats(redis_client=redis_client)
