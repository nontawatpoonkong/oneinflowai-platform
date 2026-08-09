"""Resend email provider tests with no external network calls."""

import asyncio
import logging
from typing import Any

import httpx
import pytest
from resend.exceptions import ResendError

from app.core.config import Settings
from app.integrations.email.base import (
    EmailAuthenticationError,
    EmailConfigurationError,
    EmailDeliveryError,
    EmailNetworkError,
    EmailProviderServerError,
    EmailRateLimitError,
)
from app.integrations.email.development import DevelopmentEmailProvider
from app.integrations.email.factory import create_email_provider
from app.integrations.email.resend import ResendEmailProvider

OTP = "482913"
RECIPIENT = "recipient@example.com"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "EMAIL_PROVIDER": "development",
        "RESEND_API_KEY": None,
        "EMAIL_FROM_ADDRESS": "sender@example.com",
        "EMAIL_FROM_NAME": "OneInFlow",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _resend_error(code: int, error_type: str) -> ResendError:
    return ResendError(
        code=code,
        error_type=error_type,
        message="provider detail containing test-api-key and 482913",
        suggested_action="none",
    )


def test_factory_selects_development_provider() -> None:
    provider = create_email_provider(_settings(EMAIL_PROVIDER=" Development "))
    assert isinstance(provider, DevelopmentEmailProvider)


def test_factory_selects_resend_provider() -> None:
    provider = create_email_provider(
        _settings(EMAIL_PROVIDER=" ReSeNd ", RESEND_API_KEY="test-api-key")
    )
    assert isinstance(provider, ResendEmailProvider)


@pytest.mark.parametrize(
    ("overrides", "expected_message"),
    [
        ({"EMAIL_PROVIDER": "resend"}, "RESEND_API_KEY is required"),
        (
            {
                "EMAIL_PROVIDER": "resend",
                "RESEND_API_KEY": "test-api-key",
                "EMAIL_FROM_ADDRESS": "invalid",
            },
            "A valid EMAIL_FROM_ADDRESS is required",
        ),
        ({"EMAIL_PROVIDER": "unknown"}, "Unsupported EMAIL_PROVIDER configuration"),
    ],
)
def test_factory_rejects_invalid_configuration(
    overrides: dict[str, object], expected_message: str
) -> None:
    with pytest.raises(EmailConfigurationError, match=expected_message):
        create_email_provider(_settings(**overrides))


def test_resend_payload_contains_sender_recipient_and_both_bodies(
    caplog: pytest.LogCaptureFixture,
) -> None:
    captured: list[dict[str, Any]] = []

    async def send_async(payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return {"id": "message-id"}

    provider = ResendEmailProvider(
        api_key="test-api-key",
        from_address="sender@example.com",
        from_name="OneInFlow",
        send_async=send_async,
    )
    with caplog.at_level(logging.INFO):
        asyncio.run(
            provider.send_verification_otp(
                recipient=RECIPIENT,
                otp=OTP,
                expires_in_seconds=300,
            )
        )

    assert len(captured) == 1
    payload = captured[0]
    assert payload["from"] == "OneInFlow <sender@example.com>"
    assert payload["to"] == [RECIPIENT]
    assert payload["subject"] == "รหัสยืนยันอีเมล OneInFlow"
    assert OTP in payload["text"]
    assert OTP in payload["html"]
    assert "5" in payload["text"]
    assert "OneInFlow" in payload["html"]
    assert OTP not in caplog.text
    assert RECIPIENT not in caplog.text
    assert "test-api-key" not in caplog.text


def test_resend_password_reset_payload_uses_reset_template() -> None:
    captured: list[dict[str, Any]] = []

    async def send_async(payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return {"id": "reset-message-id"}

    provider = ResendEmailProvider(
        api_key="test-api-key",
        from_address="sender@example.com",
        from_name="OneInFlow",
        send_async=send_async,
    )
    asyncio.run(
        provider.send_password_reset_otp(
            recipient=RECIPIENT,
            otp=OTP,
            expires_in_seconds=300,
        )
    )

    payload = captured[0]
    assert payload["to"] == [RECIPIENT]
    assert payload["subject"] == "รหัสรีเซ็ตรหัสผ่าน OneInFlow"
    assert OTP in payload["text"]
    assert OTP in payload["html"]
    assert "ทีมสนับสนุน" in payload["text"]


@pytest.mark.parametrize(
    ("provider_error", "expected_exception"),
    [
        (_resend_error(401, "missing_api_key"), EmailAuthenticationError),
        (_resend_error(403, "invalid_api_key"), EmailAuthenticationError),
        (_resend_error(429, "rate_limit_exceeded"), EmailRateLimitError),
        (_resend_error(500, "application_error"), EmailProviderServerError),
        (_resend_error(503, "application_error"), EmailProviderServerError),
        (_resend_error(422, "validation_error"), EmailDeliveryError),
    ],
)
def test_resend_provider_maps_sdk_errors(
    provider_error: Exception,
    expected_exception: type[EmailDeliveryError],
) -> None:
    async def send_async(payload: dict[str, Any]) -> dict[str, Any]:
        raise provider_error

    provider = ResendEmailProvider(
        api_key="test-api-key",
        from_address="sender@example.com",
        from_name="OneInFlow",
        send_async=send_async,
    )
    with pytest.raises(expected_exception) as caught:
        asyncio.run(
            provider.send_verification_otp(
                recipient=RECIPIENT,
                otp=OTP,
                expires_in_seconds=300,
            )
        )

    assert OTP not in str(caught.value)
    assert "test-api-key" not in str(caught.value)


@pytest.mark.parametrize(
    "provider_error",
    [
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("network unavailable"),
        TimeoutError("timed out"),
    ],
)
def test_resend_provider_maps_timeout_and_network_errors(
    provider_error: Exception,
) -> None:
    async def send_async(payload: dict[str, Any]) -> dict[str, Any]:
        raise provider_error

    provider = ResendEmailProvider(
        api_key="test-api-key",
        from_address="sender@example.com",
        from_name="OneInFlow",
        send_async=send_async,
    )
    with pytest.raises(EmailNetworkError):
        asyncio.run(
            provider.send_verification_otp(
                recipient=RECIPIENT,
                otp=OTP,
                expires_in_seconds=300,
            )
        )


def test_unknown_provider_error_is_sanitized_and_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "test-api-key"

    async def send_async(payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(f"failure {secret} {OTP} {RECIPIENT}")

    provider = ResendEmailProvider(
        api_key=secret,
        from_address="sender@example.com",
        from_name="OneInFlow",
        send_async=send_async,
    )
    with caplog.at_level(logging.INFO), pytest.raises(EmailDeliveryError) as caught:
        asyncio.run(
            provider.send_verification_otp(
                recipient=RECIPIENT,
                otp=OTP,
                expires_in_seconds=300,
            )
        )

    combined = caplog.text + str(caught.value)
    assert secret not in combined
    assert OTP not in combined
    assert RECIPIENT not in combined
