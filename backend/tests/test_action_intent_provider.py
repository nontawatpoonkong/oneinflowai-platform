"""Production Action Intent structured-generation boundary tests."""

import pytest

from app.core.config import Settings
from app.core.exceptions import ActionCollectionProviderError
from app.integrations.action_intent import (
    ActionIntentOption,
    ActionIntentRequest,
    GenerationActionIntentProvider,
    create_action_intent_provider,
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


def _request() -> ActionIntentRequest:
    return ActionIntentRequest(
        "please open a ticket",
        (ActionIntentOption("ticket", "Ticket", "Support request"),),
    )


@pytest.mark.asyncio
async def test_production_intent_uses_configured_generation_provider() -> None:
    generation = FakeGeneration(
        '{"selected_action_key":"ticket","confidence":1.0,"field_input":null}'
    )
    provider = create_action_intent_provider(
        Settings(
            _env_file=None,
            APP_ENV="production",
            GENERATION_PROVIDER="openai",
        ),
        generation,
    )
    assert isinstance(provider, GenerationActionIntentProvider)
    result = await provider.route(_request())
    assert result.selected_action_key == "ticket"
    assert generation.requests[0].output_schema_name == "action_intent"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "not-json",
        '{"selected_action_key":"admin","confidence":1.0,"field_input":null}',
        '{"selected_action_key":"ticket","confidence":"1","field_input":null}',
    ],
)
async def test_intent_malformed_unknown_or_wrong_type_fails_closed(text: str) -> None:
    with pytest.raises(ActionCollectionProviderError):
        await GenerationActionIntentProvider(FakeGeneration(text)).route(_request())


def test_production_intent_rejects_development_generation() -> None:
    with pytest.raises(ActionCollectionProviderError):
        create_action_intent_provider(
            Settings(
                _env_file=None,
                APP_ENV="production",
                GENERATION_PROVIDER="development",
            )
        )
