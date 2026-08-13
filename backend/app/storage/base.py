from __future__ import annotations

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    async def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def exists(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def presign_get_url(self, key: str, *, expires_seconds: int) -> str | None:
        return None
