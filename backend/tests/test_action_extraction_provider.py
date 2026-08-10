"""Deterministic provider-neutral action field extraction tests."""

import pytest

from app.core.config import Settings
from app.core.exceptions import ActionCollectionProviderError
from app.integrations.action_extraction import (
    ActionFieldExtractionRequest,
    DevelopmentActionFieldExtractionProvider,
    create_action_field_extraction_provider,
)


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
