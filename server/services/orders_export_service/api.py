"""
POST /api/orders/export/csv — presigned R2 URL for merchant order exports.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from config import settings
from models import User
from services.auth_service.api import get_current_user
from services.media_storage.r2 import is_r2_configured, presign_get, put_bytes
from services.orders_export_service.csv_builder import object_key_for_orders_csv
from services.orders_export_service.exporter import build_orders_csv_export_bytes
from services.store_integration_service.client import StoreIntegrationClient

logger = logging.getLogger(__name__)

router = APIRouter()

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover
    redis = None

_redis_failed = False


def _redis_client():
    global _redis_failed
    if redis is None or _redis_failed:
        return None
    try:
        c = redis.from_url(settings.redis_url, decode_responses=True)
        c.ping()
        return c
    except Exception:
        logger.warning("orders export: redis unavailable")
        _redis_failed = True
        return None


def _cache_key(tenant_id: int, seller_id: str, date_from: str, date_to: str) -> str:
    return f"orders_csv_url:t{tenant_id}:s{seller_id}:{date_from}:{date_to}"


def _cache_get(tenant_id: int, seller_id: str, date_from: str, date_to: str) -> Optional[Dict[str, Any]]:
    r = _redis_client()
    if not r:
        return None
    try:
        raw = r.get(_cache_key(tenant_id, seller_id, date_from, date_to))
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def _cache_set(tenant_id: int, seller_id: str, date_from: str, date_to: str, payload: Dict[str, Any]) -> None:
    r = _redis_client()
    if not r:
        return
    try:
        r.setex(_cache_key(tenant_id, seller_id, date_from, date_to), 86400, json.dumps(payload))
    except Exception as exc:  # noqa: BLE001
        logger.warning("orders export: cache set failed %s", exc)


class OrdersCsvExportIn(BaseModel):
    seller_id: int = Field(..., ge=1)
    date_from: str = Field(..., min_length=10, max_length=10)
    date_to: str = Field(..., min_length=10, max_length=10)
    format: str = Field(default="csv")


class OrdersCsvExportOut(BaseModel):
    success: bool
    download_url: str
    expires_at: str
    order_count: int = 0
    truncated: bool = False


@router.post("/export/csv", response_model=OrdersCsvExportOut)
async def post_orders_export_csv(
    body: OrdersCsvExportIn,
    current_user: User = Depends(get_current_user),
):
    role = (current_user.role or "").lower()
    if role not in ("admin", "agent"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or agent only")
    if body.format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is supported")
    if not is_r2_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage is not configured",
        )

    tenant_id = int(current_user.tenant_id)
    seller_id = str(int(body.seller_id))
    df = body.date_from.strip()[:10]
    dt = body.date_to.strip()[:10]

    cached = _cache_get(tenant_id, seller_id, df, dt)
    if cached and cached.get("download_url") and cached.get("expires_at"):
        try:
            exp = datetime.fromisoformat(str(cached["expires_at"]).replace("Z", "+00:00"))
            if exp > datetime.now(timezone.utc) + timedelta(minutes=5):
                return OrdersCsvExportOut(
                    success=True,
                    download_url=str(cached["download_url"]),
                    expires_at=str(cached["expires_at"]),
                    order_count=int(cached.get("order_count") or 0),
                    truncated=bool(cached.get("truncated")),
                )
        except (TypeError, ValueError):
            pass

    store = StoreIntegrationClient()
    csv_bytes, row_count, truncated = await build_orders_csv_export_bytes(store, seller_id, df, dt)
    if not csv_bytes or row_count <= 0:
        raise HTTPException(status_code=404, detail="No orders in the selected range")

    key = object_key_for_orders_csv(seller_id)
    put_bytes(key, csv_bytes, "text/csv")
    ttl = 86400
    url = presign_get(key, ttl)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z")

    out = OrdersCsvExportOut(
        success=True,
        download_url=url,
        expires_at=expires_at,
        order_count=row_count,
        truncated=truncated,
    )
    _cache_set(
        tenant_id,
        seller_id,
        df,
        dt,
        {
            "download_url": url,
            "expires_at": out.expires_at,
            "order_count": row_count,
            "truncated": truncated,
        },
    )
    return out
