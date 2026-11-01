from __future__ import annotations

from pathlib import Path

from hse_doc_studio.api.config.storage import StorageConfig
from hse_doc_studio.infra.storage.factory import create_object_store
from hse_doc_studio.infra.storage.fs import FsObjectStore


async def test__create_object_store__no_bucket__fs_under_data_dir(tmp_path: Path) -> None:
    store = create_object_store(StorageConfig(), tmp_path)

    assert isinstance(store, FsObjectStore)
    await store.put("a/b", b"x")
    assert (tmp_path / "objects" / "a" / "b").read_bytes() == b"x"


def test__create_object_store__explicit_fs_root__used(tmp_path: Path) -> None:
    store = create_object_store(StorageConfig(fs_root=tmp_path / "custom"), tmp_path / "data")

    assert isinstance(store, FsObjectStore)
