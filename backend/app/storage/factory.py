"""Storage provider selection."""

from app.core.config import Settings, get_settings
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider


def create_storage_provider(settings: Settings | None = None) -> StorageProvider:
    resolved = settings or get_settings()
    provider = resolved.STORAGE_PROVIDER.strip().lower()
    if provider == "local":
        return LocalStorageProvider(resolved.STORAGE_LOCAL_PATH)
    raise ValueError("Unsupported STORAGE_PROVIDER configuration")
