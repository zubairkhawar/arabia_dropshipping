import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import TrendingProduct, User
from services.auth_service.api import get_current_user
from services.media_storage.r2 import delete_object, is_r2_configured, presign_get

logger = logging.getLogger(__name__)

router = APIRouter()

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


class TrendingProductOut(BaseModel):
    id: int
    tenant_id: int
    country: str
    product_name: str
    price: float
    currency: str
    category: str
    image_url: Optional[str] = None
    image_key: Optional[str] = None
    image_display_url: Optional[str] = None
    description: Optional[str] = None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def _to_out(row: TrendingProduct) -> TrendingProductOut:
    return TrendingProductOut(
        id=row.id,
        tenant_id=row.tenant_id,
        country=row.country,
        product_name=row.product_name,
        price=float(row.price),
        currency=row.currency,
        category=row.category,
        image_url=row.image_url,
        image_key=row.image_key,
        image_display_url=_resolve_image_url(row),
        description=row.description,
        display_order=row.display_order,
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class TrendingProductCreate(BaseModel):
    country: str = Field(..., min_length=2, max_length=10)
    product_name: str = Field(..., min_length=1, max_length=255)
    price: Decimal = Field(..., ge=Decimal("0"), le=Decimal("99999999.99"))
    currency: str = Field(..., min_length=3, max_length=5)
    category: str = Field(..., min_length=1, max_length=80)
    image_url: Optional[str] = None
    image_key: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    display_order: int = Field(default=1, ge=1, le=100)
    is_active: bool = True


class TrendingProductUpdate(BaseModel):
    country: Optional[str] = Field(None, min_length=2, max_length=10)
    product_name: Optional[str] = Field(None, min_length=1, max_length=255)
    price: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("99999999.99"))
    currency: Optional[str] = Field(None, min_length=3, max_length=5)
    category: Optional[str] = Field(None, min_length=1, max_length=80)
    image_url: Optional[str] = None
    image_key: Optional[str] = Field(None, max_length=255)
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
    row = TrendingProduct(
        tenant_id=current_user.tenant_id,
        country=cty,
        product_name=payload.product_name.strip(),
        price=payload.price,
        currency=cur,
        category=cat,
        image_url=(payload.image_url or "").strip() or None,
        image_key=(payload.image_key or "").strip() or None,
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

    old_key = (row.image_key or "").strip() or None

    if payload.country is not None or payload.currency is not None or payload.category is not None:
        cty = payload.country if payload.country is not None else row.country
        cur = payload.currency if payload.currency is not None else row.currency
        cat = payload.category if payload.category is not None else row.category
        cty, cur, cat = _validate_country_currency_category(cty, cur, cat)
        row.country = cty
        row.currency = cur
        row.category = cat

    if payload.product_name is not None:
        row.product_name = payload.product_name.strip()
    if payload.price is not None:
        row.price = payload.price
    if payload.description is not None:
        row.description = (payload.description or "").strip() or None
    if payload.display_order is not None:
        row.display_order = payload.display_order
    if payload.is_active is not None:
        row.is_active = payload.is_active

    new_key = None
    if payload.image_key is not None:
        new_key = (payload.image_key or "").strip() or None
        row.image_key = new_key
    if payload.image_url is not None:
        row.image_url = (payload.image_url or "").strip() or None

    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)

    if new_key is not None and old_key and old_key != new_key:
        delete_object(old_key)

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
    key = (row.image_key or "").strip()
    db.delete(row)
    db.commit()
    if key:
        delete_object(key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
