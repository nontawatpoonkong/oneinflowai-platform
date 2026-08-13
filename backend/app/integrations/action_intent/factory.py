"""Configured Action Intent provider selection."""

from app.core.config import Settings, get_settings
from app.core.exceptions import ActionCollectionProviderError
from app.integrations.action_intent.base import ActionIntentProvider
from app.integrations.action_intent.development import DevelopmentActionIntentProvider
from app.integrations.action_intent.generation import GenerationActionIntentProvider
from app.integrations.generation import GenerationProvider, create_generation_provider


def create_action_intent_provider(
    settings: Settings | None = None,
    generation: GenerationProvider | None = None,
) -> ActionIntentProvider:
    configured = settings or get_settings()
    if configured.APP_ENV == "production":
        if configured.GENERATION_PROVIDER.strip().lower() == "development":
            raise ActionCollectionProviderError()
        return GenerationActionIntentProvider(
            generation or create_generation_provider(configured)
        )
    return DevelopmentActionIntentProvider()
