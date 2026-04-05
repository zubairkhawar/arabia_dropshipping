from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from services.auth_service.models import User
from services.auth_service.schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    TokenData,
    UserCreate,
    UserResponse,
)
from services.auth_service.services import (
    get_password_hash,
    create_access_token,
    verify_password,
)

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


def _create_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
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
    return _create_user_response(user)


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
async def read_current_user(current_user: User = Depends(get_current_user)):
    """
    Return the current authenticated user from the JWT.
    """
    return _create_user_response(current_user)


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


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Start password reset flow.
    - Looks up user by email
    - Creates a short-lived JWT reset token
    - Sends an email with a reset link (stubbed for now)
    """
    user: User | None = db.query(User).filter(User.email == payload.email).first()

    # Always return 200 to avoid leaking whether user exists
    if not user:
        return {
            "message": "If an account exists for this email, a reset link has been sent."
        }

    reset_token = create_access_token(
        {"sub": user.email, "scope": "password_reset"},
        expires_delta=timedelta(minutes=30),
    )
    reset_url = f"{settings.frontend_base_url}/reset-password?token={reset_token}"

    # TODO: integrate with AWS SES or your email provider.
    # For now this is just a placeholder so you can see the URL in logs.
    print(f"[forgot-password] Reset URL for {user.email}: {reset_url}")

    return {
        "message": "If an account exists for this email, a reset link has been sent."
    }


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Complete password reset flow using token and new password.
    """
    try:
        data = jwt.decode(
            payload.token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if data.get("scope") != "password_reset":
            raise JWTError("Invalid scope")
        email: str = data.get("sub")
        if not email:
            raise JWTError("Missing subject")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )

    user: User | None = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token.",
        )

    user.hashed_password = get_password_hash(payload.new_password)
    user.updated_at = datetime.utcnow()
    db.add(user)
    db.commit()

    return {"message": "Password has been reset successfully."}
