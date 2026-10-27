import pytest
from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.entrypoint import ensure_supported_mode
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.readiness import ReadinessZone, ServerReadinessCheck, ServerReadinessRegistry, server_readiness


def _green(zone: ReadinessZone, name: str = "base") -> ServerReadinessCheck:
    return ServerReadinessCheck(zone=zone, name=name, probe=lambda: None)


def _all_green() -> ServerReadinessRegistry:
    registry = ServerReadinessRegistry()
    for zone in ReadinessZone:
        registry.register(_green(zone))
    return registry


def test__unmet__empty_registry__lists_every_zone() -> None:
    problems = ServerReadinessRegistry().unmet()

    assert len(problems) == len(ReadinessZone)
    assert all("не зарегистрирована" in problem for problem in problems)


def test__unmet__all_zones_green__is_empty() -> None:
    assert _all_green().unmet() == []


def test__unmet__red_check__reports_zone_and_reason() -> None:
    registry = _all_green()
    registry.register(ServerReadinessCheck(zone=ReadinessZone.jobs, name="queue", probe=lambda: "очередь не создана"))

    assert registry.unmet() == ["jobs/queue: очередь не создана"]


def test__register__duplicate__raises() -> None:
    registry = ServerReadinessRegistry()
    registry.register(_green(ReadinessZone.identity))

    with pytest.raises(ValueError, match="уже зарегистрирована"):
        registry.register(_green(ReadinessZone.identity))


def test__ensure_supported_mode__server_with_missing_zones__names_them() -> None:
    with pytest.raises(RuntimeError, match=r"HSE_STUDIO__MODE=server.*stage 2.*identity"):
        ensure_supported_mode(Settings(_env_file=None, mode=StudioMode.server), ServerReadinessRegistry())


def test__ensure_supported_mode__server_all_green__passes() -> None:
    ensure_supported_mode(Settings(_env_file=None, mode=StudioMode.server), _all_green())


def test__ensure_supported_mode__global_registry__still_refuses_server() -> None:
    assert server_readiness.unmet()
    with pytest.raises(RuntimeError, match="stage 2"):
        ensure_supported_mode(Settings(_env_file=None, mode=StudioMode.server))
