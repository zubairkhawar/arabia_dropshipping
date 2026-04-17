import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import TrendingProduct, User
from services.auth_service.api import get_current_user
from services.media_storage.r2 import delete_object, is_r2_configured, presign_get

logger = logging.getLogger(__name__)

# Full path prefix avoids Starlette/FastAPI ""-path mismatches (no 404 on /api/admin/trending-products).
router = APIRouter(prefix="/api/admin/trending-products", tags=["admin-trending"])

ALLOWED_COUNTRIES = frozenset({"UAE", "KSA", "PK"})
ALLOWED_CURRENCIES = frozenset({"AED", "SAR", "PKR"})
ALLOWED_CATEGORIES = frozenset(
    {
        "Electronics",
        "Fashion",
        "Beauty",
        "Home & Living",
        "Toys & Games",
        "Sports & Outdoors",
        "Pets",
        "Automotive",
        "Baby & Kids",
        "Books & Media",
        "Office & Stationery",
        "Groceries & Food",
        "Health & Wellness",
        "Jewelry & Watches",
        "Luggage & Travel",
        "Tools & Home Improvement",
        "Garden & Outdoor",
        "Musical Instruments",
        "Art & Crafts",
        "Party & Occasion",
    }
)


def _require_admin(user: User) -> None:
    if (user.role or "").lower() != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


def _normalize_product_name(name: str) -> str:
    # Store names in title case consistently, e.g. "vacuum cleaner" -> "Vacuum Cleaner".
    return " ".join((name or "").strip().split()).title()


def _resolve_image_url(row: TrendingProduct) -> Optional[str]:
    u = (row.image_url or "").strip()
    if u:
        return u
    key = (row.image_key or "").strip()
    if key and is_r2_configured():
        try:
            return presign_get(key, settings.r2_presign_get_seconds)
        except Exception as e:
            logger.warning("trending product presign failed: %s", e)
    return None


def _normalize_image_lists(
    image_urls: Optional[List[str]],
    image_keys: Optional[List[str]],
) -> tuple[list[str], list[str]]:
    urls = [u.strip() for u in (image_urls or []) if isinstance(u, str) and u.strip()]
    keys = [k.strip() for k in (image_keys or []) if isinstance(k, str) and k.strip()]
    return urls, keys


def _resolve_image_urls(row: TrendingProduct) -> list[str]:
    out: list[str] = []
    raw_urls: Any = getattr(row, "image_urls", None)
    if isinstance(raw_urls, list):
        out.extend(str(u).strip() for u in raw_urls if str(u).strip())
    if row.image_url and row.image_url.strip():
        primary = row.image_url.strip()
        if primary not in out:
            out.insert(0, primary)
    if out:
        return out
    raw_keys: Any = getattr(row, "image_keys", None)
    keys: list[str] = []
    if isinstance(raw_keys, list):
        keys.extend(str(k).strip() for k in raw_keys if str(k).strip())
    if row.image_key and row.image_key.strip():
        primary_key = row.image_key.strip()
        if primary_key not in keys:
            keys.insert(0, primary_key)
    resolved: list[str] = []
    for k in keys:
        if is_r2_configured():
            try:
                resolved.append(presign_get(k, settings.r2_presign_get_seconds))
            except Exception as e:
                logger.warning("trending product presign failed for key %s: %s", k, e)
    return resolved


class TrendingProductOut(BaseModel):
    id: int
    tenant_id: int
    country: str
    product_name: str
    price: float
    currency: str
    category: str
    unit_pieces: Optional[int] = None
    image_url: Optional[str] = None
    image_key: Optional[str] = None
    image_display_url: Optional[str] = None
    image_urls: List[str] = []
    image_keys: List[str] = []
    image_display_urls: List[str] = []
    description: Optional[str] = None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def _to_out(row: TrendingProduct) -> TrendingProductOut:
    pr = row.price
    price_f = float(pr) if pr is not None else 0.0
    image_urls = _resolve_image_urls(row)
    raw_keys = getattr(row, "image_keys", None)
    image_keys = [str(k).strip() for k in raw_keys if str(k).strip()] if isinstance(raw_keys, list) else []
    if row.image_key and row.image_key.strip() and row.image_key.strip() not in image_keys:
        image_keys.insert(0, row.image_key.strip())
    return TrendingProductOut(
        id=row.id,
        tenant_id=row.tenant_id,
        country=row.country,
        product_name=row.product_name,
        price=price_f,
        currency=row.currency,
        category=row.category,
        unit_pieces=row.unit_pieces,
        image_url=row.image_url,
        image_key=row.image_key,
        image_display_url=_resolve_image_url(row),
        image_urls=image_urls,
        image_keys=image_keys,
        image_display_urls=image_urls,
        description=row.description,
        display_order=row.display_order,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class TrendingProductCreate(BaseModel):
    country: str = Field(..., min_length=2, max_length=10)
    product_name: str = Field(..., min_length=1, max_length=255)
    price: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("99999999.99"),
        description="Optional; omit or null to leave price unset (stored as 0).",
    )
    currency: str = Field(..., min_length=3, max_length=5)
    category: str = Field(..., min_length=1, max_length=80)
    unit_pieces: Optional[int] = Field(None, ge=1, le=1000000)
    image_url: Optional[str] = None
    image_key: Optional[str] = Field(None, max_length=255)
    image_urls: Optional[List[str]] = None
    image_keys: Optional[List[str]] = None
    description: Optional[str] = None
    display_order: int = Field(default=1, ge=1, le=100)
    is_active: bool = True


class TrendingProductUpdate(BaseModel):
    country: Optional[str] = Field(None, min_length=2, max_length=10)
    product_name: Optional[str] = Field(None, min_length=1, max_length=255)
    price: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("99999999.99"))
    currency: Optional[str] = Field(None, min_length=3, max_length=5)
    category: Optional[str] = Field(None, min_length=1, max_length=80)
    unit_pieces: Optional[int] = Field(None, ge=1, le=1000000)
    image_url: Optional[str] = None
    image_key: Optional[str] = Field(None, max_length=255)
    image_urls: Optional[List[str]] = None
    image_keys: Optional[List[str]] = None
    description: Optional[str] = None
    display_order: Optional[int] = Field(None, ge=1, le=100)
    is_active: Optional[bool] = None


def _validate_country_currency_category(
    country: str, currency: str, category: str
) -> tuple[str, str, str]:
    cty = country.strip().upper()
    if cty == "SAUDI" or cty == "SA":
        cty = "KSA"
    if cty not in ALLOWED_COUNTRIES:
        raise HTTPException(status_code=400, detail="country must be UAE, KSA, or PK")
    cur = currency.strip().upper()
    if cur not in ALLOWED_CURRENCIES:
        raise HTTPException(status_code=400, detail="currency must be AED, SAR, or PKR")
    cat = category.strip()
    if cat not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")
    return cty, cur, cat


@router.get("/", response_model=List[TrendingProductOut])
@router.get("", response_model=List[TrendingProductOut])
async def list_trending_products(
    country: Optional[str] = Query(None, description="UAE | KSA | PK"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    q = db.query(TrendingProduct).filter(TrendingProduct.tenant_id == current_user.tenant_id)
    if country:
        c = country.strip().upper()
        if c not in ALLOWED_COUNTRIES:
            raise HTTPException(status_code=400, detail="Invalid country filter")
        q = q.filter(TrendingProduct.country == c)
    rows = q.order_by(TrendingProduct.display_order.asc(), TrendingProduct.id.asc()).all()
    return [_to_out(r) for r in rows]


@router.post("/", response_model=TrendingProductOut, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=TrendingProductOut, status_code=status.HTTP_201_CREATED)
async def create_trending_product(
    payload: TrendingProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    cty, cur, cat = _validate_country_currency_category(
        payload.country, payload.currency, payload.category
    )
    norm_urls, norm_keys = _normalize_image_lists(payload.image_urls, payload.image_keys)
    ik = (payload.image_key or "").strip()
    iu = (payload.image_url or "").strip()
    if iu and iu not in norm_urls:
        norm_urls.insert(0, iu)
    if ik and ik not in norm_keys:
        norm_keys.insert(0, ik)
    if not norm_keys:
        raise HTTPException(status_code=400, detail="At least one product image is required")
    row = TrendingProduct(
        tenant_id=current_user.tenant_id,
        country=cty,
        product_name=_normalize_product_name(payload.product_name),
        price=payload.price if payload.price is not None else Decimal("0"),
        currency=cur,
        category=cat,
        unit_pieces=payload.unit_pieces,
        image_url=(norm_urls[0] if norm_urls else None),
        image_key=(norm_keys[0] if norm_keys else None),
        image_urls=norm_urls or None,
        image_keys=norm_keys or None,
        description=(payload.description or "").strip() or None,
        display_order=payload.display_order,
        is_active=payload.is_active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.put("/{product_id}", response_model=TrendingProductOut)
async def update_trending_product(
    product_id: int,
    payload: TrendingProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    row = (
        db.query(TrendingProduct)
        .filter(
            TrendingProduct.id == product_id,
            TrendingProduct.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")

    old_keys = [str(k).strip() for k in (getattr(row, "image_keys", None) or []) if str(k).strip()]
    old_primary_key = (row.image_key or "").strip()
    if old_primary_key and old_primary_key not in old_keys:
        old_keys.insert(0, old_primary_key)

    if payload.country is not None or payload.currency is not None or payload.category is not None:
        cty = payload.country if payload.country is not None else row.country
        cur = payload.currency if payload.currency is not None else row.currency
        cat = payload.category if payload.category is not None else row.category
        cty, cur, cat = _validate_country_currency_category(cty, cur, cat)
        row.country = cty
        row.currency = cur
        row.category = cat

    if payload.product_name is not None:
        row.product_name = _normalize_product_name(payload.product_name)
    if payload.price is not None:
        row.price = payload.price
    if payload.unit_pieces is not None:
        row.unit_pieces = payload.unit_pieces
    if payload.description is not None:
        row.description = (payload.description or "").strip() or None
    if payload.display_order is not None:
        row.display_order = payload.display_order
    if payload.is_active is not None:
        row.is_active = payload.is_active

    new_key = None
    if payload.image_key is not None:
        new_key = (payload.image_key or "").strip() or None
        if not new_key:
            raise HTTPException(
                status_code=400,
                detail="Product image cannot be removed; upload a new image.",
            )
        row.image_key = new_key
    if payload.image_keys is not None:
        norm_keys = [k.strip() for k in payload.image_keys if isinstance(k, str) and k.strip()]
        if not norm_keys:
            raise HTTPException(status_code=400, detail="At least one product image is required")
        row.image_keys = norm_keys
        row.image_key = norm_keys[0]
    if payload.image_url is not None:
        row.image_url = (payload.image_url or "").strip() or None
    if payload.image_urls is not None:
        norm_urls = [u.strip() for u in payload.image_urls if isinstance(u, str) and u.strip()]
        row.image_urls = norm_urls or None
        if norm_urls:
            row.image_url = norm_urls[0]
    if new_key is not None:
        existing_keys = [str(k).strip() for k in (getattr(row, "image_keys", None) or []) if str(k).strip()]
        if new_key not in existing_keys:
            existing_keys.insert(0, new_key)
            row.image_keys = existing_keys

    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)

    new_keys = [str(k).strip() for k in (getattr(row, "image_keys", None) or []) if str(k).strip()]
    if row.image_key and row.image_key.strip() and row.image_key.strip() not in new_keys:
        new_keys.insert(0, row.image_key.strip())
    for k in old_keys:
        if k and k not in new_keys:
            delete_object(k)

    return _to_out(row)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trending_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    row = (
        db.query(TrendingProduct)
        .filter(
            TrendingProduct.id == product_id,
            TrendingProduct.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    keys = [str(k).strip() for k in (getattr(row, "image_keys", None) or []) if str(k).strip()]
    primary = (row.image_key or "").strip()
    if primary and primary not in keys:
        keys.insert(0, primary)
    db.delete(row)
    db.commit()
    for k in keys:
        delete_object(k)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Public read (WhatsApp / web bot; no auth) ---

public_router = APIRouter(prefix="/api/public", tags=["public"])


class TrendingProductPublicOut(BaseModel):
    product_name: str
    price: float
    currency: str
    category: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: List[str] = []


@public_router.get("/trending-products", response_model=List[TrendingProductPublicOut])
def public_list_trending_products(
    country: str = Query(..., min_length=2, max_length=10),
    tenant_id: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    c = country.strip().upper()
    if c in ("SA", "SAUDI"):
        c = "KSA"
    if c not in ALLOWED_COUNTRIES:
        raise HTTPException(status_code=400, detail="country must be UAE, KSA, or PK")
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
    out: List[TrendingProductPublicOut] = []
    for r in rows:
        pr = r.price
        pf = float(pr) if pr is not None else 0.0
        out.append(
            TrendingProductPublicOut(
                product_name=r.product_name,
                price=pf,
                currency=r.currency,
                category=r.category,
                description=(r.description or "").strip() or None,
                image_url=_resolve_image_url(r),
                image_urls=_resolve_image_urls(r),
            )
        )
    return out
