"""Deterministic in-memory PMS adapter used only by tests."""

from collections import defaultdict
from typing import Any

from app.integrations.pms.base import PMSProvider
from app.integrations.pms.contracts import (
    PMSConnectionTestResult,
    PMSImportPage,
    PMSProviderCapabilities,
)
from app.integrations.pms.errors import (
    PMSAuthenticationError,
    PMSInvalidResponseError,
    PMSRateLimitError,
    PMSTimeoutError,
)


class FakePMSProvider(PMSProvider):
    """Inject typed pages/failures without network access."""

    def __init__(
        self,
        credentials: dict[str, str] | None = None,
        *,
        pages: dict[str, list[PMSImportPage[Any]]] | None = None,
        failure: str | None = None,
        capabilities: PMSProviderCapabilities | None = None,
    ) -> None:
        self.credentials = credentials or {}
        self.pages = pages or {}
        self.failure = failure
        self.calls: dict[str, int] = defaultdict(int)
        self._capabilities = capabilities or PMSProviderCapabilities(
            properties=True,
            room_types=True,
            physical_rooms=True,
            rate_plans=True,
            inventory=True,
            reservations=False,
            incremental_sync=True,
            pagination=True,
        )

    @property
    def name(self) -> str:
        return "fake"

    @property
    def capabilities(self) -> PMSProviderCapabilities:
        return self._capabilities

    async def test_connection(self) -> PMSConnectionTestResult:
        self._raise_if_needed()
        return PMSConnectionTestResult(
            account_id="fake-account", account_name="Fake PMS"
        )

    def _raise_if_needed(self) -> None:
        failures = {
            "auth": PMSAuthenticationError,
            "rate_limit": PMSRateLimitError,
            "timeout": PMSTimeoutError,
            "invalid": PMSInvalidResponseError,
        }
        if self.failure:
            raise failures[self.failure]()

    async def _page(self, key: str, cursor: str | None):
        self.calls[key] += 1
        self._raise_if_needed()
        index = int(cursor or 0)
        values = self.pages.get(key, [])
        return values[index] if index < len(values) else PMSImportPage(items=())

    async def list_properties(self, cursor):
        return await self._page("properties", cursor)

    async def fetch_room_types(self, cursor):
        return await self._page("room_types", cursor)

    async def fetch_rooms(self, cursor):
        return await self._page("rooms", cursor)

    async def fetch_rate_plans(self, cursor):
        return await self._page("rate_plans", cursor)

    async def fetch_inventory(self, cursor):
        return await self._page("inventory", cursor)

    async def fetch_reservations(self, cursor):
        return await self._page("reservations", cursor)
