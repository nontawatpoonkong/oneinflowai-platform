"""Startup policy for signing and hashing secrets.

JWT_SECRET_KEY signs access tokens; WEBCHAT_METADATA_HASH_SECRET keys the
HMAC that pseudonymises visitor IP addresses. Both ship with public defaults
for local work. Outside development and test, a missing, short, or published
default value must stop startup, and neither the error nor the log may
contain the configured value. Every value here is a fake test string.
"""

import logging

import pytest

from app.core.config import (
    Settings,
    insecure_secret_names,
    validate_production_settings,
)

_JWT_DEFAULT = Settings.model_fields["JWT_SECRET_KEY"].default
_WEBCHAT_DEFAULT = Settings.model_fields["WEBCHAT_METADATA_HASH_SECRET"].default
_STRONG_JWT = "test-only-jwt-signing-value-0123456789"
_STRONG_WEBCHAT = "test-only-webchat-hmac-value-0123456789"


def _settings(environment: str, **overrides) -> Settings:
    values = {
        "APP_ENV": environment,
        "DEBUG": False,
        "JWT_SECRET_KEY": _STRONG_JWT,
        "WEBCHAT_METADATA_HASH_SECRET": _STRONG_WEBCHAT,
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


@pytest.mark.parametrize("environment", ["production", "staging", "Production", "prod"])
def test_secrets_meeting_the_policy_are_accepted(environment) -> None:
    validate_production_settings(_settings(environment))


@pytest.mark.parametrize("environment", ["production", "staging", "Production", "prod"])
@pytest.mark.parametrize(
    ("name", "value", "reason"),
    [
        ("JWT_SECRET_KEY", _JWT_DEFAULT, "published default"),
        ("JWT_SECRET_KEY", "", "must be set"),
        ("JWT_SECRET_KEY", "   ", "must be set"),
        ("JWT_SECRET_KEY", "short-but-not-default", "at least 32 bytes"),
        ("JWT_SECRET_KEY", "change-me-" + "x" * 40, "published default"),
        ("WEBCHAT_METADATA_HASH_SECRET", _WEBCHAT_DEFAULT, "published default"),
        ("WEBCHAT_METADATA_HASH_SECRET", "", "must be set"),
        ("WEBCHAT_METADATA_HASH_SECRET", "short-but-not-default", "at least 32 bytes"),
    ],
)
def test_unsafe_secrets_stop_startup_outside_local_environments(
    environment, name, value, reason
) -> None:
    with pytest.raises(ValueError) as captured:
        validate_production_settings(_settings(environment, **{name: value}))
    message = str(captured.value)
    assert name in message
    assert reason in message
    if value.strip():
        assert value not in message


def test_staging_checks_secrets_without_production_provider_rules() -> None:
    # Staging may run development providers; only the secrets are enforced.
    validate_production_settings(
        _settings("staging", EMAIL_PROVIDER="development", DEBUG=True)
    )


@pytest.mark.parametrize("environment", ["development", "test", " Development "])
def test_local_environments_tolerate_the_published_defaults(environment) -> None:
    settings = _settings(
        environment,
        JWT_SECRET_KEY=_JWT_DEFAULT,
        WEBCHAT_METADATA_HASH_SECRET=_WEBCHAT_DEFAULT,
    )
    validate_production_settings(settings)
    assert insecure_secret_names(settings) == [
        "JWT_SECRET_KEY",
        "WEBCHAT_METADATA_HASH_SECRET",
    ]


def test_policy_passing_secrets_are_not_reported_as_insecure() -> None:
    assert insecure_secret_names(_settings("development")) == []


def test_startup_warns_about_default_secrets_by_name_only(caplog, monkeypatch) -> None:
    import app.core.lifespan as lifespan_module

    settings = _settings(
        "development",
        JWT_SECRET_KEY=_JWT_DEFAULT,
        WEBCHAT_METADATA_HASH_SECRET=_WEBCHAT_DEFAULT,
    )
    monkeypatch.setattr(lifespan_module, "get_settings", lambda: settings)
    with caplog.at_level(logging.WARNING):
        lifespan_module.check_startup_secrets()
    warned = [
        record.setting
        for record in caplog.records
        if record.getMessage() == "config.insecure_secret"
    ]
    assert warned == ["JWT_SECRET_KEY", "WEBCHAT_METADATA_HASH_SECRET"]
    assert _JWT_DEFAULT not in caplog.text
    assert _WEBCHAT_DEFAULT not in caplog.text


def test_startup_refuses_unsafe_secrets_without_logging_them(
    caplog, monkeypatch
) -> None:
    import app.core.lifespan as lifespan_module

    settings = _settings("staging", JWT_SECRET_KEY=_JWT_DEFAULT)
    monkeypatch.setattr(lifespan_module, "get_settings", lambda: settings)
    with caplog.at_level(logging.DEBUG), pytest.raises(ValueError):
        lifespan_module.check_startup_secrets()
    assert _JWT_DEFAULT not in caplog.text
