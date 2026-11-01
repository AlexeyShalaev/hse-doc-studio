"""Изоляция личных раннеров (раздел 5 спецификации) на живом приложении: протокол раннера поверх Postgres.

Задачи ставятся прямо в очередь, как их ставит диспетчер: проект и его участники лежат в базе, маршрут
решён заранее. Проверяется только то, что видят и могут раннеры.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.jobs.codec import encode_envelope
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.queue import EnqueueRequest
from hse_doc_studio.core.jobs.routing import JobRoute, RouteReason, RunnerScope
from hse_doc_studio.core.jobs.wire import JobEnvelope
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue

from tests.integration.api.personal.conftest import Person, Stand, seed_shared_project
from tests.unit.core.jobs.samples import make_compile_spec

pytestmark = pytest.mark.pg

_POLL = {"wait_s": 0, "free_slots": 1}


async def _enqueue(
    stand: Stand,
    project: str,
    author: Person,
    *,
    owner: Person,
    window_s: float = 60.0,
    kind: JobKind = JobKind.compile,
) -> UUID:
    actor = Actor.user(author.id, "Автор", author.email, is_instance_admin=True, source=ActorSource.session)
    spec = replace(make_compile_spec(), id=uuid4(), project_id=UUID(project), actor=actor)
    envelope = JobEnvelope(spec=spec, manifest=(), timeout_s=300.0, attempt=1, job_token="-")
    payload = {k: v for k, v in encode_envelope(envelope).items() if k not in {"job_token", "attempt"}}
    await PostgresJobQueue(stand.sessions).enqueue(
        EnqueueRequest(
            job_id=spec.id,
            kind=kind,
            project_id=spec.project_id,
            user_id=UUID(author.id),
            tags=spec.tags,
            payload=payload,
            max_attempts=2,
            route=JobRoute.personal_first,
            route_owner_id=owner.id,
            personal_until=datetime.now(UTC) + timedelta(seconds=window_s),
            route_reason=RouteReason.waiting_personal,
        )
    )
    return spec.id


def _shared_runner(stand: Stand) -> dict[str, str]:
    token = stand.admin().post("/api/admin/runner-tokens", json={"label": "shared"}).json()["secret"]
    return stand.register(token, "shared-1", tags=("tex", "pack", "office", "verify"))


async def test__i1_i4__owner_runner_gets_owner_build_with_trimmed_actor(stand: Stand) -> None:
    anna, boris = await stand.person("anna"), await stand.person("boris")
    project = await seed_shared_project(stand, anna, (boris, "editor"))
    job = await _enqueue(stand, project, anna, owner=anna)
    shared = _shared_runner(stand)
    boris_runner = stand.personal_runner(boris, "Ноутбук Бориса")
    anna_runner = stand.personal_runner(anna)

    assert stand.client.post("/api/runner/v1/poll", json=_POLL, headers=shared).json()["envelope"] is None
    assert stand.client.post("/api/runner/v1/poll", json=_POLL, headers=boris_runner).json()["envelope"] is None
    envelope = stand.client.post("/api/runner/v1/poll", json=_POLL, headers=anna_runner).json()["envelope"]
    assert envelope["spec"]["id"] == str(job)
    actor = envelope["spec"]["actor"]
    assert (actor["id"], actor["email"], actor["link_id"], actor["is_instance_admin"]) == (anna.id, None, None, False)


async def test__i1__coauthor_build_follows_policy_and_never_reaches_coauthor_runner(stand: Stand) -> None:
    anna, boris = await stand.person("anna"), await stand.person("boris")
    project = await seed_shared_project(stand, anna, (boris, "editor"))
    anna_runner = stand.personal_runner(anna)
    boris_runner = stand.personal_runner(boris, "Ноутбук Бориса")
    job = await _enqueue(stand, project, boris, owner=anna)

    assert stand.client.post("/api/runner/v1/poll", json=_POLL, headers=anna_runner).json()["envelope"] is None
    stand.client.put(
        f"/api/v1/projects/{project}/build-runners", json={"policy": "owner"}, headers=anna.headers
    ).raise_for_status()
    # Смена политики на owner окно не трогает: сборка Бориса теперь достаётся раннеру Анны.
    assert stand.client.post("/api/runner/v1/poll", json=_POLL, headers=boris_runner).json()["envelope"] is None
    envelope = stand.client.post("/api/runner/v1/poll", json=_POLL, headers=anna_runner).json()["envelope"]
    assert envelope["spec"]["id"] == str(job)
    assert envelope["spec"]["actor"]["email"] is None


async def test__fallback__shared_runner_takes_after_the_window_with_reason(stand: Stand) -> None:
    anna = await stand.person("anna")
    project = await seed_shared_project(stand, anna)
    job = await _enqueue(stand, project, anna, owner=anna, window_s=0)
    shared = _shared_runner(stand)

    envelope = stand.client.post("/api/runner/v1/poll", json=_POLL, headers=shared).json()["envelope"]
    assert envelope["spec"]["id"] == str(job)
    # Общий раннер видит актора как раньше: урезание только для личных.
    assert envelope["spec"]["actor"]["email"] == anna.email
    taken = await PostgresJobQueue(stand.sessions).get(job)
    assert taken is not None
    assert (taken.runner_scope, taken.route_reason) == (RunnerScope.shared, RouteReason.fallback_timeout)


async def test__i3_i5__personal_runner_cannot_touch_other_jobs_or_forge_results(stand: Stand) -> None:
    anna, boris = await stand.person("anna"), await stand.person("boris")
    anna_project = await seed_shared_project(stand, anna)
    boris_project = await seed_shared_project(stand, boris)
    await _enqueue(stand, anna_project, anna, owner=anna)
    boris_job = await _enqueue(stand, boris_project, boris, owner=boris)
    anna_runner = stand.personal_runner(anna)
    boris_runner = stand.personal_runner(boris, "Ноутбук Бориса")
    anna_env = stand.client.post("/api/runner/v1/poll", json=_POLL, headers=anna_runner).json()["envelope"]
    boris_env = stand.client.post("/api/runner/v1/poll", json=_POLL, headers=boris_runner).json()["envelope"]
    assert boris_env["spec"]["id"] == str(boris_job)

    # Чужая задача с чужим токеном задачи: токен привязан к раннеру.
    stolen = stand.client.post(
        f"/api/runner/v1/jobs/{boris_job}/heartbeat",
        json={"attempt": 1},
        headers={**anna_runner, "X-Job-Token": boris_env["job_token"]},
    )
    assert stolen.status_code == 401
    forged = stand.client.post(
        f"/api/runner/v1/jobs/{anna_env['spec']['id']}/complete",
        json={
            "attempt": 1,
            "result": {"status": "succeeded", "data": {"build_ok": "yes"}, "error": None},
            "artifacts": [],
        },
        headers={**anna_runner, "X-Job-Token": anna_env["job_token"]},
    )
    assert (forged.status_code, forged.json()["code"]) == (422, "artifact_invalid")
