"""Лог, блобы, выходы и завершение задачи раннером поверх настоящих маршрутов и файлового хранилища."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.server_routers import include_server_routers
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.jobs.codec import encode_envelope
from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.jobs.queue import EnqueueRequest
from hse_doc_studio.core.jobs.runners import JobTokenSigner
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION, JobEnvelope
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.jobs.storage_fs import FsJobBlobStore, FsJobLogSink, FsJobOutputIngest
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runner_io import RunnerJobIoService
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository
from tests.unit.core.jobs.samples import make_compile_spec

_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)
_INPUT = b"\\documentclass{article}"
_PDF = b"%PDF-1.7 " + b"x" * 5000


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class _Leased:
    headers: dict[str, str]
    job_id: UUID
    attempt: int
    job_token: str

    @property
    def auth(self) -> dict[str, str]:
        return {**self.headers, "X-Job-Token": self.job_token}


@dataclass
class _Env:
    client: AsyncClient
    queue: InMemoryJobQueue
    clock: _Clock
    registry: RunnerRegistry
    blobs: FsJobBlobStore
    root: Path

    async def register(self) -> dict[str, str]:
        created = await self.registry.create_registration_token(_ADMIN)
        response = await self.client.post(
            "/api/runner/v1/register",
            json={
                "name": "r",
                "protocol": RUNNER_PROTOCOL_VERSION,
                "version": "1",
                "tags": ["compile"],
                "concurrency": 1,
                "resource_class": "standard",
            },
            headers={"Authorization": f"Bearer {created.secret}"},
        )
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['runner_token']}"}

    async def lease(self, headers: dict[str, str] | None = None) -> _Leased:
        headers = headers or await self.register()
        sha = await self.blobs.store(_INPUT)
        envelope = JobEnvelope(
            spec=make_compile_spec(),
            manifest=(ManifestFile("main.tex", sha, len(_INPUT)),),
            timeout_s=600.0,
            attempt=1,
            job_token="placeholder",
            actor_role=Role.editor,
        )
        payload = {k: v for k, v in encode_envelope(envelope).items() if k not in {"job_token", "attempt"}}
        job_id = uuid4()
        await self.queue.enqueue(
            EnqueueRequest(
                job_id=job_id,
                kind=JobKind.compile,
                project_id=uuid4(),
                user_id=uuid4(),
                tags=frozenset({"compile"}),
                payload=payload,
                max_attempts=2,
                timeout_s=600.0,
            )
        )
        polled = await self.client.post("/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 1}, headers=headers)
        data = polled.json()["envelope"]
        assert data is not None
        return _Leased(headers, job_id, data["attempt"], data["job_token"])

    def url(self, leased: _Leased, tail: str) -> str:
        return f"/api/runner/v1/jobs/{leased.job_id}/{tail}"

    async def announce(self, leased: _Leased, data: bytes, path: str = "main.pdf", size: int | None = None) -> int:
        response = await self.client.post(
            self.url(leased, "artifacts"),
            json={
                "attempt": leased.attempt,
                "artifact": {"path": path, "sha256": _sha(data), "size": len(data) if size is None else size},
            },
            headers=leased.auth,
        )
        return response.status_code

    async def put(self, leased: _Leased, sha: str, data: bytes) -> int:
        response = await self.client.put(self.url(leased, f"artifacts/{sha}"), content=data, headers=leased.auth)
        return response.status_code

    async def complete(
        self, leased: _Leased, artifacts: list[dict[str, object]], attempt: int | None = None, status: str = "succeeded"
    ):  # type: ignore[no-untyped-def]
        return await self.client.post(
            self.url(leased, "complete"),
            json={
                "attempt": leased.attempt if attempt is None else attempt,
                "result": {"status": status, "data": {"build_ok": status == "succeeded"}, "error": None},
                "artifacts": artifacts,
            },
            headers=leased.auth,
        )


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[_Env]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    clock = _Clock()
    queue = InMemoryJobQueue(clock)
    runners = InMemoryRunnerRepository()
    registry = RunnerRegistry(runners, InMemoryRegistrationTokenRepository(), InMemoryAuditLog(), _Uow())
    signer = JobTokenSigner([b"k" * 32])
    queue_service = JobQueueService(queue, lease_s=45.0, timeout_grace_s=15.0, clock=clock)
    blobs = FsJobBlobStore(tmp_path)
    poll = RunnerJobService(
        queue, queue_service, runners, signer, JobWakeup(), lease_s=45.0, timeout_grace_s=15.0, clock=clock
    )
    io = RunnerJobIoService(
        queue,
        queue_service,
        runners,
        signer,
        blobs,
        FsJobOutputIngest(tmp_path, max_bytes=100_000),
        FsJobLogSink(tmp_path, max_bytes=100),
        clock=clock,
    )

    class _Provider(Provider):
        scope = Scope.APP

        @provide
        def registry_(self) -> RunnerRegistry:
            return registry

        @provide
        def poll_(self) -> RunnerJobService:
            return poll

        @provide
        def io_(self) -> RunnerJobIoService:
            return io

    app = FastAPI()
    include_server_routers(app)
    install_exception_handlers(app)
    container = make_async_container(_Provider(), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield _Env(client, queue, clock, registry, blobs, tmp_path)
    await container.close()


async def test__log__batches_are_appended_and_repeat_is_idempotent(env: _Env) -> None:
    leased = await env.lease()
    first = {"attempt": 1, "seq": 0, "lines": ["a", "b"]}

    for body in (first, first, {"attempt": 1, "seq": 1, "lines": ["c"]}):
        response = await env.client.post(env.url(leased, "log"), json=body, headers=leased.auth)
        assert response.status_code == 204

    log = (env.root / "logs" / str(leased.job_id) / "1.log").read_text()
    assert log == "a\nb\nc\n"


async def test__log__over_the_limit__is_truncated_not_rejected(env: _Env) -> None:
    leased = await env.lease()

    response = await env.client.post(
        env.url(leased, "log"), json={"attempt": 1, "seq": 0, "lines": ["x" * 90, "y" * 90]}, headers=leased.auth
    )

    assert response.status_code == 204
    assert (env.root / "logs" / str(leased.job_id) / "1.log").stat().st_size == 100


async def test__log__stale_attempt__409(env: _Env) -> None:
    leased = await env.lease()

    response = await env.client.post(
        env.url(leased, "log"), json={"attempt": 2, "seq": 0, "lines": ["a"]}, headers=leased.auth
    )

    assert response.status_code == 409
    assert response.json()["code"] == "stale_attempt"


async def test__blobs_need__manifest_blob_is_located(env: _Env) -> None:
    leased = await env.lease()

    response = await env.client.post(
        env.url(leased, "blobs/need"), json={"attempt": 1, "sha256": [_sha(_INPUT)]}, headers=leased.auth
    )

    assert response.status_code == 200
    assert response.json() == {"blobs": [{"sha256": _sha(_INPUT), "url": None}]}


async def test__blobs_need__sha_outside_manifest__forbidden(env: _Env) -> None:
    leased = await env.lease()
    foreign = await env.blobs.store(b"someone else's file")

    response = await env.client.post(
        env.url(leased, "blobs/need"), json={"attempt": 1, "sha256": [_sha(_INPUT), foreign]}, headers=leased.auth
    )

    assert response.status_code == 403
    assert response.json()["code"] == "blob_forbidden"


async def test__blob_get__streams_manifest_blob(env: _Env) -> None:
    leased = await env.lease()

    response = await env.client.get(env.url(leased, f"blobs/{_sha(_INPUT)}"), headers=leased.auth)

    assert response.status_code == 200
    assert response.content == _INPUT


async def test__blob_get__foreign_sha_404_even_when_stored(env: _Env) -> None:
    leased = await env.lease()
    foreign = await env.blobs.store(b"someone else's file")

    response = await env.client.get(env.url(leased, f"blobs/{foreign}"), headers=leased.auth)

    assert response.status_code == 404
    assert response.json()["code"] == "blob_missing"


async def test__blob_get__malformed_sha__422(env: _Env) -> None:
    leased = await env.lease()

    response = await env.client.get(env.url(leased, "blobs/..%2F..%2Fetc"), headers=leased.auth)

    assert response.status_code in (404, 422)


async def test__artifact__announce_put_complete__outputs_are_accepted(env: _Env) -> None:
    leased = await env.lease()
    assert await env.announce(leased, _PDF) == 200
    assert await env.put(leased, _sha(_PDF), _PDF) == 204

    response = await env.complete(leased, [{"path": "main.pdf", "sha256": _sha(_PDF), "size": len(_PDF)}])

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    job = await env.queue.get(leased.job_id)
    assert job is not None
    assert job.state is JobState.succeeded
    assert job.result is not None
    assert job.result["artifacts"] == [{"path": "main.pdf", "sha256": _sha(_PDF), "size": len(_PDF)}]
    stored = env.root / "outputs" / str(leased.job_id) / "1" / _sha(_PDF)
    assert stored.read_bytes() == _PDF


async def test__artifact__wrong_content__rejected_and_nothing_stored(env: _Env) -> None:
    leased = await env.lease()
    await env.announce(leased, _PDF)
    tampered = b"%PDF-1.7 " + b"y" * 5000

    response = await env.client.put(env.url(leased, f"artifacts/{_sha(_PDF)}"), content=tampered, headers=leased.auth)

    assert response.status_code == 422
    assert response.json()["code"] == "artifact_invalid"
    assert not (env.root / "outputs" / str(leased.job_id) / "1" / _sha(_PDF)).exists()
    assert list((env.root / "outputs" / str(leased.job_id) / "1").glob(".upload-*")) == []


async def test__artifact__wrong_size__rejected(env: _Env) -> None:
    leased = await env.lease()
    await env.announce(leased, _PDF)

    assert await env.put(leased, _sha(_PDF), _PDF + b"extra") == 422
    assert await env.put(leased, _sha(_PDF), _PDF[:-1]) == 422


async def test__artifact__not_announced__rejected(env: _Env) -> None:
    leased = await env.lease()

    assert await env.put(leased, _sha(_PDF), _PDF) == 422


async def test__artifact__over_the_size_limit__rejected_on_announce(env: _Env) -> None:
    leased = await env.lease()

    assert await env.announce(leased, _PDF, size=100_001) == 422


async def test__complete__artifact_not_uploaded__422_and_job_keeps_running(env: _Env) -> None:
    leased = await env.lease()
    await env.announce(leased, _PDF)

    response = await env.complete(leased, [{"path": "main.pdf", "sha256": _sha(_PDF), "size": len(_PDF)}])

    assert response.status_code == 422
    assert response.json()["code"] == "artifact_invalid"
    job = await env.queue.get(leased.job_id)
    assert job is not None
    assert job.state is JobState.running


async def test__complete__stale_attempt__409(env: _Env) -> None:
    leased = await env.lease()

    response = await env.complete(leased, [], attempt=2)

    assert response.status_code == 409
    assert response.json()["code"] == "stale_attempt"


async def test__complete__lease_lost_and_job_retaken__old_runner_gets_409_and_outputs_are_ignored(env: _Env) -> None:
    leased = await env.lease()
    await env.announce(leased, _PDF)
    await env.put(leased, _sha(_PDF), _PDF)
    env.clock.advance(46)
    await env.queue.requeue_expired()
    second = await env.register()
    retaken = await env.client.post("/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 1}, headers=second)
    assert retaken.json()["envelope"]["attempt"] == 2

    stale = await env.complete(leased, [{"path": "main.pdf", "sha256": _sha(_PDF), "size": len(_PDF)}])

    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_attempt"
    job = await env.queue.get(leased.job_id)
    assert job is not None
    assert job.state is JobState.running


async def test__complete__twice__second_is_stale(env: _Env) -> None:
    leased = await env.lease()
    assert (await env.complete(leased, [])).status_code == 200

    again = await env.complete(leased, [])

    assert again.status_code == 409
    assert again.json()["code"] == "stale_attempt"


async def test__complete__failed_status__discards_uploaded_outputs(env: _Env) -> None:
    leased = await env.lease()
    await env.announce(leased, _PDF)
    await env.put(leased, _sha(_PDF), _PDF)

    response = await env.complete(
        leased, [{"path": "main.pdf", "sha256": _sha(_PDF), "size": len(_PDF)}], status="failed"
    )

    assert response.status_code == 200
    job = await env.queue.get(leased.job_id)
    assert job is not None
    assert job.state is JobState.failed
    assert not (env.root / "outputs" / str(leased.job_id)).exists()


async def test__io__finished_job_rejects_log_and_outputs(env: _Env) -> None:
    leased = await env.lease()
    await env.complete(leased, [])

    log = await env.client.post(
        env.url(leased, "log"), json={"attempt": 1, "seq": 0, "lines": ["a"]}, headers=leased.auth
    )

    assert log.status_code == 409
    assert log.json()["code"] == "job_not_running"


async def test__io__foreign_job_token_and_unknown_job(env: _Env) -> None:
    leased = await env.lease()
    other = await env.lease()

    foreign = await env.client.post(
        env.url(leased, "log"),
        json={"attempt": 1, "seq": 0, "lines": ["a"]},
        headers={**other.headers, "X-Job-Token": other.job_token},
    )
    ghost = uuid4()
    runner = (await env.registry.list_runners(_ADMIN))[0]
    token = JobTokenSigner([b"k" * 32]).sign(str(ghost), runner.id, env.clock.now + timedelta(hours=1))
    unknown = await env.client.post(
        f"/api/runner/v1/jobs/{ghost}/complete",
        json={"attempt": 1, "result": {"status": "failed", "data": None, "error": None}, "artifacts": []},
        headers={**leased.headers, "X-Job-Token": token},
    )

    assert foreign.status_code == 401
    assert foreign.json()["code"] == "job_token_invalid"
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "job_not_found"


@pytest.mark.parametrize("path", ["../x", "/abs", "a\\b", "C:x"])
async def test__announce__unsafe_path__422_artifact_invalid(env: _Env, path: str) -> None:
    leased = await env.lease()

    response = await env.client.post(
        env.url(leased, "artifacts"),
        json={"attempt": leased.attempt, "artifact": {"path": path, "sha256": _sha(_PDF), "size": len(_PDF)}},
        headers=leased.auth,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "artifact_invalid"


@pytest.mark.parametrize("path", ["../x", "/abs"])
async def test__complete__unsafe_path__422_and_job_keeps_running(env: _Env, path: str) -> None:
    leased = await env.lease()

    response = await env.complete(leased, [{"path": path, "sha256": _sha(_PDF), "size": len(_PDF)}])

    assert response.status_code == 422
    assert response.json()["code"] == "artifact_invalid"
    job = await env.queue.get(leased.job_id)
    assert job is not None
    assert job.state is JobState.running


@pytest.mark.parametrize(
    "result",
    [
        {"status": "succeeded", "data": {"build_ok": True}, "error": None, "extra": 1},
        {"status": "succeeded", "data": {"unknown_field": 1}, "error": None},
    ],
)
async def test__complete__malformed_result__422_and_job_keeps_running(env: _Env, result: dict[str, object]) -> None:
    leased = await env.lease()

    response = await env.client.post(
        env.url(leased, "complete"),
        json={"attempt": leased.attempt, "result": result, "artifacts": []},
        headers=leased.auth,
    )

    assert response.status_code == 422
    job = await env.queue.get(leased.job_id)
    assert job is not None
    assert job.state is JobState.running
