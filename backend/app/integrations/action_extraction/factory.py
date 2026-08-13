"""Action field extraction provider factory."""

from app.core.config import Settings, get_settings
from app.core.exceptions import ActionCollectionProviderError
from app.integrations.action_extraction.base import ActionFieldExtractionProvider
from app.integrations.action_extraction.development import (
    DevelopmentActionFieldExtractionProvider,
)
from app.integrations.action_extraction.generation import (
    GenerationActionFieldExtractionProvider,
)
from app.integrations.generation import GenerationProvider, create_generation_provider


def create_action_field_extraction_provider(
    settings: Settings | None = None,
    generation: GenerationProvider | None = None,
) -> ActionFieldExtractionProvider:
    configured = settings or get_settings()
    provider = configured.ACTION_COLLECTION_PROVIDER.strip().lower()
    if provider == "development" and configured.APP_ENV != "production":
        return DevelopmentActionFieldExtractionProvider()
    if provider == "generation":
        if configured.GENERATION_PROVIDER.strip().lower() == "development":
            raise ActionCollectionProviderError()
        return GenerationActionFieldExtractionProvider(
            generation or create_generation_provider(configured)
        )
    raise ActionCollectionProviderError()
