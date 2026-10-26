"""Explicit provider registry with no dynamic imports or vendor fallback."""

from collections.abc import Callable

from app.integrations.pms.base import PMSProvider

PMSProviderFactory = Callable[[dict[str, str]], PMSProvider]


class PMSProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, PMSProviderFactory] = {}

    def register(self, name: str, factory: PMSProviderFactory) -> None:
        normalized = name.strip().lower()
        if not normalized or normalized in self._factories:
            raise ValueError("PMS provider name is invalid or already registered")
        self._factories[normalized] = factory

    def create(self, name: str, credentials: dict[str, str]) -> PMSProvider:
        factory = self._factories.get(name.strip().lower())
        if factory is None:
            raise ValueError("Unknown PMS provider")
        return factory(credentials)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


_registry = PMSProviderRegistry()


def get_pms_provider_registry() -> PMSProviderRegistry:
    return _registry
