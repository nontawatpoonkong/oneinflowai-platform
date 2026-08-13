"""Production configuration and public-boundary hardening tests."""

import uuid
from types import SimpleNamespace

import pytest
from redis.exceptions import ConnectionError

from app.auth.rate_limit import enforce_auth_rate_limit
from app.core.config import Settings, validate_production_settings
from app.webchat.rate_limit import enforce_webchat_rate_limit


def _production(**overrides) -> Settings:
    values = {
        "APP_ENV": "production",
        "DEBUG": False,
        "JWT_SECRET_KEY": "j" * 32,
        "OTP_HASH_SECRET": "o" * 32,
        "CORS_ORIGINS": "https://app.example.com",
        "TRUSTED_HOSTS": "api.example.com",
        "EMAIL_PROVIDER": "resend",
        "GENERATION_PROVIDER": "openai",
        "EMBEDDING_PROVIDER": "openai",
        "ACTION_COLLECTION_PROVIDER": "generation",
        "SLIP_VERIFICATION_PROVIDER": "easyslip_v2",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_safe_production_configuration_is_accepted() -> None:
    validate_production_settings(_production())


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"DEBUG": True}, "DEBUG"),
        ({"JWT_SECRET_KEY": "short"}, "JWT_SECRET_KEY"),
        ({"OTP_HASH_SECRET": None}, "OTP_HASH_SECRET"),
        ({"CORS_ORIGINS": "*"}, "CORS_ORIGINS"),
        ({"TRUSTED_HOSTS": "*"}, "TRUSTED_HOSTS"),
        ({"EMAIL_PROVIDER": "development"}, "EMAIL_PROVIDER"),
        ({"GENERATION_PROVIDER": "development"}, "GENERATION_PROVIDER"),
        ({"EMBEDDING_PROVIDER": "development"}, "EMBEDDING_PROVIDER"),
        ({"ACTION_COLLECTION_PROVIDER": "development"}, "ACTION_COLLECTION_PROVIDER"),
        ({"SLIP_VERIFICATION_PROVIDER": "development"}, "SLIP_VERIFICATION_PROVIDER"),
    ],
)
def test_unsafe_production_configuration_fails_closed(override, message) -> None:
    with pytest.raises(ValueError, match=message):
        validate_production_settings(_production(**override))


class _UnavailableRedis:
    async def eval(self, *args):
        raise ConnectionError("secret redis detail")


def _request(path: str):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=_UnavailableRedis())),
        client=SimpleNamespace(host="203.0.113.1"),
        url=SimpleNamespace(path=path),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dependency", "path"),
    [
        (enforce_webchat_rate_limit, "/api/v1/webchat/sessions"),
        (enforce_auth_rate_limit, "/api/v1/auth/login"),
    ],
)
async def test_cost_and_auth_rate_limits_fail_closed_when_redis_is_down(
    dependency, path
) -> None:
    with pytest.raises(Exception) as captured:
        await dependency(_request(path))
    assert getattr(captured.value, "status_code", None) == 503
    assert "secret redis detail" not in str(captured.value)


def test_untrusted_request_id_is_replaced(client) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad\nlog"})
    assert response.status_code == 200
    uuid.UUID(response.headers["X-Request-ID"])
