"""Authentication routes."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rate_limit import enforce_auth_rate_limit
from app.core.logging import get_logger
from app.database.session import get_db
from app.integrations.email import EmailDeliveryError, create_email_provider
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
    VerifyPasswordResetRequest,
    VerifyPasswordResetResponse,
)
from app.schemas.response import success_response
from app.schemas.user import UserResponse
from app.services.auth import AuthService
from app.services.email_verification import EmailVerificationService
from app.services.password_reset import PasswordResetService

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def register(
    payload: RegisterRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    service = AuthService(session)
    user = await service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )
    data = RegisterResponse(
        user=UserResponse.model_validate(user),
        verification_expires_in=(
            service.verification.settings.EMAIL_VERIFICATION_OTP_TTL_SECONDS
        ),
        resend_after=(
            service.verification.settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS
        ),
    )
    return success_response(
        data=data.model_dump(mode="json"),
        message="Registration successful. Email verification is required",
    )


@router.post("/login", dependencies=[Depends(enforce_auth_rate_limit)])
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db)) -> dict:
    _, token = await AuthService(session).login(
        email=payload.email, password=payload.password
    )
    return success_response(
        data=TokenResponse.model_validate(token).model_dump(mode="json"),
        message="Login successful",
    )


@router.post("/verify-email", dependencies=[Depends(enforce_auth_rate_limit)])
async def verify_email(
    payload: VerifyEmailRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    await EmailVerificationService(session).verify(
        email=payload.email,
        otp=payload.otp,
    )
    return success_response(message="Email verified successfully")


@router.post("/resend-verification", dependencies=[Depends(enforce_auth_rate_limit)])
async def resend_verification(
    payload: ResendVerificationRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    verification = EmailVerificationService(session)
    pending = await verification.resend(payload.email)
    try:
        await verification.deliver(create_email_provider(), pending)
    except EmailDeliveryError:
        logger.warning(
            "verification_email_delivery_failed",
            extra={"event": "verification_email_delivery_failed"},
        )
    return success_response(
        data={
            "resend_after": (
                verification.settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS
            )
        },
        message=(
            "If an account exists for this email, a verification code has been sent."
        )
    )


@router.post("/forgot-password", dependencies=[Depends(enforce_auth_rate_limit)])
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    service = PasswordResetService(session)
    pending = await service.request(payload.email)
    try:
        await service.deliver(create_email_provider(), pending)
    except EmailDeliveryError:
        logger.warning(
            "password_reset_email_delivery_failed",
            extra={"event": "password_reset_email_delivery_failed"},
        )
    return success_response(
        data={
            "resend_after": (
                service.settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS
            )
        },
        message=(
            "If an eligible account exists for this email, "
            "a password reset code has been sent."
        ),
    )


@router.post(
    "/verify-password-reset", dependencies=[Depends(enforce_auth_rate_limit)]
)
async def verify_password_reset(
    payload: VerifyPasswordResetRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    authorization = await PasswordResetService(session).verify(
        email=payload.email,
        otp=payload.otp,
    )
    data = VerifyPasswordResetResponse(
        reset_token=authorization.token,
        expires_in=authorization.expires_in_seconds,
    )
    return success_response(
        data=data.model_dump(mode="json"),
        message="Password reset code verified",
    )


@router.post("/reset-password", dependencies=[Depends(enforce_auth_rate_limit)])
async def reset_password(
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await PasswordResetService(session).reset(
        reset_token=payload.reset_token,
        new_password=payload.new_password,
    )
    return success_response(message="Password reset successfully")


@router.get("/me")
async def current_user(user: User = Depends(get_current_user)) -> dict:
    return success_response(
        data=UserResponse.model_validate(user).model_dump(mode="json"),
        message="OK",
    )
