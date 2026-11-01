import pytest
from cryptography.fernet import Fernet
from hse_doc_studio.api import route_scopes
from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.entrypoint import ensure_supported_mode
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.readiness import ReadinessZone, ServerReadinessCheck, ServerReadinessRegistry


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


def _server(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "mode": StudioMode.server,
        "db": {"dsn": "postgresql://u:p@localhost/db"},
        "secrets": {"key": Fernet.generate_key().decode()},
        "auth": {"public_url": "https://studio.example.org"},
    }
    return Settings(_env_file=None, **{**base, **overrides})


def test__ensure_supported_mode__server_fully_configured__passes() -> None:
    ensure_supported_mode(_server(), ServerReadinessRegistry())


def test__ensure_supported_mode__server_on_public_bind__passes() -> None:
    ensure_supported_mode(_server(server={"host": "0.0.0.0"}), ServerReadinessRegistry())  # noqa: S104


def test__ensure_supported_mode__server_with_empty_config__lists_everything_missing() -> None:
    with pytest.raises(RuntimeError) as err:
        ensure_supported_mode(Settings(_env_file=None, mode=StudioMode.server), ServerReadinessRegistry())

    text = str(err.value)
    assert "persistence/database" in text
    assert "HSE_STUDIO__DB__DSN" in text
    assert "persistence/secrets_key" in text
    assert "identity/public_url" in text


def test__ensure_supported_mode__server_without_public_url__is_refused() -> None:
    with pytest.raises(RuntimeError, match="identity/public_url.*HSE_STUDIO__AUTH__PUBLIC_URL"):
        ensure_supported_mode(_server(auth={}), ServerReadinessRegistry())


def test__ensure_supported_mode__server_with_lease_below_reaper__is_refused() -> None:
    with pytest.raises(RuntimeError, match="jobs/lease"):
        ensure_supported_mode(_server(jobs={"lease_s": 3, "reaper_interval_s": 5}), ServerReadinessRegistry())


def test__ensure_supported_mode__server_editor_pool_without_backend_url__is_refused() -> None:
    cfg = _server(office_editor={"pool_replicas": ["http://oo:80"]})

    with pytest.raises(RuntimeError, match="services/office_editor"):
        ensure_supported_mode(cfg, ServerReadinessRegistry())


def test__ensure_supported_mode__pending_user_routes__refuse_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(route_scopes, "PER_USER_PENDING", frozenset({("GET", "/agent-personas")}))

    with pytest.raises(RuntimeError, match="per_user_routes/global_user_routes"):
        ensure_supported_mode(_server(), ServerReadinessRegistry())


def test__ensure_supported_mode__server_without_secrets_key__is_refused() -> None:
    with pytest.raises(RuntimeError, match="persistence/secrets_key.*HSE_STUDIO__SECRETS__KEY"):
        ensure_supported_mode(_server(secrets={}), ServerReadinessRegistry())


def test__ensure_supported_mode__unmet_zone_in_registry__is_refused() -> None:
    registry = ServerReadinessRegistry()
    registry.register(ServerReadinessCheck(zone=ReadinessZone.jobs, name="queue", probe=lambda: "очередь не создана"))

    with pytest.raises(RuntimeError, match="jobs/queue: очередь не создана"):
        ensure_supported_mode(_server(), registry)


def test__ensure_supported_mode__local__changes_nothing() -> None:
    ensure_supported_mode(Settings(_env_file=None, mode=StudioMode.local))


def test__ensure_supported_mode__global_registry__accepts_a_configured_server() -> None:
    ensure_supported_mode(_server())
