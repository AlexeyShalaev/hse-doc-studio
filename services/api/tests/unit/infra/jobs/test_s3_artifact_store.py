"""S3ArtifactStore поверх каталожного хранилища: копия до переноса, архив последних N, сбой хранилища."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.artifacts import PublishPdfRequest
from hse_doc_studio.core.storage import ObjectStoreError
from hse_doc_studio.infra.jobs.artifact_store import LocalDiskArtifactStore
from hse_doc_studio.infra.jobs.s3_artifact_store import S3ArtifactStore, archived_pdf_key
from hse_doc_studio.infra.storage.fs import FsObjectStore

_SOURCE = "vkr/vkr.tex"
_KEEP = 3
PROJECT_ID = UUID("33333333-3333-4333-8333-333333333333")


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@pytest.fixture
def objects(tmp_path: Path) -> FsObjectStore:
    return FsObjectStore(tmp_path / "objects", max_object_bytes=10 * 1024**2)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    path = tmp_path / "volume"
    path.mkdir()
    return path


def _store(objects: FsObjectStore) -> S3ArtifactStore:
    return S3ArtifactStore(objects, LocalDiskArtifactStore(retry_delay_s=0), keep=_KEEP)


async def _publish_and_archive(store: S3ArtifactStore, workspace: Path, data: bytes) -> UUID:
    job_id = uuid4()
    _write(workspace / "vkr/.build/vkr/vkr.pdf", data)
    outcome = await store.publish_pdf(
        PublishPdfRequest(workspace=workspace, doc_id="vkr", job_id=job_id, source_file=_SOURCE, project_id=PROJECT_ID)
    )
    assert outcome.replaced is True
    await store.archive_pdf(PROJECT_ID, workspace, "vkr", job_id, _SOURCE)
    return job_id


async def test__publish_pdf__moves_to_volume_and_keeps_copy_in_store(objects: FsObjectStore, workspace: Path) -> None:
    store = _store(objects)

    job_id = await _publish_and_archive(store, workspace, b"%PDF fresh")

    assert (workspace / "vkr/vkr.pdf").read_bytes() == b"%PDF fresh"
    assert await store.read_archived_pdf(PROJECT_ID, workspace, "vkr", job_id) == b"%PDF fresh"
    assert not (workspace / ".hse-studio").exists()


async def test__archive_pdf__keeps_last_n_and_current(objects: FsObjectStore, workspace: Path) -> None:
    store = _store(objects)
    ids = []
    for i in range(_KEEP + 3):
        ids.append(await _publish_and_archive(store, workspace, f"build {i}".encode()))

    kept = {o.key for o in await objects.list_objects(f"artifacts/{PROJECT_ID}/pdf/vkr/")}
    assert kept == {archived_pdf_key(PROJECT_ID, "vkr", job_id) for job_id in ids[-_KEEP:]}
    with pytest.raises(FileNotFoundError):
        await store.read_archived_pdf(PROJECT_ID, workspace, "vkr", ids[0])


async def test__archive_pdf__other_project_does_not_see_archive(objects: FsObjectStore, workspace: Path) -> None:
    store = _store(objects)
    job_id = await _publish_and_archive(store, workspace, b"mine")

    with pytest.raises(FileNotFoundError):
        await store.read_archived_pdf(uuid4(), workspace, "vkr", job_id)


async def test__archive_pdf__upload_failed_on_publish__archive_retries_from_volume(
    objects: FsObjectStore, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(objects)
    real_put = objects.put
    calls = 0

    async def flaky(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ObjectStoreError("S3 недоступен")
        return await real_put(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(objects, "put", flaky)

    job_id = await _publish_and_archive(store, workspace, b"%PDF healed")

    assert (workspace / "vkr/vkr.pdf").read_bytes() == b"%PDF healed"
    assert await store.read_archived_pdf(PROJECT_ID, workspace, "vkr", job_id) == b"%PDF healed"


async def test__archive_pdf__store_down__does_not_raise(
    objects: FsObjectStore, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(objects)

    async def down(*_args: object, **_kwargs: object) -> None:
        raise ObjectStoreError("S3 недоступен")

    monkeypatch.setattr(objects, "put", down)
    monkeypatch.setattr(objects, "head", down)

    await _publish_and_archive(store, workspace, b"%PDF")

    assert (workspace / "vkr/vkr.pdf").read_bytes() == b"%PDF"


async def test__publish_pdf__without_project_id__only_volume(objects: FsObjectStore, workspace: Path) -> None:
    store = _store(objects)
    _write(workspace / "vkr/.build/vkr/vkr.pdf", b"x")

    outcome = await store.publish_pdf(
        PublishPdfRequest(workspace=workspace, doc_id="vkr", job_id=uuid4(), source_file=_SOURCE)
    )

    assert outcome.replaced is True
    assert await objects.list_objects("artifacts/") == []


async def test__archived_pdf_link__disk_store__none(objects: FsObjectStore, workspace: Path) -> None:
    store = _store(objects)
    job_id = await _publish_and_archive(store, workspace, b"x")

    assert await store.archived_pdf_link(PROJECT_ID, "vkr", job_id) is None


async def test__read_archived_pdf__unsafe_doc_id__file_not_found(objects: FsObjectStore, workspace: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await _store(objects).read_archived_pdf(PROJECT_ID, workspace, "../x", uuid4())
