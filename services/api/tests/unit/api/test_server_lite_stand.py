"""Стенд server-lite (scripts/dev/server-lite): конфигурация compose не открывает его наружу, seed знает трёх людей."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from hse_doc_studio.api.config import Settings
from hse_doc_studio.core.mode import StudioMode

_STAND = Path(__file__).resolve().parents[5] / "scripts" / "dev" / "server-lite"


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load((_STAND / "compose.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def monkeypatch_module() -> Iterator[pytest.MonkeyPatch]:
    with pytest.MonkeyPatch.context() as patch:
        yield patch


@pytest.fixture(scope="module")
def seed_module(monkeypatch_module: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("server_lite_seed", _STAND / "seed.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass с отложенными аннотациями ищет свой модуль в sys.modules
    monkeypatch_module.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test__compose__services__api_postgres_and_seed_without_s3_or_runner(compose: dict[str, Any]) -> None:
    assert set(compose["services"]) == {"postgres", "api", "seed"}


def test__compose__api_port__published_on_loopback_only(compose: dict[str, Any]) -> None:
    ports = compose["services"]["api"]["ports"]

    assert ports
    assert all(str(port).startswith("127.0.0.1:") for port in ports)
    assert "ports" not in compose["services"]["postgres"]


def test__compose__api_environment__server_mode_with_env_admin(compose: dict[str, Any]) -> None:
    env = compose["services"]["api"]["environment"]

    assert env["HSE_STUDIO__MODE"] == "server"
    assert "HSE_STUDIO__AUTH__EXPERIMENTAL" not in env
    assert env["HSE_STUDIO__DB__AUTO_MIGRATE"] == "true"
    assert env["HSE_STUDIO__AUTH__ADMIN_EMAIL"]
    assert env["HSE_STUDIO__AUTH__REGISTRATION_MODE"] == "invite"


def test__compose__secrets__come_from_env_not_from_the_repository(compose: dict[str, Any]) -> None:
    env = compose["services"]["api"]["environment"]

    for key in ("HSE_STUDIO__SECRETS__KEY", "HSE_STUDIO__AUTH__ADMIN_PASSWORD"):
        assert env[key].startswith("${SERVER_LITE_")
    assert compose["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"].startswith("${SERVER_LITE_")


def test__compose__api_environment__is_accepted_by_the_readiness_gate(compose: dict[str, Any]) -> None:
    from cryptography.fernet import Fernet
    from hse_doc_studio.api.entrypoint import ensure_supported_mode
    from hse_doc_studio.core.readiness import ServerReadinessRegistry

    env = compose["services"]["api"]["environment"]
    cfg = Settings(
        _env_file=None,
        mode=StudioMode(env["HSE_STUDIO__MODE"]),
        server={"host": env["HSE_STUDIO__SERVER__HOST"]},
        db={"dsn": "postgresql://studio:x@postgres:5432/studio"},
        secrets={"key": Fernet.generate_key().decode()},
        auth={"public_url": env["HSE_STUDIO__AUTH__PUBLIC_URL"]},
    )

    ensure_supported_mode(cfg, ServerReadinessRegistry())


def test__seed__demo_users__three_distinct_people_with_projects(seed_module: ModuleType) -> None:
    users = seed_module.DEMO_USERS

    assert len(users) == 3
    assert len({user.email for user in users}) == 3
    assert all(user.projects for user in users)
