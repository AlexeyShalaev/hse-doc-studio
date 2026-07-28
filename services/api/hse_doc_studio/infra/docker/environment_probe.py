"""Что за машина под нами и чем именно нас запустили.

Ни то, ни другое пользователю неоткуда узнать. Интерфейс живёт в контейнере:
`platform.system()` там ответит «Linux» даже на Windows, а число ядер и объём
памяти — это ядра и память ВИРТУАЛЬНОЙ МАШИНЫ Docker Desktop, а не всей машины.
Команду запуска человек мог скопировать не читая, и что в ней оказалось, он
тоже не знает.

Между тем цифры не справочные. От числа ядер и памяти, доступных контейнерам,
зависит, сколько сборок продукт пустит параллельно; от смонтированного сокета —
работает ли вообще хоть что-нибудь. Показать это на экране настройки дешевле,
чем потом разбирать, почему «всё медленно» или «ничего не собирается».
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from hse_doc_studio.core.setup import (
    ContainerMount,
    ContainerRuntimeInfo,
    DockerEngineInfo,
    SetupEnvironment,
)
from hse_doc_studio.infra.docker.cli import run_docker
from hse_doc_studio.infra.runtime.environment import self_container_ref

logger = structlog.get_logger()

_TIMEOUT_S = 10.0
_DOCKER_SOCKET = "/var/run/docker.sock"


class DockerEnvironmentProbe:
    """Спрашивает докера о нём самом и о нашем контейнере.

    Ответ кэшируется: движок посреди сеанса не меняется, а собственную
    конфигурацию может сменить только пересоздание, которое убивает процесс.
    """

    def __init__(self) -> None:
        self._cached: SetupEnvironment | None = None

    async def describe(self) -> SetupEnvironment:
        if self._cached is None:
            self._cached = SetupEnvironment(
                engine=await self._engine(),
                container=await self._container(),
            )
        return self._cached

    async def _engine(self) -> DockerEngineInfo | None:
        rc, out, err = await run_docker(["info", "--format", "{{json .}}"], timeout=_TIMEOUT_S)
        if rc != 0:
            logger.info("environment probe: docker info unavailable", err=err.strip())
            return None
        try:
            info: dict[str, Any] = json.loads(out)
        except json.JSONDecodeError:
            return None
        return DockerEngineInfo(
            server_version=str(info.get("ServerVersion") or ""),
            os_type=str(info.get("OSType") or ""),
            # На Docker Desktop это буквально «Docker Desktop», а на голом
            # движке — дистрибутив хоста. И то и другое пользователю понятно.
            operating_system=str(info.get("OperatingSystem") or ""),
            architecture=str(info.get("Architecture") or ""),
            cpus=int(info.get("NCPU") or 0),
            memory_bytes=int(info.get("MemTotal") or 0),
        )

    async def _container(self) -> ContainerRuntimeInfo | None:
        self_ref = self_container_ref()
        if self_ref is None:
            return None
        rc, out, _err = await run_docker(["inspect", self_ref], timeout=_TIMEOUT_S)
        if rc != 0:
            return None
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, list) or not payload:
            return None
        return _runtime_info(payload[0])


def _runtime_info(container: dict[str, Any]) -> ContainerRuntimeInfo:
    config = container.get("Config") or {}
    host_config = container.get("HostConfig") or {}
    mounts = tuple(
        ContainerMount(
            source=str(m.get("Name") or m.get("Source") or ""),
            destination=str(m.get("Destination") or ""),
            read_only=not m.get("RW", True),
        )
        for m in container.get("Mounts") or []
        if m.get("Destination")
    )
    return ContainerRuntimeInfo(
        image=str(config.get("Image") or ""),
        published_ports=_ports(host_config),
        # Сокет в списке маунтов не показываем отдельной строкой — он деталь
        # реализации; важен сам факт, что он есть.
        mounts=tuple(m for m in mounts if m.destination != _DOCKER_SOCKET),
        socket_mounted=any(m.destination == _DOCKER_SOCKET for m in mounts),
        group_add=tuple(str(g) for g in host_config.get("GroupAdd") or []),
        restart_policy=str((host_config.get("RestartPolicy") or {}).get("Name") or "no"),
        network_mode=str(host_config.get("NetworkMode") or ""),
    )


def _ports(host_config: dict[str, Any]) -> tuple[str, ...]:
    """Публикации в синтаксисе `docker run -p`.

    Ровно в том виде, в каком пользователь писал их сам: экран показывает
    «параметры запуска», и узнать в них свою же команду важнее, чем прочитать
    красивую стрелку.
    """
    published: list[str] = []
    for port_proto, bindings in (host_config.get("PortBindings") or {}).items():
        container_port = port_proto.split("/", 1)[0]
        for binding in bindings or []:
            host_port = binding.get("HostPort")
            if host_port:
                published.append(f"{host_port}:{container_port}")
    return tuple(published)
