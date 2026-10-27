"""Provider-neutral, read-only PMS integration boundary."""

from app.integrations.pms.base import PMSProvider
from app.integrations.pms.registry import PMSProviderRegistry, get_pms_provider_registry

__all__ = ["PMSProvider", "PMSProviderRegistry", "get_pms_provider_registry"]
