from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from services.auth_service.models import User
from services.auth_service.schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from services.auth_service.services import get_password_hash, create_access_token

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


@router.post("/register")
async def register():
    """User registration endpoint"""
    return {"message": "Registration endpoint"}


@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """User login endpoint"""
    return {"message": "Login endpoint"}


@router.get("/me")
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get current authenticated user"""
    return {"message": "Get current user endpoint"}


@router.post("/logout")
async def logout():
    """User logout endpoint"""
    return {"message": "Logout endpoint"}


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
    db.add(user)
    db.commit()

    return {"message": "Password has been reset successfully."}
