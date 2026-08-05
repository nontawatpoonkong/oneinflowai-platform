"""Provider-neutral binary object storage contract."""

from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    async def save(self, *, key: str, data: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, *, key: str) -> None:
        raise NotImplementedError
