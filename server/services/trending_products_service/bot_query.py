"""Read-only trending product queries for the customer bot (no HTTP round-trip)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import settings
from models import TrendingProduct
from services.media_storage.r2 import is_r2_configured, presign_get

logger = logging.getLogger(__name__)


def _resolve_key_to_url(key: str, public_base: str) -> Optional[str]:
    if public_base:
        return f"{public_base}/{key}"
    if is_r2_configured():
        try:
            return presign_get(key, settings.r2_presign_get_seconds)
        except Exception as e:  # noqa: BLE001
            logger.warning("trending image presign failed for key=%s: %s", key, e)
            return None
    return None


def resolve_trending_image_url(row: TrendingProduct) -> Optional[str]:
    u = (row.image_url or "").strip()
    if u:
        return u
    key = (row.image_key or "").strip()
    if not key:
        logger.info(
            "trending image: product_id=%s country=%s has no image_url and no image_key",
            getattr(row, "id", "?"),
            getattr(row, "country", "?"),
        )
        return None
    public_base = (getattr(settings, "r2_public_base_url", None) or "").strip().rstrip("/")
    url = _resolve_key_to_url(key, public_base)
    if not url:
        logger.warning(
            "trending image: product_id=%s country=%s could not resolve key=%s "
            "(r2_public_base_url_set=%s, r2_configured=%s) — set R2_PUBLIC_BASE_URL or R2_PUBLIC_URL",
            getattr(row, "id", "?"),
            getattr(row, "country", "?"),
            key[:80],
            bool(public_base),
            is_r2_configured(),
        )
    return url


def resolve_trending_image_urls(row: TrendingProduct) -> List[str]:
    out: List[str] = []
    raw_urls = getattr(row, "image_urls", None)
    if isinstance(raw_urls, list):
        out.extend(str(u).strip() for u in raw_urls if str(u).strip())
    if row.image_url and row.image_url.strip():
        primary = row.image_url.strip()
        if primary not in out:
            out.insert(0, primary)
    if out:
        return out
    raw_keys = getattr(row, "image_keys", None)
    keys: List[str] = []
    if isinstance(raw_keys, list):
        keys.extend(str(k).strip() for k in raw_keys if str(k).strip())
    if row.image_key and row.image_key.strip():
        primary_key = row.image_key.strip()
        if primary_key not in keys:
            keys.insert(0, primary_key)
    public_base = (getattr(settings, "r2_public_base_url", None) or "").strip().rstrip("/")
    resolved: List[str] = []
    for key in keys:
        url = _resolve_key_to_url(key, public_base)
        if url:
            resolved.append(url)
    if keys and not resolved:
        logger.warning(
            "trending images: product_id=%s country=%s had %d key(s) but none resolved "
            "(r2_public_base_url_set=%s, r2_configured=%s)",
            getattr(row, "id", "?"),
            getattr(row, "country", "?"),
            len(keys),
            bool(public_base),
            is_r2_configured(),
        )
    return resolved


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
                "image_urls": resolve_trending_image_urls(r),
            }
        )
    return out


def get_trending_product_by_id(
    db: Session, tenant_id: int, product_id: int
) -> Optional[Dict[str, Any]]:
    """Single active trending row for detail replies (authoritative vs cached list)."""
    r = (
        db.query(TrendingProduct)
        .filter(
            TrendingProduct.id == int(product_id),
            TrendingProduct.tenant_id == tenant_id,
            TrendingProduct.is_active.is_(True),
        )
        .first()
    )
    if not r:
        return None
    price_val = float(r.price) if r.price is not None else 0.0
    return {
        "id": r.id,
        "product_name": r.product_name,
        "price": price_val,
        "currency": r.currency,
        "category": r.category,
        "description": (r.description or "").strip(),
        "image_url": resolve_trending_image_url(r) or "",
        "image_urls": resolve_trending_image_urls(r),
        "country": (r.country or "").strip().upper(),
    }
