"""S3ArtifactStore в настоящем S3 (moto или MinIO): ссылка на архивный PDF и CORS бакета."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.artifacts import PublishPdfRequest
from hse_doc_studio.infra.jobs.artifact_store import LocalDiskArtifactStore
from hse_doc_studio.infra.jobs.s3_artifact_store import S3ArtifactStore, archived_pdf_key
from hse_doc_studio.infra.storage.s3 import S3ObjectStore

pytestmark = pytest.mark.s3

PROJECT_ID = UUID("44444444-4444-4444-8444-444444444444")
PDF = b"%PDF-1.7\n" + bytes(range(256)) * 16


@pytest.fixture
def objects(s3_client: Any, s3_bucket: str) -> S3ObjectStore:
    return S3ObjectStore(s3_client, s3_bucket, max_object_bytes=10 * 1024**2, multipart_threshold_bytes=5 * 1024**2)


async def test__archived_pdf_link__after_publish__short_link_to_bucket_object(
    objects: S3ObjectStore, tmp_path: Path, s3_bucket: str
) -> None:
    store = S3ArtifactStore(objects, LocalDiskArtifactStore(retry_delay_s=0), link_ttl_s=90)
    job_id = uuid4()
    built = tmp_path / "vkr/.build/vkr/vkr.pdf"
    built.parent.mkdir(parents=True)
    built.write_bytes(PDF)
    await store.publish_pdf(
        PublishPdfRequest(
            workspace=tmp_path, doc_id="vkr", job_id=job_id, source_file="vkr/vkr.tex", project_id=PROJECT_ID
        )
    )
    await store.archive_pdf(PROJECT_ID, tmp_path, "vkr", job_id, "vkr/vkr.tex")

    link = await store.archived_pdf_link(PROJECT_ID, "vkr", job_id)

    assert link is not None
    assert archived_pdf_key(PROJECT_ID, "vkr", job_id) in urlparse(link.url).path
    assert 60 < (link.expires_at - datetime.now(UTC)).total_seconds() <= 90
    assert await store.read_archived_pdf(PROJECT_ID, tmp_path, "vkr", job_id) == PDF


async def test__archived_pdf_link__no_archive__file_not_found(objects: S3ObjectStore) -> None:
    store = S3ArtifactStore(objects, LocalDiskArtifactStore())

    with pytest.raises(FileNotFoundError):
        await store.archived_pdf_link(PROJECT_ID, "vkr", uuid4())


async def test__apply_cors__bucket_allows_range_reads_from_origin(
    objects: S3ObjectStore, s3_client: Any, s3_bucket: str
) -> None:
    await objects.apply_cors(["https://studio.example.org"])

    rule = s3_client.get_bucket_cors(Bucket=s3_bucket)["CORSRules"][0]
    assert rule["AllowedOrigins"] == ["https://studio.example.org"]
    assert set(rule["AllowedMethods"]) == {"GET", "HEAD"}
    assert "Range" in rule["AllowedHeaders"]
    assert "Content-Range" in rule["ExposeHeaders"]
