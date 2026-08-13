from __future__ import annotations

from app.core.config import Settings, settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


def create_storage(config: Settings = settings) -> StorageBackend:
    backend = config.storage_backend.strip().lower()
    if backend == "local":
        return LocalStorage(config.upload_dir)
    if backend in {"s3", "minio"}:
        if not config.s3_bucket:
            raise RuntimeError("S3_BUCKET is required for S3/MinIO storage")
        return S3Storage(
            bucket=config.s3_bucket,
            endpoint_url=config.s3_endpoint_url,
            region=config.s3_region,
            access_key=config.s3_access_key,
            secret_key=config.s3_secret_key,
            use_ssl=config.s3_use_ssl,
            addressing_style=config.s3_addressing_style,
        )
    raise RuntimeError(f"Unsupported STORAGE_BACKEND: {config.storage_backend}")
