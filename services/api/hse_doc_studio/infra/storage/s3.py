"""Хранилище объектов в S3-совместимом сервисе (AWS, MinIO, Yandex Object Storage, Ceph).

boto3 синхронный, поэтому каждый вызов уходит в ``asyncio.to_thread``. Подпись v4 и path-style
адресация нужны MinIO и Ceph; публичный endpoint для ссылок может отличаться от внутреннего.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import TYPE_CHECKING, Any, BinaryIO

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from hse_doc_studio.core.storage.errors import ChecksumMismatchError, ObjectNotFoundError, ObjectStoreError
from hse_doc_studio.core.storage.keys import is_sha256, validate_key
from hse_doc_studio.core.storage.models import ObjectInfo, PresignedUrl
from hse_doc_studio.core.storage.ports import ByteRange, ObjectSource
from hse_doc_studio.infra.storage.checked import check_source

if TYPE_CHECKING:
    from collections.abc import Callable

_MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound"})
_SHA_METADATA = "sha256"


def build_client_config(*, path_style: bool) -> Config:
    return Config(
        signature_version="s3v4",
        s3={"addressing_style": "path" if path_style else "virtual"},
        retries={"max_attempts": 4, "mode": "standard"},
        connect_timeout=5,
        read_timeout=60,
    )


def cors_rules(origins: Sequence[str]) -> dict[str, Any]:
    return {
        "CORSRules": [
            {
                "AllowedOrigins": list(origins),
                "AllowedMethods": ["GET", "HEAD"],
                "AllowedHeaders": ["Range", "If-Range", "If-None-Match", "If-Modified-Since"],
                "ExposeHeaders": ["Content-Range", "Content-Length", "Accept-Ranges", "ETag"],
                "MaxAgeSeconds": 3600,
            }
        ]
    }


class _HashingReader:
    """Читает источник строго подряд и считает размер и sha256 того, что действительно ушло в S3.

    Без `seek`/`tell`: загрузчик тогда не перечитывает части параллельно и каждый байт виден хешу ровно раз.
    """

    def __init__(self, source: BinaryIO) -> None:
        self._source = source
        self._digest = hashlib.sha256()
        self.size = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._source.read(size)
        self._digest.update(chunk)
        self.size += len(chunk)
        return chunk

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


class S3ObjectStore:
    """``presign_client`` подписывает ссылки для внешнего адреса, ``client`` ходит по внутреннему."""

    def __init__(
        self,
        client: Any,
        bucket: str,
        *,
        max_object_bytes: int,
        multipart_threshold_bytes: int,
        presign_client: Any | None = None,
    ) -> None:
        self._client = client
        self._presign_client = presign_client or client
        self._bucket = bucket
        self._max_bytes = max_object_bytes
        self._multipart_threshold = multipart_threshold_bytes

    async def _call[T](self, fn: Callable[[], T]) -> T:
        try:
            return await asyncio.to_thread(fn)
        except ClientError as exc:
            if _code(exc) in _MISSING_CODES:
                msg = "объекта нет"
                raise ObjectNotFoundError(msg) from exc
            msg = f"S3 отказал: {_code(exc)}"
            raise ObjectStoreError(msg) from exc
        except BotoCoreError as exc:
            msg = f"S3 недоступен: {type(exc).__name__}"
            raise ObjectStoreError(msg) from exc

    async def put(
        self,
        key: str,
        source: ObjectSource,
        *,
        content_type: str | None = None,
        sha256: str | None = None,
    ) -> ObjectInfo:
        validate_key(key)

        def run() -> ObjectInfo:
            from boto3.s3.transfer import TransferConfig  # noqa: PLC0415

            size, actual = check_source(source, max_bytes=self._max_bytes, expected_sha256=sha256)
            extra: dict[str, Any] = {"Metadata": {_SHA_METADATA: actual}}
            if content_type:
                extra["ContentType"] = content_type
            reader = _HashingReader(BytesIO(source) if isinstance(source, bytes) else source)
            self._client.upload_fileobj(
                reader,
                self._bucket,
                key,
                ExtraArgs=extra,
                Config=TransferConfig(multipart_threshold=self._multipart_threshold),
            )
            if reader.size != size or reader.hexdigest() != actual:
                # Источник изменился между проверкой и загрузкой: под ключом-хешем лежали бы чужие байты.
                self._client.delete_object(Bucket=self._bucket, Key=key)
                msg = "источник изменился во время загрузки"
                raise ChecksumMismatchError(msg)
            return ObjectInfo(key=key, size=size, last_modified=datetime.now(UTC), sha256=actual)

        return await self._call(run)

    async def get(self, key: str, *, byte_range: ByteRange | None = None) -> bytes:
        validate_key(key)

        def run() -> bytes:
            args: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
            if byte_range is not None:
                args["Range"] = _range_header(byte_range)
            body = self._client.get_object(**args)["Body"]
            try:
                return bytes(body.read())
            finally:
                body.close()

        return await self._call(run)

    async def stream(self, key: str, *, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        validate_key(key)
        body = await self._call(lambda: self._client.get_object(Bucket=self._bucket, Key=key)["Body"])
        try:
            while chunk := await asyncio.to_thread(body.read, chunk_size):
                yield bytes(chunk)
        finally:
            await asyncio.to_thread(body.close)

    async def head(self, key: str) -> ObjectInfo | None:
        validate_key(key)
        try:
            raw = await self._call(lambda: self._client.head_object(Bucket=self._bucket, Key=key))
        except ObjectNotFoundError:
            return None
        return ObjectInfo(
            key=key,
            size=int(raw["ContentLength"]),
            last_modified=raw["LastModified"],
            sha256=_sha_of(raw.get("Metadata", {})),
            etag=str(raw.get("ETag", "")).strip('"') or None,
        )

    async def delete(self, key: str) -> None:
        validate_key(key)
        await self._call(lambda: self._client.delete_object(Bucket=self._bucket, Key=key))

    async def list_objects(self, prefix: str = "") -> list[ObjectInfo]:
        def run() -> list[ObjectInfo]:
            found: list[ObjectInfo] = []
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                found.extend(
                    ObjectInfo(
                        key=item["Key"],
                        size=int(item["Size"]),
                        last_modified=item["LastModified"],
                        etag=str(item.get("ETag", "")).strip('"') or None,
                    )
                    for item in page.get("Contents", [])
                )
            return sorted(found, key=lambda info: info.key)

        return await self._call(run)

    async def presign_get(self, key: str, *, expires_in_s: int = 300) -> PresignedUrl | None:
        validate_key(key)
        return await self._presign("get_object", {"Bucket": self._bucket, "Key": key}, expires_in_s, {})

    async def presign_put(
        self, key: str, *, expires_in_s: int = 300, content_type: str | None = None
    ) -> PresignedUrl | None:
        validate_key(key)
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        headers: dict[str, str] = {}
        if content_type:
            params["ContentType"] = content_type
            headers["Content-Type"] = content_type
        return await self._presign("put_object", params, expires_in_s, headers)

    async def _presign(
        self, operation: str, params: dict[str, Any], expires_in_s: int, headers: dict[str, str]
    ) -> PresignedUrl:
        url = await self._call(
            lambda: self._presign_client.generate_presigned_url(operation, Params=params, ExpiresIn=expires_in_s)
        )
        return PresignedUrl(url=url, expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_s), headers=headers)

    async def check(self) -> None:
        await self._call(lambda: self._client.head_bucket(Bucket=self._bucket))

    async def apply_cors(self, origins: Sequence[str]) -> None:
        """Выставляет CORS бакета под чтение по подписанным ссылкам (GET и HEAD с Range)."""
        rules = cors_rules(origins)
        await self._call(lambda: self._client.put_bucket_cors(Bucket=self._bucket, CORSConfiguration=rules))


def _code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def _range_header(byte_range: ByteRange) -> str:
    start, end = byte_range
    return f"bytes={start}-" if end is None else f"bytes={start}-{end}"


def _sha_of(metadata: dict[str, str]) -> str | None:
    value = metadata.get(_SHA_METADATA)
    return value if value is not None and is_sha256(value) else None
