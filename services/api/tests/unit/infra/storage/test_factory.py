from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.api.config.storage import StorageConfig
from hse_doc_studio.infra.storage.factory import create_object_store
from hse_doc_studio.infra.storage.fs import FsObjectStore
from pydantic import ValidationError


async def test__create_object_store__no_bucket__fs_under_data_dir(tmp_path: Path) -> None:
    store = create_object_store(StorageConfig(), tmp_path)

    assert isinstance(store, FsObjectStore)
    await store.put("a/b", b"x")
    assert (tmp_path / "objects" / "a" / "b").read_bytes() == b"x"


def test__create_object_store__explicit_fs_root__used(tmp_path: Path) -> None:
    store = create_object_store(StorageConfig(fs_root=tmp_path / "custom"), tmp_path / "data")

    assert isinstance(store, FsObjectStore)


def test__storage_config__public_endpoint__normalized_to_origin() -> None:
    assert StorageConfig(public_endpoint="https://files.example.org/").public_endpoint == "https://files.example.org"
    assert (
        StorageConfig(public_endpoint="http://files.example.org:9000").public_endpoint
        == "http://files.example.org:9000"
    )
    assert StorageConfig(public_endpoint="  ").public_endpoint is None
    assert StorageConfig(public_endpoint="").public_endpoint is None


@pytest.mark.parametrize(
    "value",
    [
        "files.example.org",
        "ftp://files.example.org",
        "https://user:pw@files.example.org",
        "https://f.org/s3",
        "https://f.org/?a=1",
    ],
)
def test__storage_config__public_endpoint_not_an_origin__rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        StorageConfig(public_endpoint=value)


def test__storage_config__outside_access__defaults_and_unknown_value() -> None:
    cfg = StorageConfig()
    assert (cfg.outside_runner_access, cfg.shared_runners_outside) == ("presigned", False)
    with pytest.raises(ValidationError):
        StorageConfig(outside_runner_access="direct")  # type: ignore[arg-type]


def test__create_object_store__public_endpoint__separate_presign_client(tmp_path: Path) -> None:
    pytest.importorskip("boto3")
    from hse_doc_studio.infra.storage.s3 import S3ObjectStore  # noqa: PLC0415

    both = create_object_store(
        StorageConfig(bucket="b", endpoint="http://minio.internal:9000", public_endpoint="https://files.example.org"),
        tmp_path,
    )
    only_internal = create_object_store(StorageConfig(bucket="b", endpoint="http://minio.internal:9000"), tmp_path)

    assert isinstance(both, S3ObjectStore)
    assert isinstance(only_internal, S3ObjectStore)
    assert both.has_public_endpoint
    assert not only_internal.has_public_endpoint
