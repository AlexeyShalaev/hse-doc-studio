from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.storage import ChecksumMismatchError, ObjectStoreError
from hse_doc_studio.infra.storage.fs import FsObjectStore


@pytest.fixture
def store(tmp_path: Path) -> FsObjectStore:
    return FsObjectStore(tmp_path / "objects", max_object_bytes=1024)


async def test__put__leaves_no_temporary_files(store: FsObjectStore, tmp_path: Path) -> None:
    await store.put("a/b", b"data")
    with pytest.raises(ChecksumMismatchError):
        await store.put("a/c", b"data", sha256="0" * 64)

    leftovers = list((tmp_path / "objects" / ".tmp").iterdir())
    assert leftovers == []
    assert [i.key for i in await store.list_objects()] == ["a/b"]


async def test__put__file_changed_after_check__mismatch_detected_on_copy(store: FsObjectStore, tmp_path: Path) -> None:
    class Shifting:
        """Источник, который при втором чтении отдаёт другие байты."""

        def __init__(self) -> None:
            self.reads = 0
            self.pos = 0

        def tell(self) -> int:
            return 0

        def seek(self, _pos: int) -> int:
            self.pos = 0
            return 0

        def read(self, _n: int = -1) -> bytes:
            if self.pos:
                return b""
            self.pos = 1
            self.reads += 1
            return b"aaaa" if self.reads == 1 else b"bbbb"

    import hashlib  # noqa: PLC0415

    with pytest.raises(ChecksumMismatchError):
        await store.put("k/x", Shifting(), sha256=hashlib.sha256(b"aaaa").hexdigest())  # type: ignore[arg-type]

    assert await store.head("k/x") is None


async def test__put__key_under_existing_file__store_error(store: FsObjectStore) -> None:
    await store.put("k/x", b"1")

    with pytest.raises(ObjectStoreError):
        await store.put("k/x/y", b"2")


async def test__delete__removes_empty_parent_folders(store: FsObjectStore, tmp_path: Path) -> None:
    await store.put("a/b/c", b"1")

    await store.delete("a/b/c")

    assert not (tmp_path / "objects" / "a").exists()


async def test__presign__fs_gives_no_links(store: FsObjectStore) -> None:
    assert await store.presign_get("a/b") is None
    assert await store.presign_put("a/b") is None


async def test__check__unwritable_root__store_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    store = FsObjectStore(blocker / "objects", max_object_bytes=10)

    with pytest.raises(ObjectStoreError):
        await store.check()
