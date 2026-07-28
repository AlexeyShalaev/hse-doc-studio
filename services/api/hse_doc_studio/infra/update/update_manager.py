from __future__ import annotations

import asyncio
import socket
from asyncio import subprocess as asubprocess
from collections.abc import Mapping
from contextlib import suppress

import structlog

from hse_doc_studio.infra.compile.docker_image_manager import docker_socket_gid
from hse_doc_studio.infra.docker.cli import docker_binary, managed_label_args

logger = structlog.get_logger()

_UPDATER_NAME = "hse-studio-updater"
_UPDATER_MODULE = "hse_doc_studio.infra.update.updater"
_DOCKER_SOCK = "/var/run/docker.sock"
_INSPECT_TIMEOUT_S = 5.0
_RUN_TIMEOUT_S = 30.0
_RM_TIMEOUT_S = 30.0
_PROCESS_TERMINATE_TIMEOUT_S = 5.0


class UpdateManager:
    """Spawns a detached "updater" container that replaces the running app.

    The backend cannot update itself in-process (recreating its own container
    kills the process), so it launches a sibling that reuses the running app
    image (which has Python + the docker CLI) and runs
    `infra.update.updater`. The updater is detached and deliberately NOT
    `--rm`'d so its `docker logs` survive for post-mortem; the next run clears
    the previous one by name.
    """

    @staticmethod
    def self_container_id() -> str:
        # Inside a container Docker sets the hostname to the (short) container id.
        return socket.gethostname()

    async def self_image(self) -> str | None:
        rc, out, _err = await self._run_docker(
            ["inspect", "-f", "{{.Config.Image}}", self.self_container_id()],
            timeout=_INSPECT_TIMEOUT_S,
        )
        ref = out.strip()
        return ref if rc == 0 and ref else None

    async def spawn_self_update(self, new_image: str) -> bool:
        """Launch the detached updater. Returns False if it couldn't be started."""
        return await self._spawn(new_image=new_image)

    async def spawn_reconfigure(self, mounts: Mapping[str, str], env: Mapping[str, str]) -> bool:
        """Пересоздать себя с новыми биндами и переменными, не меняя версии.

        Это мастер первоначальной настройки: пользователь выбрал папку для своих
        файлов, и её надо примонтировать — а примонтировать что-либо в живой
        контейнер докер не умеет, только пересоздать. Механизм тот же самый, что
        у обновления: сосед из нашего образа переживает нашу смерть, ждёт
        здоровья и откатывается, если новая конфигурация не поднялась.
        """
        return await self._spawn(new_image=None, mounts=mounts, env=env)

    async def _spawn(
        self,
        *,
        new_image: str | None,
        mounts: Mapping[str, str] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> bool:
        image = await self.self_image()
        if image is None:
            logger.warning("self-update: cannot determine own image")
            return False
        target = self.self_container_id()

        # Clear a leftover updater from a previous run (its logs are no longer needed).
        await self._run_docker(["rm", "-f", _UPDATER_NAME], timeout=_RM_TIMEOUT_S)

        worker_args = [target]
        if new_image is not None:
            worker_args.append(new_image)
        for container_path, host_path in (mounts or {}).items():
            worker_args += ["--mount", f"{container_path}={host_path}"]
        for key, value in (env or {}).items():
            worker_args += ["--env", f"{key}={value}"]

        rc, _out, err = await self._run_docker(
            [
                "run",
                "-d",
                "--name",
                _UPDATER_NAME,
                *managed_label_args(),
                "-v",
                f"{_DOCKER_SOCK}:{_DOCKER_SOCK}",
                # Апдейтер работает от того же непривилегированного `app`, что и
                # мы, а сокет приезжает с правами владельца С ХОСТА. Без членства
                # в его группе самый первый `docker inspect` падает с «permission
                # denied», и вся работа заканчивается сообщением «target container
                # not found» — то есть ни обновление, ни перенастройка не
                # начинались вовсе. Своё членство нам не наследуется: контейнер
                # создаётся заново.
                *_socket_group_args(),
                image,
                "python",
                "-m",
                _UPDATER_MODULE,
                *worker_args,
            ],
            timeout=_RUN_TIMEOUT_S,
        )
        if rc != 0:
            logger.warning("self-update: failed to start updater", err=err.strip())
            return False
        logger.info("self-update: updater started", target=target, new_image=new_image, mounts=mounts)
        return True

    async def _run_docker(self, args: list[str], timeout: float) -> tuple[int | None, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                docker_binary(),
                *args,
                stdout=asubprocess.PIPE,
                stderr=asubprocess.PIPE,
            )
        except OSError as exc:
            return None, "", f"docker CLI not found: {exc}"
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await _terminate_process(proc)
            return None, "", "docker command timed out"
        return (
            proc.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )


def _socket_group_args() -> list[str]:
    """`--group-add` с группой-владельцем docker-сокета.

    gid читается прямо у сокета: у нас он смонтирован, и `stat` доступен даже
    там, где чтение самого сокета запрещено. Не прочитали (сокета нет, ОС без
    POSIX-владельцев) — 0 верен для Docker Desktop, где сокет принадлежит
    root:root, и безвреден там, где группа другая: лишнее членство ничего не
    ломает, а нехватка нужного — ломает всё.
    """
    return ["--group-add", str(docker_socket_gid() or 0)]


async def _terminate_process(proc: asubprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with suppress(ProcessLookupError):
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=_PROCESS_TERMINATE_TIMEOUT_S)
    except asyncio.TimeoutError:
        with suppress(ProcessLookupError):
            proc.kill()
