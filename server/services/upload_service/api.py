import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import Agent, User
from services.auth_service.api import get_current_user
from services.media_storage.r2 import (
    is_r2_configured,
    new_object_key,
    presign_get,
    presign_put,
    put_bytes,
    trending_product_object_key,
    validate_upload_request,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class UploadSignIn(BaseModel):
    type: str = Field(..., description="voice | image | file")
    content_type: str
    size_bytes: int = Field(..., ge=1, le=10 * 1024 * 1024)
    duration_seconds: Optional[float] = None


class UploadSignOut(BaseModel):
    upload_url: str
    object_key: str
    expires_in: int


@router.post("/sign", response_model=UploadSignOut)
async def sign_upload(
    payload: UploadSignIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Issue a presigned PUT URL for direct browser → R2 upload.
    """
    if not is_r2_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media storage is not configured",
        )
    role = (current_user.role or "").lower()
    if role not in ("agent", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    if role == "agent":
        ag = (
            db.query(Agent)
            .filter(Agent.user_id == current_user.id, Agent.tenant_id == current_user.tenant_id)
            .first()
        )
        if not ag:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an agent")

    try:
        kind, ext = validate_upload_request(payload.type, payload.content_type, payload.size_bytes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    from config import settings

    expires = max(30, min(settings.r2_presign_put_seconds, 600))
    object_key = new_object_key(kind, ext)
    try:
        url = presign_put(object_key, payload.content_type.strip(), expires)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create upload URL",
        ) from e

    return UploadSignOut(upload_url=url, object_key=object_key, expires_in=expires)


def _trending_country_folder(country: str) -> str:
    c = (country or "").strip().upper()
    if c in ("KSA", "SA", "SAUDI", "SAUDI ARABIA"):
        return "ksa"
    if c in ("PK", "PAK", "PAKISTAN"):
        return "pk"
    if c in ("UAE", "AE", "EMIRATES"):
        return "uae"
    raise ValueError("country must be UAE, KSA, or PK")


class ProductImageUploadOut(BaseModel):
    object_key: str
    image_url: Optional[str] = None
    image_display_url: Optional[str] = None


@router.post("/product-image", response_model=ProductImageUploadOut)
async def upload_product_image(
    country: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Admin-only: upload a trending product image to R2 under trending-products/{uae|ksa|pk}/.
    """
    if (current_user.role or "").lower() != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    if not is_r2_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Media storage is not configured",
        )
    try:
        folder = _trending_country_folder(country)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    body = await file.read()
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    raw_ct = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    try:
        _, ext = validate_upload_request("image", raw_ct, len(body))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    object_key = trending_product_object_key(folder, ext)
    try:
        put_bytes(object_key, body, raw_ct or "application/octet-stream")
    except Exception as e:
        logger.exception("R2 put_bytes failed for trending product image: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload failed",
        ) from e

    from config import settings

    public_base = (settings.r2_public_base_url or "").strip().rstrip("/")
    stored_url = f"{public_base}/{object_key}" if public_base else None
    display_url = stored_url
    if not display_url:
        try:
            display_url = presign_get(object_key, min(86400, settings.r2_presign_get_seconds))
        except Exception as e:
            logger.warning("presign_get for trending image: %s", e)
            display_url = None

    return ProductImageUploadOut(
        object_key=object_key,
        image_url=stored_url,
        image_display_url=display_url,
    )
