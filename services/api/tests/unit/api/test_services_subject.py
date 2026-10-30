"""Прокси `/api/services`: токен задачи работает, только пока задача идёт у этого раннера."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from hse_doc_studio.api.routers.services_api import _subject
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.jobs.enums import JobKind, JobState, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.routing import IPersonalRunnerSettings, PersonalRunnerSettings, RunnerScope
from hse_doc_studio.core.jobs.runners import IRunnerRepository, JobTokenSigner

_SIGNER = JobTokenSigner([b"k" * 32])


class _Container:
    def __init__(
        self, job: object | None, runner: object | None, *, enabled: bool = True, owner_active: bool = True
    ) -> None:
        async def queue_get(_job_id: object) -> object | None:
            return job

        async def runner_get(_runner_id: str) -> object | None:
            return runner

        async def current() -> PersonalRunnerSettings:
            return PersonalRunnerSettings(enabled=enabled)

        async def user_get(_user_id: str) -> object | None:
            return SimpleNamespace(can_sign_in=owner_active)

        self._items = {
            JobTokenSigner: _SIGNER,
            IJobQueue: SimpleNamespace(get=queue_get),
            IRunnerRepository: SimpleNamespace(get=runner_get),
            IPersonalRunnerSettings: SimpleNamespace(current=current),
            IUserRepository: SimpleNamespace(get=user_get),
        }

    async def get(self, kind: type) -> object:
        return self._items[kind]


def _request(container: _Container, token: str) -> object:
    return SimpleNamespace(headers={"X-Job-Token": token}, state=SimpleNamespace(dishka_container=container))


_AUTHOR = uuid4()


def _setup(  # noqa: PLR0913
    *,
    state: JobState = JobState.running,
    leased: bool = True,
    revoked: bool = False,
    kind: JobKind = JobKind.compile,
    scope: RunnerScope = RunnerScope.shared,
    enabled: bool = True,
    owner_active: bool = True,
):
    job_id, runner_id = uuid4(), uuid4()
    job = SimpleNamespace(state=state, runner_id=runner_id if leased else uuid4(), kind=kind, user_id=_AUTHOR)
    runner = SimpleNamespace(revoked_at=datetime.now(UTC) if revoked else None, scope=scope, owner_id="anna")
    token = _SIGNER.sign(str(job_id), str(runner_id), datetime.now(UTC) + timedelta(hours=1))
    return job_id, _request(_Container(job, runner, enabled=enabled, owner_active=owner_active), token)


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
        {"kind": JobKind.ai_relay},
        {"kind": JobKind.pack_submission},
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


async def test__personal_runner_job__shares_its_author_quota() -> None:
    """Каждая новая задача личного раннера не открывает свежую долю: ключ это автор задачи."""
    _, request = _setup(scope=RunnerScope.personal)

    assert await _subject(request) == f"user:{_AUTHOR}"  # type: ignore[arg-type]


@pytest.mark.parametrize("case", [{"enabled": False}, {"owner_active": False}])
async def test__personal_runner_turned_off_or_owner_disabled__refused(case: dict[str, bool]) -> None:
    _, request = _setup(scope=RunnerScope.personal, **case)

    with pytest.raises(RunnerAuthError) as caught:
        await _subject(request)  # type: ignore[arg-type]
    assert caught.value.code is RunnerErrorCode.runner_disabled
