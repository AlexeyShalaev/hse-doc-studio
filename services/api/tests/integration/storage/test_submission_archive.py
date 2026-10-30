"""ObjectSubmissionArchive и аудит скачиваний на настоящем S3 (moto или MinIO)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.storage.keys import validate_key
from hse_doc_studio.infra.storage.s3 import S3ObjectStore
from hse_doc_studio.infra.submission.archive import AUDIT_DOWNLOADED, AuditSubmissionDownloads, ObjectSubmissionArchive

pytestmark = pytest.mark.s3


class _Audit:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def record(self, action: str, **kwargs: Any) -> None:
        self.calls.append((action, kwargs))


@pytest.fixture
def archive(s3_client: Any, s3_bucket: str) -> ObjectSubmissionArchive:
    return ObjectSubmissionArchive(
        S3ObjectStore(s3_client, s3_bucket, max_object_bytes=10 * 1024**2, multipart_threshold_bytes=5 * 1024**2)
    )


async def test__put__then_size_and_stream(archive: ObjectSubmissionArchive, tmp_path: Path) -> None:
    source = tmp_path / "final.zip"
    source.write_bytes(b"PK" * 1000)
    project_id, submission_id = uuid4(), uuid4()

    key = await archive.put(project_id, submission_id, source, "application/zip")

    assert key == validate_key(f"artifacts/{project_id}/submissions/{submission_id}/final.zip")
    assert await archive.size(key) == 2000
    assert b"".join([chunk async for chunk in archive.stream(key)]) == b"PK" * 1000


async def test__size__missing_object__none(archive: ObjectSubmissionArchive) -> None:
    assert await archive.size("artifacts/a/submissions/b/none.zip") is None


async def test__stream__missing_object__file_not_found(archive: ObjectSubmissionArchive) -> None:
    with pytest.raises(FileNotFoundError):
        [chunk async for chunk in archive.stream("artifacts/a/submissions/b/none.zip")]


async def test__link__missing_object__file_not_found(archive: ObjectSubmissionArchive) -> None:
    with pytest.raises(FileNotFoundError):
        await archive.link("artifacts/a/submissions/b/none.zip")


async def test__link__existing_object__presigned_url(archive: ObjectSubmissionArchive, tmp_path: Path) -> None:
    source = tmp_path / "final.zip"
    source.write_bytes(b"x")
    key = await archive.put(uuid4(), uuid4(), source, "application/zip")

    link = await archive.link(key)

    assert link is not None
    assert "final.zip" in link.url


async def test__audit__download_is_recorded_with_actor_project_and_way() -> None:
    audit = _Audit()
    project_id, submission_id = uuid4(), uuid4()

    await AuditSubmissionDownloads(audit).downloaded(  # type: ignore[arg-type]
        Actor.user("anna"), project_id, submission_id, via="link"
    )

    assert audit.calls == [
        (
            AUDIT_DOWNLOADED,
            {
                "actor_id": "anna",
                "target": str(submission_id),
                "details": {"project_id": str(project_id), "via": "link"},
            },
        )
    ]
