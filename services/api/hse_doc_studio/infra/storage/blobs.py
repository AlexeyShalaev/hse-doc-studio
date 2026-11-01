"""IBlobStore поверх IObjectStore: ключ блоба равен его sha256."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Collection

from hse_doc_studio.core.storage.errors import ChecksumMismatchError
from hse_doc_studio.core.storage.hashing import measure
from hse_doc_studio.core.storage.keys import blob_key, is_sha256
from hse_doc_studio.core.storage.models import BlobInfo, PresignedUrl
from hse_doc_studio.core.storage.ports import ByteRange, IObjectStore, ObjectSource

_HEAD_CONCURRENCY = 16
_VERIFY_CHUNK = 1024 * 1024


class ObjectBlobStore:
    def __init__(self, store: IObjectStore) -> None:
        self._store = store

    async def put(self, source: ObjectSource, *, sha256: str | None = None) -> BlobInfo:
        size, actual = await asyncio.to_thread(measure, source)
        if sha256 is not None and sha256 != actual:
            msg = "sha256 данных не совпал с заявленным"
            raise ChecksumMismatchError(msg)
        if (existing := await self._store.head(blob_key(actual))) is not None and existing.size == size:
            return BlobInfo(sha256=actual, size=size)
        info = await self._store.put(blob_key(actual), source, sha256=actual)
        return BlobInfo(sha256=actual, size=info.size)

    async def has_many(self, shas: Collection[str]) -> set[str]:
        unique = set(shas)
        gate = asyncio.Semaphore(_HEAD_CONCURRENCY)

        async def present(sha: str) -> bool:
            async with gate:
                return await self._store.head(blob_key(sha)) is not None

        ordered = sorted(unique)
        flags = await asyncio.gather(*(present(sha) for sha in ordered))
        return {sha for sha, flag in zip(ordered, flags, strict=True) if flag}

    async def head(self, sha256: str) -> BlobInfo | None:
        info = await self._store.head(blob_key(sha256))
        return None if info is None else BlobInfo(sha256=sha256, size=info.size)

    async def get(self, sha256: str, *, byte_range: ByteRange | None = None) -> bytes:
        return await self._store.get(blob_key(sha256), byte_range=byte_range)

    def stream(self, sha256: str, *, chunk_size: int = _VERIFY_CHUNK) -> AsyncIterator[bytes]:
        return self._store.stream(blob_key(sha256), chunk_size=chunk_size)

    async def delete(self, sha256: str) -> None:
        await self._store.delete(blob_key(sha256))

    async def presign_get(self, sha256: str, *, expires_in_s: int = 300) -> PresignedUrl | None:
        return await self._store.presign_get(blob_key(sha256), expires_in_s=expires_in_s)

    async def presign_put(self, sha256: str, *, expires_in_s: int = 300) -> PresignedUrl | None:
        return await self._store.presign_put(blob_key(sha256), expires_in_s=expires_in_s)

    async def verify(self, sha256: str) -> BlobInfo:
        if not is_sha256(sha256):
            msg = "sha256 должен быть 64 строчными шестнадцатеричными цифрами"
            raise ChecksumMismatchError(msg)
        digest = hashlib.sha256()
        size = 0
        async for chunk in self._store.stream(blob_key(sha256)):
            digest.update(chunk)
            size += len(chunk)
        if digest.hexdigest() != sha256:
            await self._store.delete(blob_key(sha256))
            msg = "залитый блоб не совпал по sha256 и удалён"
            raise ChecksumMismatchError(msg)
        return BlobInfo(sha256=sha256, size=size)
