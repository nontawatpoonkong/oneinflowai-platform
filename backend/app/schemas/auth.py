"""Authentication schemas."""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserResponse
from app.schemas.workspace import WorkspaceResponse


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^[0-9]{6}$")


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RegisterResponse(BaseModel):
    user: UserResponse
    workspace: WorkspaceResponse
    verification_required: bool = True
    verification_type: Literal["EMAIL_OTP"] = "EMAIL_OTP"
    verification_expires_in: int
    resend_after: int
