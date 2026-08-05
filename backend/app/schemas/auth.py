"""Authentication schemas."""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyPasswordResetRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r"^[0-9]{6}$")


class VerifyPasswordResetResponse(BaseModel):
    reset_token: str
    expires_in: int


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


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
