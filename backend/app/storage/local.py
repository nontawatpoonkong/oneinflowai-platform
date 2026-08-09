"""Local filesystem storage for development and self-hosting."""

import asyncio
from pathlib import Path

from app.storage.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if self.root not in target.parents:
            raise ValueError("Invalid storage key")
        return target

    async def save(self, *, key: str, data: bytes) -> None:
        target = self._path(key)

        def _write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        await asyncio.to_thread(_write)

    async def read(self, *, key: str) -> bytes:
        target = self._path(key)
        return await asyncio.to_thread(target.read_bytes)

    async def delete(self, *, key: str) -> None:
        target = self._path(key)

        def _delete() -> None:
            target.unlink(missing_ok=True)

        await asyncio.to_thread(_delete)
