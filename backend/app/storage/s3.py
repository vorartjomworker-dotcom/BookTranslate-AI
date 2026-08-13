from __future__ import annotations

import asyncio
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.storage.base import StorageBackend


class S3Storage(StorageBackend):
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str,
        access_key: str | None,
        secret_key: str | None,
        use_ssl: bool,
        addressing_style: str,
        presign_downloads: bool = False,
        client: Any | None = None,
    ):
        self.bucket = bucket
        self.presign_downloads = presign_downloads
        self.client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            use_ssl=use_ssl,
            config=Config(signature_version="s3v4", s3={"addressing_style": addressing_style}),
        )

    @staticmethod
    def _validate_key(key: str) -> str:
        value = key.strip().lstrip("/")
        if not value or value.startswith("../") or "/../" in value or value == "..":
            raise ValueError("Invalid object storage key")
        return value

    async def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        object_key = self._validate_key(key)
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Key": object_key, "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type
        await asyncio.to_thread(self.client.put_object, **kwargs)

    async def get_bytes(self, key: str) -> bytes:
        object_key = self._validate_key(key)
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=object_key)
        return await asyncio.to_thread(response["Body"].read)

    async def exists(self, key: str) -> bool:
        object_key = self._validate_key(key)
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=object_key)
            return True
        except ClientError as exc:
            status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)
            if status == 404 or exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    async def delete(self, key: str) -> None:
        object_key = self._validate_key(key)
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=object_key)

    async def presign_get_url(self, key: str, *, expires_seconds: int) -> str | None:
        if not self.presign_downloads:
            return None
        object_key = self._validate_key(key)
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=expires_seconds,
        )
