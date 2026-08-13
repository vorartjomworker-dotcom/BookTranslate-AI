import asyncio
import io

import pytest

from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


class FakeBody:
    def __init__(self, value: bytes):
        self.value = value

    def read(self) -> bytes:
        return self.value


class FakeS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = bytes(Body)

    def get_object(self, *, Bucket, Key):
        return {"Body": FakeBody(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject")
        return {}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://objects.test/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"


async def _run_local(tmp_path) -> None:
    storage = LocalStorage(tmp_path)
    await storage.put_bytes("assets/book/image.png", b"payload", content_type="image/png")
    assert await storage.exists("assets/book/image.png")
    assert await storage.get_bytes("assets/book/image.png") == b"payload"
    await storage.delete("assets/book/image.png")
    assert not await storage.exists("assets/book/image.png")
    with pytest.raises(ValueError):
        await storage.put_bytes("../escape", b"x")


async def _run_s3() -> None:
    client = FakeS3Client()
    storage = S3Storage(
        bucket="books",
        endpoint_url="http://minio:9000",
        region="us-east-1",
        access_key="test",
        secret_key="test",
        use_ssl=False,
        addressing_style="path",
        client=client,
    )
    await storage.put_bytes("renders/a.png", b"png", content_type="image/png")
    assert await storage.exists("renders/a.png")
    assert await storage.get_bytes("renders/a.png") == b"png"
    assert (await storage.presign_get_url("renders/a.png", expires_seconds=90)) == "https://objects.test/books/renders/a.png?expires=90"
    await storage.delete("renders/a.png")
    assert not await storage.exists("renders/a.png")
    with pytest.raises(ValueError):
        await storage.get_bytes("../../secret")


def test_local_storage_round_trip(tmp_path) -> None:
    asyncio.run(_run_local(tmp_path))


def test_s3_storage_contract() -> None:
    asyncio.run(_run_s3())
