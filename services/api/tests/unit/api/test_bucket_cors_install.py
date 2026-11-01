"""CORS бакета на старте: S3 без PutBucketCors (MinIO) даёт предупреждение, а не падение api."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from hse_doc_studio.api.observability.install import install_bucket_cors
from hse_doc_studio.core.storage import ObjectStoreError
from hse_doc_studio.infra.storage.s3 import S3ObjectStore

pytestmark = pytest.mark.unit


class _Container:
    def __init__(self, store: object) -> None:
        self._store = store

    async def get(self, _key: object) -> object:
        return self._store


async def _run_startup(app: FastAPI) -> None:
    for handler in app.router.on_startup:
        await handler()


async def test__install_bucket_cors__not_implemented__startup_survives(monkeypatch: pytest.MonkeyPatch) -> None:
    store = object.__new__(S3ObjectStore)

    async def _not_implemented(_self: S3ObjectStore, _origins: Any) -> None:
        raise ObjectStoreError("S3 отказал: NotImplemented")

    monkeypatch.setattr(S3ObjectStore, "apply_cors", _not_implemented)
    app = FastAPI()
    cfg = SimpleNamespace(s3=SimpleNamespace(cors_origins=["https://studio.example.org"]))
    install_bucket_cors(app, _Container(store), cfg)  # type: ignore[arg-type]

    await _run_startup(app)


async def test__install_bucket_cors__no_origins__nothing_registered() -> None:
    app = FastAPI()
    install_bucket_cors(app, _Container(object()), SimpleNamespace(s3=SimpleNamespace(cors_origins=[])))  # type: ignore[arg-type]

    assert not app.router.on_startup
