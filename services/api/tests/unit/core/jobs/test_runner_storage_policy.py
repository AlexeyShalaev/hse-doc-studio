from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass, JobState
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.queue import QueuedJob
from hse_doc_studio.core.jobs.routing import RunnerScope
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.core.jobs.storage import RunnerStoragePolicy
from hse_doc_studio.core.jobs.wire import ArtifactUploadRequest, BlobNeedRequest
from hse_doc_studio.core.storage.models import LinkAudience
from hse_doc_studio.use_cases.jobs.runner_io import RunnerJobIoService

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
DATA = b"manifest blob"
SHA = hashlib.sha256(DATA).hexdigest()


@pytest.mark.parametrize(
    ("policy", "scope", "expected"),
    [
        (RunnerStoragePolicy(), RunnerScope.shared, LinkAudience.internal),
        (RunnerStoragePolicy(), RunnerScope.personal, LinkAudience.outside),
        (RunnerStoragePolicy(outside_via_api=True), RunnerScope.personal, None),
        (RunnerStoragePolicy(outside_via_api=True), RunnerScope.shared, LinkAudience.internal),
        (RunnerStoragePolicy(shared_outside=True), RunnerScope.shared, LinkAudience.outside),
        (RunnerStoragePolicy(shared_outside=True, outside_via_api=True), RunnerScope.shared, None),
    ],
)
def test__audience_for__scope_and_mode__picks_recipient(
    policy: RunnerStoragePolicy, scope: RunnerScope, expected: LinkAudience | None
) -> None:
    assert policy.audience_for(scope) is expected


class _Blobs:
    def __init__(self) -> None:
        self.asked: list[LinkAudience] = []

    async def exists(self, sha256: str) -> bool:
        return True

    async def url_for(self, sha256: str, audience: LinkAudience = LinkAudience.outside) -> str | None:
        self.asked.append(audience)
        return f"https://{audience.value}.test/{sha256}"

    async def open(self, sha256: str) -> AsyncIterator[bytes]:
        raise NotImplementedError


class _Outputs:
    def __init__(self) -> None:
        self.asked: list[LinkAudience | None] = []

    async def announce(
        self, job_id: UUID, attempt: int, artifact: ArtifactRef, audience: LinkAudience | None = LinkAudience.outside
    ) -> str | None:
        self.asked.append(audience)
        return None if audience is None else f"https://{audience.value}.test/up"


def _job() -> QueuedJob:
    return QueuedJob(
        id=uuid4(),
        kind=JobKind.compile,
        project_id=uuid4(),
        user_id=uuid4(),
        org_id=None,
        tags=frozenset(),
        priority_class=JobPriorityClass.interactive,
        vtime=0.0,
        queued_at=NOW,
        state=JobState.running,
        attempt=1,
        max_attempts=3,
        timeout_s=60.0,
        payload={"manifest": [{"sha256": SHA}]},
    )


def _runner(*, personal: bool) -> Runner:
    runner = Runner(
        id=str(uuid4()),
        name="r",
        token_hash="h",
        tags=frozenset(),
        concurrency=1,
        resource_class="standard",
        version="1",
        created_at=NOW,
    )
    return replace(runner, owner_kind=RunnerOwnerKind.user, owner_id="u") if personal else runner


def _service(blobs: _Blobs, outputs: _Outputs, policy: RunnerStoragePolicy | None) -> RunnerJobIoService:
    service = RunnerJobIoService(
        MagicMock(), MagicMock(), MagicMock(), MagicMock(), blobs, outputs, MagicMock(), storage_policy=policy
    )
    job = _job()

    async def authorize(*args: object, **kwargs: object) -> QueuedJob:
        return job

    service.authorize = authorize  # type: ignore[method-assign]
    return service


_ARTIFACT = ArtifactRef(path="out/a.pdf", sha256=SHA, size=len(DATA))


@pytest.mark.parametrize(
    ("personal", "policy", "audience", "url_host"),
    [
        (False, None, LinkAudience.internal, "internal"),
        (True, None, LinkAudience.outside, "outside"),
        (True, RunnerStoragePolicy(outside_via_api=True), None, None),
        (False, RunnerStoragePolicy(shared_outside=True), LinkAudience.outside, "outside"),
    ],
    ids=["shared-in-network", "personal-outside", "personal-proxy", "shared-declared-outside"],
)
async def test__links__issued_for_recipient_address(
    personal: bool, policy: RunnerStoragePolicy | None, audience: LinkAudience | None, url_host: str | None
) -> None:
    blobs, outputs = _Blobs(), _Outputs()
    service = _service(blobs, outputs, policy)
    runner = _runner(personal=personal)

    need = await service.need_blobs(runner, uuid4(), "t", BlobNeedRequest(attempt=1, sha256=(SHA,)))
    slot = await service.announce_artifact(runner, uuid4(), "t", ArtifactUploadRequest(attempt=1, artifact=_ARTIFACT))

    expected_blob = None if url_host is None else f"https://{url_host}.test/{SHA}"
    expected_slot = None if url_host is None else f"https://{url_host}.test/up"
    assert [b.url for b in need.blobs] == [expected_blob]
    assert slot.url == expected_slot
    assert outputs.asked == [audience]
    assert blobs.asked == ([] if audience is None else [audience])
