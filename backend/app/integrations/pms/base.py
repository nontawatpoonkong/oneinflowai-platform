"""Read-only PMS provider contract. Outbound mutation methods do not exist."""

from abc import ABC, abstractmethod

from app.integrations.pms.contracts import (
    ImportedInventoryDay,
    ImportedProperty,
    ImportedRatePlan,
    ImportedReservation,
    ImportedRoom,
    ImportedRoomType,
    PMSConnectionTestResult,
    PMSImportPage,
    PMSProviderCapabilities,
)


class PMSProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def capabilities(self) -> PMSProviderCapabilities: ...

    @abstractmethod
    async def test_connection(self) -> PMSConnectionTestResult: ...

    async def list_properties(
        self, cursor: str | None
    ) -> PMSImportPage[ImportedProperty]:
        return self._unsupported("properties")

    async def fetch_room_types(
        self, cursor: str | None
    ) -> PMSImportPage[ImportedRoomType]:
        return self._unsupported("room_types")

    async def fetch_rooms(self, cursor: str | None) -> PMSImportPage[ImportedRoom]:
        return self._unsupported("physical_rooms")

    async def fetch_rate_plans(
        self, cursor: str | None
    ) -> PMSImportPage[ImportedRatePlan]:
        return self._unsupported("rate_plans")

    async def fetch_inventory(
        self, cursor: str | None
    ) -> PMSImportPage[ImportedInventoryDay]:
        return self._unsupported("inventory")

    async def fetch_reservations(
        self, cursor: str | None
    ) -> PMSImportPage[ImportedReservation]:
        return self._unsupported("reservations")

    @staticmethod
    def _unsupported(capability: str):
        from app.integrations.pms.errors import PMSUnsupportedCapabilityError

        raise PMSUnsupportedCapabilityError(capability)
