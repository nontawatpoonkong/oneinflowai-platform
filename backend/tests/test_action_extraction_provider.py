"""Deterministic provider-neutral action field extraction tests."""

import pytest

from app.core.config import Settings
from app.core.exceptions import ActionCollectionProviderError
from app.integrations.action_extraction import (
    ActionFieldExtractionRequest,
    DevelopmentActionFieldExtractionProvider,
    GenerationActionFieldExtractionProvider,
    create_action_field_extraction_provider,
)
from app.integrations.generation import GenerationResult


class FakeGeneration:
    name = "openai"

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return GenerationResult(self.text, "test-model", self.name)


@pytest.mark.asyncio
async def test_development_extractor_is_deterministic_and_preserves_unicode() -> None:
    provider = DevelopmentActionFieldExtractionProvider()
    request = ActionFieldExtractionRequest(
        field_schema=({"key": "note", "type": "string"},),
        user_input='{"note":"ส่ง Asia server ให้ Non#TH1"}',
        collected_payload={},
    )
    first = await provider.extract(request)
    second = await provider.extract(request)
    assert first == second
    assert first.candidates == {"note": "ส่ง Asia server ให้ Non#TH1"}


@pytest.mark.asyncio
async def test_development_extractor_rejects_malformed_output_safely() -> None:
    provider = DevelopmentActionFieldExtractionProvider()
    with pytest.raises(ActionCollectionProviderError):
        await provider.extract(ActionFieldExtractionRequest((), "not-json", {}))
    with pytest.raises(ActionCollectionProviderError):
        await provider.extract(ActionFieldExtractionRequest((), "[]", {}))


def test_extraction_factory_has_no_implicit_network_provider() -> None:
    provider = create_action_field_extraction_provider(
        Settings(_env_file=None, ACTION_COLLECTION_PROVIDER="development")
    )
    assert isinstance(provider, DevelopmentActionFieldExtractionProvider)
    with pytest.raises(ActionCollectionProviderError):
        create_action_field_extraction_provider(
            Settings(_env_file=None, ACTION_COLLECTION_PROVIDER="unknown")
        )


@pytest.mark.asyncio
async def test_production_extraction_uses_configured_generation_provider() -> None:
    generation = FakeGeneration('{"candidates":{"server":"Asia"}}')
    provider = create_action_field_extraction_provider(
        Settings(
            _env_file=None,
            APP_ENV="production",
            ACTION_COLLECTION_PROVIDER="generation",
            GENERATION_PROVIDER="openai",
        ),
        generation,
    )
    assert isinstance(provider, GenerationActionFieldExtractionProvider)
    result = await provider.extract(
        ActionFieldExtractionRequest(
            field_schema=(
                {"key": "server", "label": "Server", "type": "enum"},
            ),
            user_input="Asia",
            collected_payload={},
        )
    )
    assert result.candidates == {"server": "Asia"}
    assert generation.requests[0].output_schema_name == "action_fields"


def test_production_extraction_rejects_development_provider() -> None:
    with pytest.raises(ActionCollectionProviderError):
        create_action_field_extraction_provider(
            Settings(
                _env_file=None,
                APP_ENV="production",
                ACTION_COLLECTION_PROVIDER="development",
            )
        )


@pytest.mark.asyncio
async def test_generation_extraction_fails_closed_on_bad_output() -> None:
    request = ActionFieldExtractionRequest(
        field_schema=({"key": "server", "label": "Server", "type": "enum"},),
        user_input="untrusted",
        collected_payload={},
    )
    for text in ("not-json", '{"candidates":{"admin":true}}'):
        with pytest.raises(ActionCollectionProviderError):
            await GenerationActionFieldExtractionProvider(
                FakeGeneration(text)
            ).extract(request)
