"""Контрактный набор IObjectStore на S3 (moto внутри процесса или MinIO из CI)."""

from __future__ import annotations

from typing import Any

import pytest
from hse_doc_studio.infra.storage.s3 import S3ObjectStore

from tests.contract.object_store_suite import ObjectStoreContract

pytestmark = pytest.mark.s3


class TestS3ObjectStoreContract(ObjectStoreContract):
    @pytest.fixture
    def port(self, s3_client: Any, s3_bucket: str) -> S3ObjectStore:
        return S3ObjectStore(s3_client, s3_bucket, max_object_bytes=1024 * 1024, multipart_threshold_bytes=5 * 1024**2)

    @pytest.fixture
    def small_port(self, s3_client: Any, s3_bucket: str) -> S3ObjectStore:
        return S3ObjectStore(s3_client, s3_bucket, max_object_bytes=10, multipart_threshold_bytes=5 * 1024**2)
