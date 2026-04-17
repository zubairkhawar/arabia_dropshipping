"""Read-only trending product queries for the customer bot (no HTTP round-trip)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import settings
from models import TrendingProduct
from services.media_storage.r2 import is_r2_configured, presign_get

logger = logging.getLogger(__name__)


def resolve_trending_image_url(row: TrendingProduct) -> Optional[str]:
    u = (row.image_url or "").strip()
    if u:
        return u
    key = (row.image_key or "").strip()
    if key and is_r2_configured():
        try:
            return presign_get(key, settings.r2_presign_get_seconds)
        except Exception as e:
            logger.warning("trending image presign failed: %s", e)
    return None


def list_active_trending_for_country(
    db: Session,
    tenant_id: int,
    country: str,
) -> List[Dict[str, Any]]:
    c = (country or "").strip().upper()
    rows = (
        db.query(TrendingProduct)
        .filter(
            TrendingProduct.tenant_id == tenant_id,
            TrendingProduct.country == c,
            TrendingProduct.is_active.is_(True),
        )
        .order_by(TrendingProduct.display_order.asc(), TrendingProduct.id.asc())
        .all()
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        price_val = float(r.price) if r.price is not None else 0.0
        out.append(
            {
                "id": r.id,
                "product_name": r.product_name,
                "price": price_val,
                "currency": r.currency,
                "category": r.category,
                "description": (r.description or "").strip(),
                "image_url": resolve_trending_image_url(r) or "",
            }
        )
    return out
