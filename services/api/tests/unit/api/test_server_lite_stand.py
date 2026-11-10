"""Стенд server-lite (scripts/dev/server-lite): конфигурация compose не открывает его наружу, seed знает трёх людей,
раннер с поддельным TeX включается отдельно и собирает одинаковый PDF из одинаковых исходников."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

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


def test__compose__services__api_postgres_and_opt_in_seed_and_fake_runner_without_s3(
    compose: dict[str, Any],
) -> None:
    services = compose["services"]

    assert set(services) == {"postgres", "api", "seed", "runner"}
    # Стенд по умолчанию без раннера: M1 проверяет именно это; seed и раннер поднимаются отдельно.
    assert services["seed"]["profiles"] == ["seed"]
    assert services["runner"]["profiles"] == ["runner"]


def test__compose__fake_runner__no_ports_tex_and_verify_tags_script_mounted(compose: dict[str, Any]) -> None:
    runner = compose["services"]["runner"]
    env = runner["environment"]

    assert "ports" not in runner
    assert env["HSE_RUNNER__API_URL"] == "http://api:8000"
    assert {"tex", "verify"} <= set(env["HSE_RUNNER__TAGS"].split(","))
    assert env["HSE_STUDIO__SECRETS__KEY"].startswith("${SERVER_LITE_")
    assert "./fake_tex_runner.py:/runner/fake_tex_runner.py:ro" in runner["volumes"]
    assert runner["command"] == ["python", "/runner/fake_tex_runner.py"]


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


@pytest.fixture(scope="module")
def fake_runner(monkeypatch_module: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("server_lite_fake_tex_runner", _STAND / "fake_tex_runner.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch_module.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def _document(root: Path, text: str) -> Path:
    source = root / "topic_application" / "topic_application.tex"
    (source.parent / "parts").mkdir(parents=True, exist_ok=True)
    source.write_text(text, encoding="utf-8")
    (source.parent / "parts" / "goal.tex").write_text("Цель", encoding="utf-8")
    return source


def test__fake_tex__same_sources__same_pdf_bytes(fake_runner: ModuleType, tmp_path: Path) -> None:
    pdfs = []
    for root in (tmp_path / "a", tmp_path / "b"):
        source = _document(root, "\\documentclass{article}")
        pdf = source.with_suffix(".pdf")
        fake_runner.render_pdf(pdf, "topic_application", fake_runner.sources_digest(source))
        pdfs.append(pdf.read_bytes())

    assert pdfs[0].startswith(b"%PDF-")
    assert pdfs[0] == pdfs[1]


def test__fake_tex__digest__follows_sources_not_outputs(fake_runner: ModuleType, tmp_path: Path) -> None:
    source = _document(tmp_path, "\\documentclass{article}")
    before = fake_runner.sources_digest(source)

    source.with_suffix(".pdf").write_bytes(b"%PDF-old")
    source.with_suffix(".log").write_text("log", encoding="utf-8")
    assert fake_runner.sources_digest(source) == before

    (source.parent / "parts" / "goal.tex").write_text("Уточнённая цель", encoding="utf-8")
    assert fake_runner.sources_digest(source) != before


async def test__fake_tex__executor__pdf_next_to_source_and_done_sentinel(
    fake_runner: ModuleType, tmp_path: Path
) -> None:
    from hse_doc_studio.infra.compile.latexmk import SENTINEL_DONE

    _document(tmp_path, "\\documentclass{article}")

    lines = await fake_runner.FakeTexExecutor().run(
        tmp_path, "topic_application/topic_application.tex", "xelatex", 3, "topic_application", uuid4()
    )
    emitted = [line async for line in lines]

    assert emitted[-1] == SENTINEL_DONE
    assert (tmp_path / "topic_application" / "topic_application.pdf").read_bytes().startswith(b"%PDF-")
