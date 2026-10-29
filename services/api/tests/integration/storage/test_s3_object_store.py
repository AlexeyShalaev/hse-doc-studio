"""S3: ссылки с Range, срок ссылки, публичный адрес, блобы и проверка бакета (moto или MinIO)."""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from typing import Any

import pytest
from hse_doc_studio.core.storage import ChecksumMismatchError, ObjectStoreError, blob_key
from hse_doc_studio.infra.storage.blobs import ObjectBlobStore
from hse_doc_studio.infra.storage.s3 import S3ObjectStore

pytestmark = pytest.mark.s3

PDF = b"%PDF-1.7\n" + bytes(range(256)) * 64


@pytest.fixture
def store(s3_client: Any, s3_bucket: str) -> S3ObjectStore:
    return S3ObjectStore(s3_client, s3_bucket, max_object_bytes=10 * 1024**2, multipart_threshold_bytes=5 * 1024**2)


async def test__presign_get__range_request__returns_partial_pdf(store: S3ObjectStore) -> None:
    requests = pytest.importorskip("requests")
    await store.put("artifacts/p/a.pdf", PDF, content_type="application/pdf")

    link = await store.presign_get("artifacts/p/a.pdf", expires_in_s=60)
    assert link is not None
    response = requests.get(link.url, headers={"Range": "bytes=0-7"}, timeout=10)

    assert response.status_code == 206
    assert response.content == PDF[:8]


async def test__presign_get__link_carries_short_expiry(store: S3ObjectStore) -> None:
    await store.put("artifacts/p/a.pdf", PDF)

    link = await store.presign_get("artifacts/p/a.pdf", expires_in_s=45)

    assert link is not None
    assert "Expires=" in link.url
    assert 40 <= (link.expires_at - datetime.now(UTC)).total_seconds() <= 46


async def test__presign_get__expired_link__rejected_by_real_s3(s3_target: Any) -> None:
    if s3_target.endpoint_url is None:
        pytest.skip("moto не проверяет срок подписи; срок проверяется на MinIO из CI")
    requests = pytest.importorskip("requests")
    store = S3ObjectStore(
        s3_target.client, s3_target.bucket, max_object_bytes=10**6, multipart_threshold_bytes=5 * 1024**2
    )
    await store.put("artifacts/p/a.pdf", PDF)

    link = await store.presign_get("artifacts/p/a.pdf", expires_in_s=1)
    assert link is not None
    time.sleep(2.2)

    assert requests.get(link.url, timeout=10).status_code == 403


async def test__presign_put__upload_then_verify_blob(store: S3ObjectStore) -> None:
    requests = pytest.importorskip("requests")
    blobs = ObjectBlobStore(store)
    sha = hashlib.sha256(PDF).hexdigest()

    link = await blobs.presign_put(sha, expires_in_s=60)
    assert link is not None
    assert requests.put(link.url, data=PDF, headers=link.headers, timeout=10).status_code == 200
    info = await blobs.verify(sha)

    assert (info.sha256, info.size) == (sha, len(PDF))


async def test__verify__wrong_content_uploaded__removed(store: S3ObjectStore) -> None:
    requests = pytest.importorskip("requests")
    blobs = ObjectBlobStore(store)
    sha = hashlib.sha256(PDF).hexdigest()

    link = await blobs.presign_put(sha, expires_in_s=60)
    assert link is not None
    requests.put(link.url, data=b"not the pdf", headers=link.headers, timeout=10)
    with pytest.raises(ChecksumMismatchError):
        await blobs.verify(sha)

    assert await store.head(blob_key(sha)) is None


async def test__blob_put__wrong_sha__nothing_written(store: S3ObjectStore) -> None:
    blobs = ObjectBlobStore(store)

    with pytest.raises(ChecksumMismatchError):
        await blobs.put(PDF, sha256="0" * 64)

    assert await store.list_objects() == []


async def test__head__reports_stored_sha256(store: S3ObjectStore) -> None:
    await store.put("k/x", PDF)

    info = await store.head("k/x")

    assert info is not None
    assert info.sha256 == hashlib.sha256(PDF).hexdigest()


async def test__put__above_multipart_threshold__roundtrip(s3_client: Any, s3_bucket: str) -> None:
    store = S3ObjectStore(s3_client, s3_bucket, max_object_bytes=64 * 1024**2, multipart_threshold_bytes=5 * 1024**2)
    big = b"z" * (6 * 1024**2)

    info = await store.put("k/big", big)

    assert info.size == len(big)
    assert await store.get("k/big", byte_range=(len(big) - 3, None)) == b"zzz"


async def test__check__missing_bucket__store_error(s3_client: Any) -> None:
    store = S3ObjectStore(s3_client, "no-such-bucket-xyz", max_object_bytes=10, multipart_threshold_bytes=5 * 1024**2)

    with pytest.raises(ObjectStoreError):
        await store.check()


async def test__presign_get__public_endpoint_client__signs_for_public_host(s3_client: Any, s3_bucket: str) -> None:
    import boto3  # noqa: PLC0415
    from hse_doc_studio.infra.storage.s3 import build_client_config  # noqa: PLC0415

    public = boto3.client(
        "s3",
        endpoint_url="https://files.example.test",
        region_name="us-east-1",
        aws_access_key_id="k",
        aws_secret_access_key="s",
        config=build_client_config(path_style=True),
    )
    store = S3ObjectStore(
        s3_client,
        s3_bucket,
        max_object_bytes=10,
        multipart_threshold_bytes=5 * 1024**2,
        presign_client=public,
    )

    link = await store.presign_get("a/b")

    assert link is not None
    assert link.url.startswith(f"https://files.example.test/{s3_bucket}/a/b?")
    assert "X-Amz-Signature=" in link.url
