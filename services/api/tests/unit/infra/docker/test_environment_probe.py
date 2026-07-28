"""Разбор `docker inspect` собственного контейнера для экрана настройки.

Смысл блока «эта машина» в том, что показанные цифры — не справка. Ресурсы,
которые видит демон, это ресурсы КОНТЕЙНЕРОВ: на Docker Desktop между хостом и
демоном стоит виртуальная машина со своей квотой, и человек с 64 ГБ памяти
вполне мог отдать сборкам четыре. А смонтированный сокет — условие, без которого
не работает вообще ничего.
"""

from __future__ import annotations

from typing import Any

import pytest
from hse_doc_studio.infra.docker.environment_probe import _runtime_info

_CONTAINER: dict[str, Any] = {
    "Config": {"Image": "ghcr.io/alexeyshalaev/hse-doc-studio:latest"},
    "HostConfig": {
        "PortBindings": {"8000/tcp": [{"HostIp": "", "HostPort": "17240"}]},
        "RestartPolicy": {"Name": "unless-stopped"},
        "NetworkMode": "bridge",
        "GroupAdd": ["0"],
    },
    "Mounts": [
        {"Type": "bind", "Source": "C:/Users/me/HSE", "Destination": "/data", "RW": True},
        {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock", "RW": True},
    ],
}


@pytest.fixture
def info() -> Any:
    return _runtime_info(_CONTAINER)


@pytest.mark.unit
def test__runtime_info__socket_is_bound__reports_it_as_a_fact_not_a_mount(info: Any) -> None:
    # Сокет — деталь реализации, а не папка пользователя: в списке маунтов он
    # только сбивает с толку, важен сам факт его наличия.
    assert info.socket_mounted is True
    assert [m.destination for m in info.mounts] == ["/data"]


@pytest.mark.unit
def test__runtime_info__no_socket__says_so() -> None:
    container = {**_CONTAINER, "Mounts": [_CONTAINER["Mounts"][0]]}

    assert _runtime_info(container).socket_mounted is False


@pytest.mark.unit
def test__runtime_info__published_port__is_shown_in_docker_run_syntax(info: Any) -> None:
    # Экран показывает «параметры запуска» — узнать в них свою же команду важнее,
    # чем прочитать красиво оформленную стрелку.
    assert info.published_ports == ("17240:8000",)


@pytest.mark.unit
def test__runtime_info__socket_group__is_surfaced(info: Any) -> None:
    # Без членства в этой группе докер недоступен, и увидеть её человек может
    # только здесь: в своей команде запуска он мог её просто не заметить.
    assert info.group_add == ("0",)


@pytest.mark.unit
def test__runtime_info__data_bind__keeps_the_host_side_of_it(info: Any) -> None:
    data = next(m for m in info.mounts if m.destination == "/data")

    assert data.source == "C:/Users/me/HSE"
    assert data.read_only is False


@pytest.mark.unit
def test__runtime_info__bare_container__does_not_crash_on_missing_sections() -> None:
    result = _runtime_info({})

    assert result.image == ""
    assert result.published_ports == ()
    assert result.mounts == ()
    assert result.socket_mounted is False
    assert result.restart_policy == "no"
