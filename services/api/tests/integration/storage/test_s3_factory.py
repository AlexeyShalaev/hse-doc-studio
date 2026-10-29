from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.api.config.storage import StorageConfig
from hse_doc_studio.infra.storage.factory import create_object_store
from hse_doc_studio.infra.storage.s3 import S3ObjectStore
from pydantic import SecretStr

pytestmark = pytest.mark.s3


async def test__create_object_store__bucket_set__s3_store_against_moto(s3_target, tmp_path: Path) -> None:
    if s3_target.endpoint_url is not None:
        pytest.skip("фабрика проверяется на moto: ключи MinIO CI не передаются в конфиг")
    cfg = StorageConfig(bucket=s3_target.bucket, access_key=SecretStr("testing"), secret_key=SecretStr("testing"))

    store = create_object_store(cfg, tmp_path)

    assert isinstance(store, S3ObjectStore)
    await store.check()
    await store.put("a/b", b"x")
    assert await store.get("a/b") == b"x"
