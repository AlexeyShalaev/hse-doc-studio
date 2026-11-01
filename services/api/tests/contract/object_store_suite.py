"""Общий набор проверок IObjectStore; наследники подставляют fs и S3."""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any

import pytest
from hse_doc_studio.core.storage import (
    ChecksumMismatchError,
    InvalidObjectKeyError,
    ObjectNotFoundError,
    ObjectTooLargeError,
)

PAYLOAD = b"%PDF-1.7 " + bytes(range(256)) * 8


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ObjectStoreContract:
    async def test__put_get__roundtrip(self, port: Any) -> None:
        info = await port.put("artifacts/p/a.pdf", PAYLOAD, content_type="application/pdf")

        assert info.size == len(PAYLOAD)
        assert info.sha256 == sha(PAYLOAD)
        assert await port.get("artifacts/p/a.pdf") == PAYLOAD

    async def test__put__stream_source_from_current_position(self, port: Any) -> None:
        stream = BytesIO(b"skip" + PAYLOAD)
        stream.seek(4)

        info = await port.put("k/stream", stream)

        assert info.size == len(PAYLOAD)
        assert await port.get("k/stream") == PAYLOAD

    async def test__put__overwrites_existing(self, port: Any) -> None:
        await port.put("k/x", b"one")
        await port.put("k/x", b"second")

        assert await port.get("k/x") == b"second"

    async def test__put__wrong_sha256__refused_and_nothing_written(self, port: Any) -> None:
        with pytest.raises(ChecksumMismatchError):
            await port.put("k/bad", PAYLOAD, sha256=sha(b"other"))

        assert await port.head("k/bad") is None
        assert await port.list_objects() == []

    async def test__put__wrong_sha256_over_existing__keeps_old_object(self, port: Any) -> None:
        await port.put("k/keep", b"old")

        with pytest.raises(ChecksumMismatchError):
            await port.put("k/keep", PAYLOAD, sha256=sha(b"other"))

        assert await port.get("k/keep") == b"old"

    async def test__put__right_sha256__accepted(self, port: Any) -> None:
        info = await port.put("k/ok", PAYLOAD, sha256=sha(PAYLOAD))

        assert info.sha256 == sha(PAYLOAD)

    async def test__put__malformed_sha256__refused(self, port: Any) -> None:
        with pytest.raises(ChecksumMismatchError):
            await port.put("k/bad", PAYLOAD, sha256="abc")

    async def test__get__missing__raises_not_found(self, port: Any) -> None:
        with pytest.raises(ObjectNotFoundError):
            await port.get("k/missing")

    async def test__stream__missing__raises_not_found(self, port: Any) -> None:
        with pytest.raises(ObjectNotFoundError):
            async for _ in port.stream("k/missing"):
                pass

    async def test__get__byte_range__returns_slice(self, port: Any) -> None:
        await port.put("k/r", PAYLOAD)

        assert await port.get("k/r", byte_range=(2, 9)) == PAYLOAD[2:10]
        assert await port.get("k/r", byte_range=(len(PAYLOAD) - 5, None)) == PAYLOAD[-5:]

    async def test__stream__yields_all_bytes_in_chunks(self, port: Any) -> None:
        await port.put("k/s", PAYLOAD)

        chunks = [chunk async for chunk in port.stream("k/s", chunk_size=100)]

        assert b"".join(chunks) == PAYLOAD
        assert len(chunks) > 1

    async def test__head__existing_and_missing(self, port: Any) -> None:
        await port.put("k/h", b"12345")

        info = await port.head("k/h")

        assert info is not None
        assert (info.key, info.size) == ("k/h", 5)
        assert await port.head("k/none") is None

    async def test__delete__removes_and_is_idempotent(self, port: Any) -> None:
        await port.put("k/d", b"x")

        await port.delete("k/d")
        await port.delete("k/d")

        assert await port.head("k/d") is None

    async def test__list_objects__filters_by_prefix_sorted(self, port: Any) -> None:
        for key in ("a/2", "a/1", "b/1", "a/sub/3"):
            await port.put(key, b"x")

        assert [i.key for i in await port.list_objects("a/")] == ["a/1", "a/2", "a/sub/3"]
        assert [i.key for i in await port.list_objects()] == ["a/1", "a/2", "a/sub/3", "b/1"]
        assert await port.list_objects("zz/") == []

    @pytest.mark.parametrize("key", ["", "/abs", "a/../b", "a//b", "../x", ".hidden/x", "a/.tmp/x", "a\\b", "a/\x00b"])
    async def test__any_operation__unsafe_key__refused(self, port: Any, key: str) -> None:
        with pytest.raises(InvalidObjectKeyError):
            await port.put(key, b"x")
        with pytest.raises(InvalidObjectKeyError):
            await port.get(key)
        with pytest.raises(InvalidObjectKeyError):
            await port.delete(key)

    async def test__check__reachable_store__passes(self, port: Any) -> None:
        await port.check()

    async def test__put__over_limit__refused_and_nothing_written(self, small_port: Any) -> None:
        with pytest.raises(ObjectTooLargeError):
            await small_port.put("k/big", b"x" * 11)

        assert await small_port.head("k/big") is None
