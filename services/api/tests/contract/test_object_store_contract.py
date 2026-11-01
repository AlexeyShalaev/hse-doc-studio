"""Контрактный набор IObjectStore на диске."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.storage.fs import FsObjectStore

from tests.contract.object_store_suite import ObjectStoreContract


class TestFsObjectStoreContract(ObjectStoreContract):
    @pytest.fixture
    def port(self, tmp_path: Path) -> FsObjectStore:
        return FsObjectStore(tmp_path / "objects", max_object_bytes=1024 * 1024)

    @pytest.fixture
    def small_port(self, tmp_path: Path) -> FsObjectStore:
        return FsObjectStore(tmp_path / "small", max_object_bytes=10)
