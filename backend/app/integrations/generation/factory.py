"""Generation provider factory."""

from app.core.config import Settings, get_settings
from app.core.exceptions import GenerationConfigurationError
from app.integrations.generation.base import GenerationProvider
from app.integrations.generation.development import DevelopmentGenerationProvider
from app.integrations.generation.openai import OpenAIGenerationProvider


def create_generation_provider(settings: Settings | None = None) -> GenerationProvider:
    configured = settings or get_settings()
    provider = configured.GENERATION_PROVIDER.strip().lower()
    if provider == "development":
        return DevelopmentGenerationProvider()
    if provider == "openai":
        if not configured.OPENAI_API_KEY:
            raise GenerationConfigurationError()
        return OpenAIGenerationProvider(
            api_key=configured.OPENAI_API_KEY,
            model=configured.OPENAI_MODEL,
            timeout_seconds=configured.GENERATION_REQUEST_TIMEOUT_SECONDS,
        )
    raise GenerationConfigurationError()
