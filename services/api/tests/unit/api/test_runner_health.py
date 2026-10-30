"""Проверка «runners»: необязательная, мастер видит причину, а `/health/ready` на свежей установке остаётся зелёным."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from hse_doc_studio.api.observability.health import HealthRegistry, build_health_router
from hse_doc_studio.api.observability.install import install_runner_health
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind

from tests.fakes.runners import InMemoryRunnerRepository


class _Container:
    def __init__(self, runners: InMemoryRunnerRepository) -> None:
        self._runners = runners

    async def get(self, kind: type) -> Any:
        return self._runners


def _runner(runner_id: str, *, seen_ago: timedelta | None, revoked: bool = False, personal: bool = False) -> Runner:
    now = utc_now()
    return Runner(
        id=runner_id,
        name=runner_id,
        token_hash=runner_id,
        tags=frozenset(),
        concurrency=1,
        resource_class="standard",
        version="1",
        created_at=now - timedelta(days=1),
        last_seen_at=now - seen_ago if seen_ago is not None else None,
        revoked_at=now if revoked else None,
        owner_kind=RunnerOwnerKind.user if personal else RunnerOwnerKind.instance,
        owner_id="u1" if personal else None,
    )


async def test__probe__reports_reason_until_a_runner_is_online() -> None:
    runners = InMemoryRunnerRepository()
    health = HealthRegistry()
    install_runner_health(FastAPI(), _Container(runners), health)  # type: ignore[arg-type]

    fresh_install = await health.run()
    await runners.add(_runner("revoked", seen_ago=timedelta(seconds=1), revoked=True))
    only_revoked = await health.run()
    await runners.add(_runner("silent", seen_ago=timedelta(hours=2)))
    offline = await health.run()
    await runners.add(_runner("live", seen_ago=timedelta(seconds=5)))
    online = await health.run()

    assert fresh_install == {"runners": "no_runners"}
    assert only_revoked == {"runners": "no_runners"}
    assert offline == {"runners": "no_online_runner"}
    assert online == {"runners": None}
    assert health.optional == {"runners"}


async def test__probe__ignores_personal_runners() -> None:
    # Личный раннер на связи не обслуживает сборки соавторов и организаций: установке нужен общий.
    runners = InMemoryRunnerRepository()
    health = HealthRegistry()
    install_runner_health(FastAPI(), _Container(runners), health)  # type: ignore[arg-type]

    await runners.add(_runner("mine", seen_ago=timedelta(seconds=5), personal=True))
    only_personal = await health.run()
    await runners.add(_runner("silent", seen_ago=timedelta(hours=2)))
    shared_offline = await health.run()

    assert only_personal == {"runners": "no_runners"}
    assert shared_offline == {"runners": "no_online_runner"}


def test__ready__stays_green_without_runners_and_details_name_the_reason() -> None:
    health = HealthRegistry()
    install_runner_health(FastAPI(), _Container(InMemoryRunnerRepository()), health)  # type: ignore[arg-type]
    app = FastAPI()
    app.include_router(build_health_router(health, health_token="secret"))  # noqa: S106
    client = TestClient(app)

    public = client.get("/health/ready")
    detailed = client.get("/health/ready", headers={"Authorization": "Bearer secret"})

    assert (public.status_code, public.json()) == (200, {"status": "ok"})
    assert detailed.json()["checks"] == {"runners": {"ok": False, "reason": "no_runners"}}
