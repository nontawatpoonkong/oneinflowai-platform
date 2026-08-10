"""Action field extraction provider factory."""

from app.core.config import Settings, get_settings
from app.core.exceptions import ActionCollectionProviderError
from app.integrations.action_extraction.base import ActionFieldExtractionProvider
from app.integrations.action_extraction.development import (
    DevelopmentActionFieldExtractionProvider,
)


def create_action_field_extraction_provider(
    settings: Settings | None = None,
) -> ActionFieldExtractionProvider:
    configured = settings or get_settings()
    if configured.ACTION_COLLECTION_PROVIDER.strip().lower() == "development":
        return DevelopmentActionFieldExtractionProvider()
    raise ActionCollectionProviderError()
