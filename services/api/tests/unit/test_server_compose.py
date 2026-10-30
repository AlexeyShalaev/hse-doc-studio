"""Серверный compose (deploy/server): сокет докера только у раннера, имена настроек существуют, профили на месте."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from hse_doc_studio.api.config import Settings
from hse_doc_studio.infra.runner.config import RunnerConfig
from pydantic import BaseModel

_DEPLOY = Path(__file__).resolve().parents[4] / "deploy" / "server"
_SOCKET = "/var/run/docker.sock"


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load((_DEPLOY / "docker-compose.yml").read_text(encoding="utf-8"))


def _paths(model: type[BaseModel], prefix: str = "") -> set[str]:
    names: set[str] = set()
    for name, field in model.model_fields.items():
        names.add(f"{prefix}{name}".upper())
        inner = field.annotation
        for candidate in (inner, *getattr(inner, "__args__", ())):
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                names |= _paths(candidate, f"{prefix}{name}__")
    return names


def test_docker_socket_only_on_runner(compose: dict[str, Any]) -> None:
    holders = {
        name for name, svc in compose["services"].items() if any(_SOCKET in str(v) for v in svc.get("volumes", []))
    }
    assert holders == {"runner"}


def test_profiles(compose: dict[str, Any]) -> None:
    services = compose["services"]
    always = {name for name, svc in services.items() if "profiles" not in svc}
    assert always == {"postgres", "minio", "minio-init", "api", "runner"}
    assert {n for n, s in services.items() if s.get("profiles") == ["services"]} == {
        "languagetool-1",
        "languagetool-2",
        "onlyoffice",
    }
    assert services["ollama"]["profiles"] == ["ai"]
    assert "redis" not in services


def test_api_env_names_exist_in_settings(compose: dict[str, Any]) -> None:
    known = _paths(Settings)
    env = compose["services"]["api"]["environment"]
    assert env["HSE_STUDIO__MODE"] == "server"
    unknown = [k for k in env if k.removeprefix("HSE_STUDIO__") not in known]
    assert unknown == []


def test_runner_env_names_exist_in_config(compose: dict[str, Any]) -> None:
    known = {name.upper() for name in RunnerConfig.model_fields}
    env = compose["services"]["runner"]["environment"]
    assert [k for k in env if k.removeprefix("HSE_RUNNER__") not in known] == []
    assert compose["services"]["runner"]["command"] == ["hse-doc-studio", "runner"]


def test_secrets_are_required_and_not_inline(compose: dict[str, Any]) -> None:
    text = (_DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
    for var in ("POSTGRES_PASSWORD", "SECRETS_KEY", "S3_SECRET_KEY", "RUNNER_BOOTSTRAP_TOKEN", "PUBLIC_URL"):
        assert f"${{{var}:?" in text


def test_env_example_covers_required_variables() -> None:
    example = (_DEPLOY / ".env.example").read_text(encoding="utf-8")
    defined = {line.split("=", 1)[0] for line in example.splitlines() if "=" in line and not line.startswith("#")}
    text = (_DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
    for var in ("POSTGRES_PASSWORD", "SECRETS_KEY", "S3_ACCESS_KEY", "S3_SECRET_KEY", "RUNNER_BOOTSTRAP_TOKEN"):
        assert var in defined
        assert var in text
