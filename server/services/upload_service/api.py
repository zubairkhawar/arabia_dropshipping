from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import Agent, User
from services.auth_service.api import get_current_user
from services.media_storage.r2 import (
    is_r2_configured,
    new_object_key,
    presign_put,
    validate_upload_request,
)

router = APIRouter()


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
