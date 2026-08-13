from __future__ import annotations

import asyncio
from pathlib import Path

from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Storage key escapes local storage root")
        return candidate

    async def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not await asyncio.to_thread(path.is_file):
            raise FileNotFoundError(key)
        return await asyncio.to_thread(path.read_bytes)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).is_file)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)
