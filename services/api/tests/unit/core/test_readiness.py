import pytest
from cryptography.fernet import Fernet
from hse_doc_studio.api import route_scopes
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


def test__ensure_supported_mode__server_all_green__passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(route_scopes, "PER_USER_PENDING", frozenset())
    cfg = Settings(_env_file=None, mode=StudioMode.server, secrets={"key": Fernet.generate_key().decode()})

    ensure_supported_mode(cfg, _all_green())


def test__ensure_supported_mode__server_with_global_user_routes__is_refused() -> None:
    cfg = Settings(_env_file=None, mode=StudioMode.server, secrets={"key": Fernet.generate_key().decode()})

    with pytest.raises(RuntimeError, match="per_user_routes/global_user_routes"):
        ensure_supported_mode(cfg, _all_green())


def test__ensure_supported_mode__server_without_secrets_key__is_refused() -> None:
    with pytest.raises(RuntimeError, match="persistence/secrets_key.*HSE_STUDIO__SECRETS__KEY"):
        ensure_supported_mode(Settings(_env_file=None, mode=StudioMode.server), _all_green())


def test__ensure_supported_mode__global_registry__still_refuses_server() -> None:
    assert server_readiness.unmet()
    with pytest.raises(RuntimeError, match="stage 2"):
        ensure_supported_mode(Settings(_env_file=None, mode=StudioMode.server))


def _experimental(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "mode": StudioMode.server,
        "server": {"host": "127.0.0.1"},
        "db": {"dsn": "postgresql://u:p@localhost/db"},
        "secrets": {"key": Fernet.generate_key().decode()},
        "auth": {"experimental": True},
    }
    return Settings(_env_file=None, **{**base, **overrides})


def test__ensure_supported_mode__experimental_on_loopback__passes_despite_unmet_zones() -> None:
    ensure_supported_mode(_experimental(), ServerReadinessRegistry())


def test__ensure_supported_mode__experimental_on_public_bind__is_refused() -> None:
    with pytest.raises(RuntimeError, match="public bind"):
        ensure_supported_mode(_experimental(server={"host": "0.0.0.0"}), ServerReadinessRegistry())  # noqa: S104


def test__ensure_supported_mode__experimental_in_container__allows_the_container_bind() -> None:
    cfg = _experimental(server={"host": "0.0.0.0"}, auth={"experimental": True, "experimental_in_container": True})  # noqa: S104

    ensure_supported_mode(cfg, ServerReadinessRegistry())


def test__ensure_supported_mode__experimental_without_database__is_refused() -> None:
    with pytest.raises(RuntimeError, match="HSE_STUDIO__DB__DSN"):
        ensure_supported_mode(_experimental(db={}), ServerReadinessRegistry())


def test__ensure_supported_mode__experimental_without_secrets_key__is_refused() -> None:
    with pytest.raises(RuntimeError, match="secrets key"):
        ensure_supported_mode(_experimental(secrets={}), ServerReadinessRegistry())


def test__ensure_supported_mode__experimental_flag_in_local__changes_nothing() -> None:
    ensure_supported_mode(Settings(_env_file=None, mode=StudioMode.local, auth={"experimental": True}))
