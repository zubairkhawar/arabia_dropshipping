import html
import logging
import secrets
from datetime import datetime, timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import PasswordReset, Tenant
from services.auth_service.models import User
from services.auth_service.schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    TokenData,
    UserCreate,
    UserResponse,
    VerifyResetTokenResponse,
)
from services.auth_service.services import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from services.email_service import send_html_email

logger = logging.getLogger(__name__)

router = APIRouter()

# OAuth2PasswordBearer is used by FastAPI's security utilities
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False,
)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


def _create_user_response(user: User, db: Session) -> UserResponse:
    tz = "Asia/Karachi"
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant is not None:
        raw = getattr(tenant, "display_timezone", None)
        if isinstance(raw, str) and raw.strip():
            tz = raw.strip()
    return UserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        tenant_display_timezone=tz,
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> User:
    """
    Decode JWT, load the user, and ensure they are active.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception

    user: User | None = (
        db.query(User).filter(User.email == token_data.email).first()
    )
    if user is None or not user.is_active:
        raise credentials_exception
    return user


async def get_current_user_optional(
    token: Annotated[str | None, Depends(oauth2_scheme_optional)],
    db: Session = Depends(get_db),
) -> User | None:
    """
    Same as get_current_user when Authorization is present; otherwise None.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        email: str | None = payload.get("sub")
        if email is None:
            return None
        token_data = TokenData(email=email)
    except JWTError:
        return None

    user: User | None = (
        db.query(User).filter(User.email == token_data.email).first()
    )
    if user is None or not user.is_active:
        return None
    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: Session = Depends(get_db)):
    """
    Create a new user (admin/agent).

    In most deployments this should be admin-protected or invite-only.
    """
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        tenant_id=payload.tenant_id,
        role=payload.role,
        hashed_password=get_password_hash(payload.password),
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _create_user_response(user, db)


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    OAuth2 password flow login.

    - Accepts email in `username` field.
    - Returns JWT access token with user identity and role.
    """
    user: User | None = (
        db.query(User).filter(User.email == form_data.username).first()
    )
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    access_token_expires = timedelta(hours=settings.jwt_expiration_hours)
    access_token = create_access_token(
        data={
            "sub": user.email,
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role,
        },
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the current authenticated user from the JWT.
    """
    return _create_user_response(current_user, db)


@router.put("/me/password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Allow the logged-in user (agent or admin) to change their password.
    """
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect",
        )

    current_user.hashed_password = get_password_hash(payload.new_password)
    current_user.updated_at = datetime.utcnow()
    db.add(current_user)
    db.commit()

    return {"message": "Password updated successfully"}


@router.post("/logout")
async def logout():
    """
    Stateless JWT logout.

    The frontend should drop the token; token blacklisting is not implemented.
    """
    return {"message": "Logged out"}


def _frontend_base_url() -> str:
    return (settings.frontend_base_url or "").strip().rstrip("/")


def _reset_email_html(reset_url: str, display_email: str) -> str:
    safe_url = html.escape(reset_url, quote=True)
    safe_email = html.escape(display_email, quote=True)
    return f"""<!DOCTYPE html>
<html><body style="font-family:system-ui,sans-serif;line-height:1.5;color:#0f172a;">
  <p>We received a request to reset the password for <strong>{safe_email}</strong>.</p>
  <p><a href="{safe_url}" style="display:inline-block;margin:12px 0;padding:10px 18px;background:#dc2626;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;">Reset password</a></p>
  <p style="font-size:13px;color:#64748b;">This link expires in one hour. If you did not request this, you can ignore this email.</p>
  <p style="font-size:12px;color:#94a3b8;word-break:break-all;">{safe_url}</p>
</body></html>"""


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Start password reset: store URL-safe token (1 hour), email reset link.
    Always returns the same message (no email enumeration).
    """
    generic = {
        "message": "If an account exists for this email, a reset link has been sent."
    }

    email_norm = str(payload.email).strip().lower()
    user: User | None = (
        db.query(User).filter(func.lower(User.email) == email_norm).first()
    )

    if not user or not user.is_active:
        return generic

    db.query(PasswordReset).filter(
        PasswordReset.user_id == user.id,
        PasswordReset.used.is_(False),
    ).update({"used": True}, synchronize_session=False)

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    row = PasswordReset(
        user_id=user.id,
        token=raw_token,
        expires_at=expires_at,
        used=False,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()

    base = _frontend_base_url()
    token_q = quote(raw_token, safe="")
    reset_url = f"{base}/reset-password?token={token_q}"

    ok, err = send_html_email(
        to_email=user.email,
        subject="Reset your Dropship Arabia password",
        html_content=_reset_email_html(reset_url, user.email),
    )
    if ok:
        logger.info("Password reset email sent to %s", user.email)
    else:
        logger.warning("Password reset email failed for %s: %s", user.email, err)
        logger.info("Password reset URL (dev fallback) for %s: %s", user.email, reset_url)

    return generic


@router.get("/verify-reset-token", response_model=VerifyResetTokenResponse)
async def verify_reset_token(
    token: str = Query("", min_length=1),
    db: Session = Depends(get_db),
):
    """Validate a password-reset token before showing the new-password form."""
    row: PasswordReset | None = (
        db.query(PasswordReset).filter(PasswordReset.token == token.strip()).first()
    )
    now = datetime.utcnow()
    if not row or row.used or row.expires_at <= now:
        return VerifyResetTokenResponse(
            valid=False,
            message="This reset link is invalid or has expired. Please request a new one.",
        )

    user: User | None = db.query(User).filter(User.id == row.user_id).first()
    if not user or not user.is_active:
        return VerifyResetTokenResponse(
            valid=False,
            message="This reset link is invalid or has expired. Please request a new one.",
        )

    return VerifyResetTokenResponse(valid=True, email=user.email)


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Complete password reset using DB token and new password (min 8 characters).
    """
    token = (payload.token or "").strip()
    new_password = payload.new_password or ""

    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )

    row: PasswordReset | None = (
        db.query(PasswordReset).filter(PasswordReset.token == token).first()
    )
    now = datetime.utcnow()
    if not row or row.used or row.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    user: User | None = db.query(User).filter(User.id == row.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    user.hashed_password = get_password_hash(new_password)
    user.updated_at = datetime.utcnow()
    row.used = True
    db.add(user)
    db.add(row)
    db.commit()

    return {"message": "Password has been reset successfully."}
