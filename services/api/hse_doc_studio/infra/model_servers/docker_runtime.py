"""Контейнеры серверов моделей на хостовом докере (соседние контейнеры рядом со Студией)."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path

import structlog

from hse_doc_studio.core.model_servers import (
    LABEL_SERVER,
    ContainerInfo,
    ContainerRunError,
    ContainerSpec,
)
from hse_doc_studio.infra.docker.cli import docker_available, managed_label_args, published_host_port, run_docker
from hse_doc_studio.infra.docker.siblings import SiblingNetwork, host_gateway_url
from hse_doc_studio.infra.runtime.environment import in_container

logger = structlog.get_logger()

_RUN_TIMEOUT_S = 600.0  # первый запуск тянет образ на несколько гигабайт
_SHORT_TIMEOUT_S = 30.0
_MAX_ERROR_LEN = 400


def _scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text.strip()[:_MAX_ERROR_LEN]


def run_args(spec: ContainerSpec, network: str | None, env_file: str | None, *, gpu: bool) -> list[str]:
    """Аргументы `docker run`. Секретов здесь нет: они едут в `--env-file`."""
    args = ["run", "-d", "--name", spec.name, *managed_label_args(), "--restart", "unless-stopped"]
    for key, value in spec.labels.items():
        args += ["--label", f"{key}={value}"]
    # Наружу не публикуем: в общей сети контейнер виден только Студии, без сети только на loopback хоста.
    args += ["--network", network] if network else ["-p", f"127.0.0.1::{spec.port}"]
    args += ["-v", f"{spec.volume[0]}:{spec.volume[1]}"]
    for key, value in spec.env.items():
        args += ["-e", f"{key}={value}"]
    if env_file:
        args += ["--env-file", env_file]
    if gpu:
        args += ["--gpus", "all"]
    if spec.shm_size:
        args += ["--shm-size", spec.shm_size]
    return [*args, spec.image, *spec.command]


class DockerContainerRuntime:
    def __init__(self, siblings: SiblingNetwork) -> None:
        self._siblings = siblings

    async def available(self) -> bool:
        return await docker_available()

    async def run(self, spec: ContainerSpec) -> str:
        network = await self._siblings.ensure()
        secrets = list(spec.secret_env.values())
        env_file = self._write_env_file(spec) if spec.secret_env else None
        try:
            rc, out, err = await run_docker(run_args(spec, network, env_file, gpu=spec.gpu), timeout=_RUN_TIMEOUT_S)
            if rc != 0 and spec.gpu and spec.gpu_optional:
                # Нет NVIDIA Container Toolkit: остаётся процессор. Неудачный запуск оставляет полусозданный контейнер.
                logger.warning("model server: GPU run failed, retrying on CPU", name=spec.name)
                await run_docker(["rm", "-f", spec.name], timeout=_SHORT_TIMEOUT_S)
                rc, out, err = await run_docker(run_args(spec, network, env_file, gpu=False), timeout=_RUN_TIMEOUT_S)
        finally:
            if env_file:
                with contextlib.suppress(OSError):
                    Path(env_file).unlink()
        if rc != 0:
            raise ContainerRunError(_scrub(err or "docker run failed", secrets))
        return out.strip()

    @staticmethod
    def _write_env_file(spec: ContainerSpec) -> str:
        fd, path = tempfile.mkstemp(prefix="hse-ms-", suffix=".env")
        with os.fdopen(fd, "w") as handle:  # mkstemp создаёт файл с правами 0600
            for key, value in spec.secret_env.items():
                handle.write(f"{key}={value}\n")
        return path

    async def inspect(self, name: str) -> ContainerInfo | None:
        found = await self._inspect([name])
        return found[0] if found else None

    async def list_managed(self) -> list[ContainerInfo]:
        rc, out, _err = await run_docker(
            ["ps", "-a", "--filter", f"label={LABEL_SERVER}", "--format", "{{.Names}}"], timeout=_SHORT_TIMEOUT_S
        )
        names = [line.strip() for line in out.splitlines() if line.strip()] if rc == 0 else []
        return await self._inspect(names) if names else []

    @staticmethod
    async def _inspect(names: list[str]) -> list[ContainerInfo]:
        template = "{{.Name}}\t{{.State.Running}}\t{{.State.Status}}\t{{.Config.Image}}\t{{json .Config.Labels}}"
        rc, out, _err = await run_docker(["inspect", "--format", template, *names], timeout=_SHORT_TIMEOUT_S)
        if rc != 0:
            return []
        found: list[ContainerInfo] = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) != 5:  # noqa: PLR2004 — строка шаблона выше
                continue
            try:
                labels = json.loads(parts[4]) or {}
            except ValueError:
                labels = {}
            found.append(ContainerInfo(parts[0].lstrip("/"), parts[1] == "true", parts[2], parts[3], labels))
        return found

    async def start(self, name: str) -> bool:
        rc, _out, _err = await run_docker(["start", name], timeout=_SHORT_TIMEOUT_S)
        return rc == 0

    async def stop(self, name: str) -> bool:
        rc, _out, _err = await run_docker(["stop", name], timeout=_SHORT_TIMEOUT_S)
        return rc == 0

    async def remove(self, name: str, *, volume: str | None = None) -> bool:
        rc, _out, _err = await run_docker(["rm", "-f", name], timeout=_SHORT_TIMEOUT_S)
        if volume:
            await run_docker(["volume", "rm", volume], timeout=_SHORT_TIMEOUT_S)
        return rc == 0

    async def logs(self, name: str, tail: int) -> str:
        rc, out, err = await run_docker(["logs", "--tail", str(tail), name], timeout=_SHORT_TIMEOUT_S)
        return (out + err) if rc == 0 else ""

    async def endpoint(self, name: str, port: int) -> str | None:
        by_name = await self._siblings.resolve_url(name, port)
        if by_name is not None:
            return by_name
        published = await published_host_port(name, port)
        if published is None:
            return None
        url = f"http://127.0.0.1:{published}"
        return host_gateway_url(url) if in_container() else url
