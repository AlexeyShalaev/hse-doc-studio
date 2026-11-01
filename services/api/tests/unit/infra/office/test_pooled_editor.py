from __future__ import annotations

import pytest
from hse_doc_studio.infra.office.pooled_editor import ConfiguredReachability, PooledOfficeEditorService
from hse_doc_studio.infra.services.pool import ServicePool

_REPLICAS = ["http://ds-1", "http://ds-2", "http://ds-3"]


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _service(
    clock: _Clock, *, replicas: list[str] | None = None, healthy: set[str] | None = None, max_sessions: int = 2
) -> PooledOfficeEditorService:
    alive = healthy if healthy is not None else set(_REPLICAS)

    async def probe(url: str) -> bool:
        return url in alive

    return PooledOfficeEditorService(
        ServicePool("onlyoffice", replicas if replicas is not None else _REPLICAS, clock=clock),
        "secret",
        probe,
        max_sessions=max_sessions,
        session_ttl_s=100.0,
        probe_interval_s=10.0,
        clock=clock,
    )


@pytest.mark.unit
def test__sticky__same_key_same_replica() -> None:
    service = _service(_Clock())

    assert {service.base_url_for("doc-1-key") for _ in range(20)} <= set(_REPLICAS)
    assert len({service.base_url_for("doc-1-key") for _ in range(20)}) == 1


@pytest.mark.unit
def test__sticky__keys_spread_over_replicas() -> None:
    service = _service(_Clock())

    assert len({service.base_url_for(f"doc-{i}") for i in range(60)}) == len(_REPLICAS)


@pytest.mark.unit
async def test__sticky__dead_replica__only_its_keys_move() -> None:
    clock = _Clock()
    healthy = set(_REPLICAS)
    service = _service(clock, healthy=healthy)
    await service.ensure_running()
    before = {f"doc-{i}": service.base_url_for(f"doc-{i}") for i in range(60)}

    healthy.discard("http://ds-2")
    clock.now += 20
    await service.ensure_running()
    after = {key: service.base_url_for(key) for key in before}

    assert all(url != "http://ds-2" for url in after.values())
    assert all(after[key] == url for key, url in before.items() if url != "http://ds-2")


@pytest.mark.unit
async def test__ensure_running__no_healthy_replica__none() -> None:
    service = _service(_Clock(), healthy=set())

    assert await service.ensure_running() is None
    assert service.base_url_for("k") is None


@pytest.mark.unit
async def test__ensure_running__not_configured__none() -> None:
    service = _service(_Clock(), replicas=[])

    assert await service.ensure_running() is None


@pytest.mark.unit
def test__sessions__limit_enforced_and_released_by_close() -> None:
    service = _service(_Clock(), max_sessions=2)

    assert service.try_open_session("a")
    assert service.try_open_session("b")
    assert not service.try_open_session("c")
    service.mark_closed("a")
    assert service.try_open_session("c")
    assert service.active_sessions == 2


@pytest.mark.unit
def test__sessions__same_key_reopens_without_a_new_slot() -> None:
    service = _service(_Clock(), max_sessions=1)

    assert service.try_open_session("a")
    assert service.try_open_session("a")
    assert not service.try_open_session("b")


@pytest.mark.unit
def test__sessions__released_by_ttl() -> None:
    clock = _Clock()
    service = _service(clock, max_sessions=1)
    assert service.try_open_session("a")

    clock.now += 101

    assert service.try_open_session("b")
    assert service.active_sessions == 1


@pytest.mark.unit
def test__sessions__touch_extends_only_own_document() -> None:
    clock = _Clock()
    service = _service(clock, max_sessions=5)
    service.try_open_session("pres-1", "pres")
    service.try_open_session("other-1", "other")

    clock.now += 60
    service.touch("pres")
    clock.now += 60

    assert service.active_sessions == 1
    assert service.try_open_session("x") is not False


@pytest.mark.unit
def test__sessions__ds_reports_open_editor__counted_even_over_limit() -> None:
    service = _service(_Clock(), max_sessions=1)
    service.try_open_session("a")

    service.mark_active("b")

    assert service.active_sessions == 2
    assert not service.try_open_session("c")


@pytest.mark.unit
async def test__pool_misc__image_never_missing_ai_not_synced_reachability_configured() -> None:
    service = _service(_Clock())

    assert await service.is_image_missing() is False
    assert await service.apply_ai_settings({}) is False
    assert service.jwt_secret == "secret"  # noqa: S105
    assert await ConfiguredReachability("http://api:8000/").base_url() == "http://api:8000"
