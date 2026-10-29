from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.errors import ArtifactInvalidError, BlobMissingError, QueuedJobNotFoundError
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.queue import EnqueueRequest
from hse_doc_studio.infra.jobs.live_blobs import QueueLiveBlobs
from hse_doc_studio.infra.jobs.object_storage import AnnouncedJobOutputIngest, ObjectJobBlobStore
from hse_doc_studio.infra.storage.blobs import ObjectBlobStore
from hse_doc_studio.infra.storage.fs import FsObjectStore
from hse_doc_studio.infra.storage.job_output_ingest import ObjectJobOutputIngest

from tests.fakes.job_queue import InMemoryJobQueue

DATA = b"%PDF-1.7 output" * 20
SHA = hashlib.sha256(DATA).hexdigest()
PROJECT = uuid4()


async def _chunks(data: bytes, step: int = 64) -> AsyncIterator[bytes]:
    for start in range(0, len(data), step):
        yield data[start : start + step]


def _ref(path: str = "out/a.pdf", data: bytes = DATA) -> ArtifactRef:
    return ArtifactRef(path=path, sha256=hashlib.sha256(data).hexdigest(), size=len(data))


async def _enqueue(queue: InMemoryJobQueue, manifest: list[dict[str, object]] | None = None) -> UUID:
    job_id = uuid4()
    await queue.enqueue(
        EnqueueRequest(
            job_id=job_id,
            kind=JobKind.compile,
            project_id=PROJECT,
            user_id=uuid4(),
            tags=frozenset(),
            payload={"manifest": manifest or []},
        )
    )
    return job_id


@pytest.fixture
def objects(tmp_path: Path) -> FsObjectStore:
    return FsObjectStore(tmp_path / "objects", max_object_bytes=1024 * 1024)


@pytest.fixture
def queue() -> InMemoryJobQueue:
    return InMemoryJobQueue()


@pytest.fixture
def ingest(queue: InMemoryJobQueue, objects: FsObjectStore) -> AnnouncedJobOutputIngest:
    return AnnouncedJobOutputIngest(queue, objects, ObjectJobOutputIngest(objects))


async def test__blob_store__uploaded_blob__is_visible_and_streams(objects: FsObjectStore) -> None:
    blobs = ObjectBlobStore(objects)
    info = await blobs.put(DATA)
    store = ObjectJobBlobStore(blobs)

    assert await store.exists(info.sha256)
    assert b"".join([chunk async for chunk in await store.open(info.sha256)]) == DATA
    assert await store.url_for(info.sha256) is None


async def test__blob_store__missing_or_malformed_hash__is_missing(objects: FsObjectStore) -> None:
    store = ObjectJobBlobStore(ObjectBlobStore(objects))

    assert not await store.exists("0" * 64)
    assert not await store.exists("../x")
    with pytest.raises(BlobMissingError):
        await store.open("0" * 64)


async def test__outputs__announce_put_commit__stored_under_job_prefix(
    ingest: AnnouncedJobOutputIngest, queue: InMemoryJobQueue, objects: FsObjectStore
) -> None:
    job_id = await _enqueue(queue)
    ref = _ref()

    assert await ingest.announce(job_id, 1, ref) is None
    await ingest.put(job_id, 1, ref.sha256, _chunks(DATA))
    await ingest.commit(job_id, 1, [ref])

    assert await objects.get(f"artifacts/{PROJECT}/jobs/{job_id}/out/a.pdf") == DATA


async def test__outputs__put_without_announce__rejected(
    ingest: AnnouncedJobOutputIngest, queue: InMemoryJobQueue
) -> None:
    job_id = await _enqueue(queue)

    with pytest.raises(ArtifactInvalidError):
        await ingest.put(job_id, 1, SHA, _chunks(DATA))


async def test__outputs__stream_larger_than_announced__rejected(
    ingest: AnnouncedJobOutputIngest, queue: InMemoryJobQueue
) -> None:
    job_id = await _enqueue(queue)
    await ingest.announce(job_id, 1, _ref())

    with pytest.raises(ArtifactInvalidError):
        await ingest.put(job_id, 1, SHA, _chunks(DATA + b"x"))


async def test__outputs__wrong_content__rejected_and_not_stored(
    ingest: AnnouncedJobOutputIngest, queue: InMemoryJobQueue, objects: FsObjectStore
) -> None:
    job_id = await _enqueue(queue)
    await ingest.announce(job_id, 1, _ref())

    with pytest.raises(ArtifactInvalidError):
        await ingest.put(job_id, 1, SHA, _chunks(b"y" * len(DATA)))

    assert await objects.list_objects(f"artifacts/{PROJECT}/") == []


async def test__outputs__commit_without_upload__rejected(
    ingest: AnnouncedJobOutputIngest, queue: InMemoryJobQueue
) -> None:
    job_id = await _enqueue(queue)
    await ingest.announce(job_id, 1, _ref())

    with pytest.raises(ArtifactInvalidError):
        await ingest.commit(job_id, 1, [_ref()])


async def test__outputs__same_content_two_paths__both_stored(
    ingest: AnnouncedJobOutputIngest, queue: InMemoryJobQueue, objects: FsObjectStore
) -> None:
    job_id = await _enqueue(queue)
    first, second = _ref("a.pdf"), _ref("b/copy.pdf")
    await ingest.announce(job_id, 1, first)
    await ingest.announce(job_id, 1, second)

    await ingest.put(job_id, 1, SHA, _chunks(DATA))
    await ingest.commit(job_id, 1, [first, second])

    prefix = f"artifacts/{PROJECT}/jobs/{job_id}/"
    assert await objects.get(prefix + "a.pdf") == await objects.get(prefix + "b/copy.pdf") == DATA


async def test__outputs__duplicate_uploaded_once__commit_copies_missing(
    ingest: AnnouncedJobOutputIngest, queue: InMemoryJobQueue, objects: FsObjectStore
) -> None:
    job_id = await _enqueue(queue)
    first, second = _ref("a.pdf"), _ref("b.pdf")
    await ingest.announce(job_id, 1, first)
    await objects.put(f"artifacts/{PROJECT}/jobs/{job_id}/a.pdf", DATA)

    await ingest.announce(job_id, 1, second)
    await ingest.commit(job_id, 1, [first, second])

    assert await objects.get(f"artifacts/{PROJECT}/jobs/{job_id}/b.pdf") == DATA


async def test__outputs__discard__removes_outputs_and_markers(
    ingest: AnnouncedJobOutputIngest, queue: InMemoryJobQueue, objects: FsObjectStore
) -> None:
    job_id = await _enqueue(queue)
    other = await _enqueue(queue)
    for job in (job_id, other):
        await ingest.announce(job, 1, _ref())
        await ingest.put(job, 1, SHA, _chunks(DATA))

    await ingest.discard(job_id)

    keys = [info.key for info in await objects.list_objects("")]
    assert keys
    assert all(str(job_id) not in key for key in keys)
    assert any(str(other) in key for key in keys)


async def test__outputs__unknown_job__not_found(ingest: AnnouncedJobOutputIngest) -> None:
    with pytest.raises(QueuedJobNotFoundError):
        await ingest.announce(uuid4(), 1, _ref())


async def test__live_blobs__only_unfinished_jobs_keep_their_manifest(queue: InMemoryJobQueue) -> None:
    await _enqueue(queue, [{"path": "a", "sha256": "a" * 64, "size": 1}])
    done = await _enqueue(queue, [{"path": "b", "sha256": "b" * 64, "size": 1}])
    job = await queue.get(done)
    assert job is not None
    assert job.state is JobState.queued
    await queue.request_cancel(done)

    live = await QueueLiveBlobs(queue).live_blobs()

    assert "a" * 64 in live
    assert "b" * 64 not in live
