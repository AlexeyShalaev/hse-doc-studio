from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from hse_doc_studio.core.storage import ChecksumMismatchError, InvalidObjectKeyError, ObjectNotFoundError, blob_key
from hse_doc_studio.infra.storage.blobs import ObjectBlobStore
from hse_doc_studio.infra.storage.fs import FsObjectStore

DATA = b"hello blob" * 100
SHA = hashlib.sha256(DATA).hexdigest()


@pytest.fixture
def objects(tmp_path: Path) -> FsObjectStore:
    return FsObjectStore(tmp_path / "objects", max_object_bytes=1024 * 1024)


@pytest.fixture
def blobs(objects: FsObjectStore) -> ObjectBlobStore:
    return ObjectBlobStore(objects)


async def test__put__without_sha__hash_computed_and_stored_by_key(
    blobs: ObjectBlobStore, objects: FsObjectStore
) -> None:
    info = await blobs.put(DATA)

    assert (info.sha256, info.size) == (SHA, len(DATA))
    assert await objects.get(blob_key(SHA)) == DATA


async def test__put__wrong_sha__refused_and_nothing_written(blobs: ObjectBlobStore, objects: FsObjectStore) -> None:
    with pytest.raises(ChecksumMismatchError):
        await blobs.put(DATA, sha256=hashlib.sha256(b"other").hexdigest())

    assert await objects.list_objects() == []


async def test__put__same_blob_twice__written_once(blobs: ObjectBlobStore, objects: FsObjectStore) -> None:
    await blobs.put(DATA)
    first = await objects.head(blob_key(SHA))
    assert first is not None

    await blobs.put(BytesIO(DATA), sha256=SHA)

    assert len(await objects.list_objects()) == 1
    assert (await objects.head(blob_key(SHA))) == first


async def test__has_many__reports_only_present(blobs: ObjectBlobStore) -> None:
    await blobs.put(DATA)
    absent = hashlib.sha256(b"absent").hexdigest()

    assert await blobs.has_many([SHA, absent, SHA]) == {SHA}
    assert await blobs.has_many([]) == set()


async def test__has_many__malformed_sha__refused(blobs: ObjectBlobStore) -> None:
    with pytest.raises(InvalidObjectKeyError):
        await blobs.has_many(["../etc/passwd"])


async def test__get_head_delete__roundtrip(blobs: ObjectBlobStore) -> None:
    await blobs.put(DATA)

    assert await blobs.get(SHA) == DATA
    assert await blobs.get(SHA, byte_range=(0, 4)) == DATA[:5]
    info = await blobs.head(SHA)
    assert info is not None
    assert info.size == len(DATA)
    await blobs.delete(SHA)
    assert await blobs.head(SHA) is None
    with pytest.raises(ObjectNotFoundError):
        await blobs.get(SHA)


async def test__verify__content_matches__returns_info(blobs: ObjectBlobStore) -> None:
    await blobs.put(DATA)

    info = await blobs.verify(SHA)

    assert (info.sha256, info.size) == (SHA, len(DATA))


async def test__verify__uploaded_under_wrong_key__mismatch_and_object_removed(
    blobs: ObjectBlobStore, objects: FsObjectStore
) -> None:
    await objects.put(blob_key(SHA), b"tampered")

    with pytest.raises(ChecksumMismatchError):
        await blobs.verify(SHA)

    assert await objects.head(blob_key(SHA)) is None


async def test__verify__nothing_uploaded__not_found(blobs: ObjectBlobStore) -> None:
    with pytest.raises(ObjectNotFoundError):
        await blobs.verify(SHA)
