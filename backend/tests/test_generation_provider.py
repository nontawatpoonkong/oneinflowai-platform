"""Provider contract, OpenAI normalization, and safe error mapping tests."""

from types import SimpleNamespace

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from app.core.config import Settings
from app.core.exceptions import (
    GenerationAuthenticationError,
    GenerationConfigurationError,
    GenerationMalformedResponseError,
    GenerationNetworkError,
    GenerationRateLimitError,
    GenerationServerError,
    GenerationTimeoutError,
)
from app.integrations.generation import (
    DevelopmentGenerationProvider,
    GenerationRequest,
    OpenAIGenerationProvider,
    create_generation_provider,
)

PROMPT = GenerationRequest("system", "user", 0.2, 800)


class FakeResponses:
    def __init__(self, response=None, failure=None):
        self.response = response
        self.failure = failure
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        return self.response


def _provider(
    api: FakeResponses, model: str = "gpt-5.5"
) -> OpenAIGenerationProvider:
    return OpenAIGenerationProvider(
        api_key="test",
        model=model,
        timeout_seconds=45,
        client=SimpleNamespace(responses=api),
    )


@pytest.mark.asyncio
async def test_development_provider_is_deterministic_without_network() -> None:
    provider = DevelopmentGenerationProvider()
    assert await provider.generate(PROMPT) == await provider.generate(PROMPT)
    assert (await provider.generate(PROMPT)).text.endswith("[S1]")


@pytest.mark.asyncio
async def test_openai_provider_maps_request_and_normalizes_result_and_usage() -> None:
    response = SimpleNamespace(
        output_text=" grounded [S1] ",
        model="gpt-5.5",
        status="completed",
        usage=SimpleNamespace(input_tokens=10, output_tokens=4, total_tokens=14),
    )
    api = FakeResponses(response)
    result = await _provider(api).generate(PROMPT)
    assert api.calls == [
        {
            "model": "gpt-5.5",
            "instructions": "system",
            "input": "user",
            "max_output_tokens": 800,
            "timeout": 45,
        }
    ]
    assert result.text == "grounded [S1]"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (
        10,
        4,
        14,
    )
    assert result.provider == "openai"


@pytest.mark.asyncio
async def test_openai_temperature_compatible_model_keeps_temperature() -> None:
    api = FakeResponses(SimpleNamespace(output_text="ok", model="gpt-4o-mini"))

    await _provider(api, model="gpt-4o-mini").generate(PROMPT)

    assert api.calls[0]["temperature"] == 0.2
    assert api.calls[0]["max_output_tokens"] == 800


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model",
    [
        "gpt-5.5",
        "gpt-5.5-2026-04-23",
        "gpt-5.6-terra",
        "gpt-5.6-terra-2026-04-23",
        "gpt-5.6-luna",
        "gpt-5.6-luna-2026-04-23",
    ],
)
async def test_openai_unsupported_model_family_omits_temperature(
    model: str,
) -> None:
    api = FakeResponses(SimpleNamespace(output_text='{"ok":true}', model=model))
    prompt = GenerationRequest(
        "system",
        "user",
        0,
        16,
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        output_schema_name="compatibility_check",
    )

    await _provider(api, model=model).generate(prompt)

    assert "temperature" not in api.calls[0]
    assert api.calls[0]["max_output_tokens"] == 16
    assert api.calls[0]["text"] == {
        "format": {
            "type": "json_schema",
            "name": "compatibility_check",
            "schema": prompt.output_schema,
            "strict": True,
        }
    }


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.test/responses")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (
            AuthenticationError(
                "auth", response=httpx.Response(401, request=_request()), body=None
            ),
            GenerationAuthenticationError,
        ),
        (
            RateLimitError(
                "rate", response=httpx.Response(429, request=_request()), body=None
            ),
            GenerationRateLimitError,
        ),
        (APITimeoutError(request=_request()), GenerationTimeoutError),
        (APIConnectionError(request=_request()), GenerationNetworkError),
        (
            APIStatusError(
                "server", response=httpx.Response(500, request=_request()), body=None
            ),
            GenerationServerError,
        ),
    ],
)
async def test_openai_provider_maps_operational_errors(failure, expected) -> None:
    with pytest.raises(expected) as captured:
        await _provider(FakeResponses(failure=failure)).generate(PROMPT)
    assert "api" not in str(captured.value).lower()


@pytest.mark.asyncio
async def test_openai_provider_rejects_malformed_response() -> None:
    with pytest.raises(GenerationMalformedResponseError):
        await _provider(
            FakeResponses(SimpleNamespace(output_text="", model="gpt-5.5"))
        ).generate(PROMPT)


def test_generation_factory_selects_development_and_rejects_unknown() -> None:
    settings = Settings(_env_file=None, GENERATION_PROVIDER="development")
    assert isinstance(
        create_generation_provider(settings), DevelopmentGenerationProvider
    )
    with pytest.raises(GenerationConfigurationError):
        create_generation_provider(
            Settings(_env_file=None, GENERATION_PROVIDER="unknown")
        )
