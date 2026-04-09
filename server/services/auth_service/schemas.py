from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    tenant_id: int
    role: str


class UserResponse(BaseModel):
    id: int
    tenant_id: int
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    tenant_display_timezone: str = "Asia/Karachi"

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
