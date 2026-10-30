"""Прокси `/api/services`: токен задачи работает, только пока задача идёт у этого раннера."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from hse_doc_studio.api.routers.services_api import _subject
from hse_doc_studio.core.jobs.enums import JobState, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.runners import IRunnerRepository, JobTokenSigner

_SIGNER = JobTokenSigner([b"k" * 32])


class _Container:
    def __init__(self, job: object | None, runner: object | None) -> None:
        async def queue_get(_job_id: object) -> object | None:
            return job

        async def runner_get(_runner_id: str) -> object | None:
            return runner

        self._items = {
            JobTokenSigner: _SIGNER,
            IJobQueue: SimpleNamespace(get=queue_get),
            IRunnerRepository: SimpleNamespace(get=runner_get),
        }

    async def get(self, kind: type) -> object:
        return self._items[kind]


def _request(container: _Container, token: str) -> object:
    return SimpleNamespace(headers={"X-Job-Token": token}, state=SimpleNamespace(dishka_container=container))


def _setup(*, state: JobState = JobState.running, leased: bool = True, revoked: bool = False):
    job_id, runner_id = uuid4(), uuid4()
    job = SimpleNamespace(state=state, runner_id=runner_id if leased else uuid4())
    runner = SimpleNamespace(revoked_at=datetime.now(UTC) if revoked else None)
    token = _SIGNER.sign(str(job_id), str(runner_id), datetime.now(UTC) + timedelta(hours=1))
    return job_id, _request(_Container(job, runner), token)


async def test__running_job_of_a_live_runner__is_the_subject() -> None:
    job_id, request = _setup()

    assert await _subject(request) == f"job:{job_id}"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "case",
    [
        {"state": JobState.succeeded},
        {"state": JobState.queued},
        {"leased": False},
        {"revoked": True},
    ],
)
async def test__finished_superseded_or_revoked__token_is_refused(case: dict[str, object]) -> None:
    _, request = _setup(**case)  # type: ignore[arg-type]

    with pytest.raises(RunnerAuthError) as caught:
        await _subject(request)  # type: ignore[arg-type]
    assert caught.value.code is RunnerErrorCode.job_token_invalid


async def test__unknown_job_or_runner__token_is_refused() -> None:
    token = _SIGNER.sign(str(uuid4()), str(uuid4()), datetime.now(UTC) + timedelta(hours=1))
    request = _request(_Container(None, None), token)

    with pytest.raises(RunnerAuthError):
        await _subject(request)  # type: ignore[arg-type]
