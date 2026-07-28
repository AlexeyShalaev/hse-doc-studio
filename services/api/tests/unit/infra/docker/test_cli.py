"""Поиск бинарника докера: один порядок на весь бэкенд.

Раньше имя `docker` было захардкожено строкой в семи независимых местах. У
службы (systemd/launchd) PATH урезан, Colima и Rancher Desktop кладут CLI в
домашний каталог, а Docker Desktop с версии 4.28 — в `~/.docker/bin`. Во всех
этих случаях пользователь видит работающий докер и сообщение
«docker CLI not found», из которого ничего не следует.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.docker import cli


@pytest.fixture(autouse=True)
def _fresh_resolver() -> None:
    """Резолвер кэширует удачу — тесты не должны видеть чужой ответ."""
    cli.configure_docker_binary(None)


@pytest.mark.unit
def test__docker_binary__cli_is_on_path__uses_the_bare_name(monkeypatch) -> None:
    # Голое имя, а не результат which: команды в логах остаются читаемыми, а
    # вызов продолжает уважать PATH процесса.
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/usr/bin/docker")

    assert cli.docker_binary() == "docker"


@pytest.mark.unit
def test__docker_binary__not_on_path_but_installed__falls_back_to_a_known_location(monkeypatch, tmp_path: Path) -> None:
    installed = tmp_path / "docker"
    installed.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    monkeypatch.setattr(cli, "_KNOWN_LOCATIONS", ("/nope/docker", str(installed)))

    assert cli.docker_binary() == str(installed)


@pytest.mark.unit
def test__docker_binary__nowhere_to_be_found__still_returns_a_name_to_try(monkeypatch) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    monkeypatch.setattr(cli, "_KNOWN_LOCATIONS", ())

    assert cli.docker_binary() == "docker"


@pytest.mark.unit
def test__docker_binary__found_once__is_not_searched_again(monkeypatch) -> None:
    calls = 0

    def counting_which(_name: str) -> str:
        nonlocal calls
        calls += 1
        return "/usr/bin/docker"

    monkeypatch.setattr(cli.shutil, "which", counting_which)

    cli.docker_binary()
    cli.docker_binary()

    assert calls == 1


@pytest.mark.unit
def test__docker_binary__absent_at_first_call__is_searched_again_next_time(monkeypatch) -> None:
    # Неудачу кэшировать нельзя: самый частый первый запуск — пользователь
    # увидел, что докера нет, поставил его и вернулся во вкладку. Заставлять его
    # перезапускать ещё и приложение мы не имеем права.
    monkeypatch.setattr(cli, "_KNOWN_LOCATIONS", ())
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    assert cli.docker_binary() == "docker"

    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/usr/local/bin/docker")

    assert cli.docker_binary() == "docker"
    assert cli._docker_binary._resolved == "docker"


@pytest.mark.unit
def test__docker_binary__explicit_setting__wins_over_discovery(monkeypatch) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _name: "/usr/bin/docker")
    cli.configure_docker_binary("/opt/podman/bin/docker")

    assert cli.docker_binary() == "/opt/podman/bin/docker"
