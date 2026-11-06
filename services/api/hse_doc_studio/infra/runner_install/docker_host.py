"""Раннер соседним контейнером через docker.sock Студии: тот же `docker`, что у страницы «Диск»."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from hse_doc_studio.core.runner_install import (
    Capability,
    InstallError,
    InstallStepState,
    InstallTarget,
    LocalInstance,
    LocalRunnerSpec,
    ProgressReporter,
    UnavailableReason,
)
from hse_doc_studio.infra.docker.cli import docker_available, run_docker

INSTALL_LABEL = "hse-doc-studio.runner-install"
DOCKER_SOCK = "/var/run/docker.sock"
_PULL_TIMEOUT_S = 900.0
_RUN_TIMEOUT_S = 60.0
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,62}$")


def _socket_present() -> bool:
    return bool(os.environ.get("DOCKER_HOST")) or Path(DOCKER_SOCK).exists()


def _socket_gid() -> int | None:
    try:
        return Path(DOCKER_SOCK).stat().st_gid
    except OSError:
        return None


def _scrub(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


class DockerLocalHost:
    target = InstallTarget.docker

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

    async def capability(self) -> Capability:
        if not self._enabled:
            return Capability.no(UnavailableReason.disabled)
        if not _socket_present():
            return Capability.no(UnavailableReason.no_socket)
        if not await docker_available():
            return Capability.no(UnavailableReason.docker_unreachable)
        return Capability.yes()

    def steps(self) -> tuple[str, ...]:
        return ("pull", "start")

    async def install(self, spec: LocalRunnerSpec, report: ProgressReporter) -> None:
        if not _NAME_RE.fullmatch(spec.name):
            raise InstallError("invalid_name")
        await report("pull", InstallStepState.running, spec.image)
        code, _, err = await run_docker(["pull", spec.image], timeout=_PULL_TIMEOUT_S)
        if code != 0:
            raise InstallError("image_pull_failed", _scrub(err.strip()[-400:], spec.token))
        await report("pull", InstallStepState.done, "")

        await report("start", InstallStepState.running, spec.name)
        # Старый контейнер с этим именем заменяем только если он наш.
        if await self._owned(spec.name):
            await run_docker(["rm", "-f", spec.name], timeout=_RUN_TIMEOUT_S)
        # Токен идёт через файл с правами 0600, а не через аргументы: в `ps` и в `docker inspect` его не видно.
        fd, path = tempfile.mkstemp(prefix="hds-runner-", suffix=".env")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"HSE_RUNNER__API_URL={spec.api_url}\n")
                handle.write(f"HSE_RUNNER__TOKEN={spec.token}\n")
                handle.write(f"HSE_RUNNER__DATA_DIR={spec.data_dir}\n")
                handle.write(f"HSE_RUNNER__CONCURRENCY={spec.concurrency}\n")
                handle.write(f"HSE_RUNNER__NAME={spec.name}\n")
            os.chmod(path, 0o600)  # noqa: PTH101
            args = [
                "run",
                "-d",
                "--name",
                spec.name,
                "--restart",
                "unless-stopped",
                "--label",
                f"{INSTALL_LABEL}=true",
                "--env-file",
                path,
                "-v",
                f"{DOCKER_SOCK}:/var/run/docker.sock",
                "-v",
                # Путь одинаков снаружи и внутри: соседние контейнеры сборки монтируют его по пути хоста.
                f"{spec.data_dir}:{spec.data_dir}",
            ]
            gid = _socket_gid()
            if gid is not None:
                args += ["--group-add", str(gid)]
            args += [spec.image, "hse-doc-studio", "runner"]
            code, _, err = await run_docker(args, timeout=_RUN_TIMEOUT_S)
        finally:
            with contextlib.suppress(OSError):
                Path(path).unlink()
        if code != 0:
            raise InstallError("container_start_failed", _scrub(err.strip()[-400:], spec.token))
        await report("start", InstallStepState.done, "")

    async def _owned(self, name: str) -> bool:
        code, out, _ = await run_docker(
            ["ps", "-a", "--filter", f"label={INSTALL_LABEL}=true", "--filter", f"name=^{name}$", "-q"],
            timeout=_RUN_TIMEOUT_S,
        )
        return code == 0 and bool(out.strip())

    async def list_instances(self) -> list[LocalInstance]:
        code, out, _ = await run_docker(
            ["ps", "-a", "--filter", f"label={INSTALL_LABEL}=true", "--format", "{{json .}}"], timeout=_RUN_TIMEOUT_S
        )
        if code != 0:
            return []
        items: list[LocalInstance] = []
        for line in out.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            items.append(
                LocalInstance(
                    target=self.target,
                    name=str(row.get("Names", "")),
                    image=str(row.get("Image", "")),
                    state=str(row.get("State", "")),
                    created_at=_parse_created(str(row.get("CreatedAt", ""))),
                )
            )
        return items

    async def remove(self, name: str) -> bool:
        if not _NAME_RE.fullmatch(name) or not await self._owned(name):
            return False
        code, _, _ = await run_docker(["rm", "-f", name], timeout=_RUN_TIMEOUT_S)
        return code == 0


def _parse_created(raw: str) -> datetime | None:
    # "2026-11-06 12:00:00 +0000 UTC": берём первые три части.
    parts = raw.split()
    if len(parts) < 3:
        return None
    try:
        return datetime.strptime(" ".join(parts[:3]), "%Y-%m-%d %H:%M:%S %z")  # noqa: DTZ007
    except ValueError:
        return None
