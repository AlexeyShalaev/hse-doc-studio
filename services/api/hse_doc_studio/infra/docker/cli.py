from __future__ import annotations

import asyncio
import shutil
import socket
from asyncio import subprocess as asubprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()

_DEFAULT_TIMEOUT_S = 30.0
_VERSION_TIMEOUT_S = 5.0
_INSPECT_TIMEOUT_S = 5.0
_PROCESS_TERMINATE_TIMEOUT_S = 5.0

# Applied to every auxiliary container the app spawns (LanguageTool, Gotenberg,
# ONLYOFFICE, Ollama, the self-update helper) so the disk-usage cleanup
# (infra/docker/system_manager.py) can identify "ours" by a `docker ps --filter
# label=...` server-side filter instead of matching on --name — a name is just
# a string the user could coincidentally reuse; a label we set is proof of
# origin. Deliberately NOT applied to the app's own container (all-in-one) —
# that one must never be a cleanup candidate.
MANAGED_LABEL = "com.hse-studio.managed"


def managed_label_args() -> list[str]:
    """`--label` flags to append to a `docker run` for an app-managed container."""
    return ["--label", f"{MANAGED_LABEL}=true"]


# ── Где искать сам бинарник докера ──────────────────────────────────────────
#
# Внутри нашего образа `docker` лежит на PATH, и голого имени хватало. Но PATH —
# не универсальная гарантия: у службы (systemd/launchd) он урезан, Colima и
# Rancher Desktop кладут CLI в домашний каталог, а Docker Desktop с версии 4.28
# ставит его в `~/.docker/bin`. Пользователь при этом видит работающий докер и
# сообщение «docker CLI not found», из которого ничего не следует.
#
# Порядок один на весь бэкенд: явная настройка → PATH → известные места.
_KNOWN_LOCATIONS: tuple[str, ...] = (
    "/usr/local/bin/docker",
    "/usr/bin/docker",
    "/opt/homebrew/bin/docker",  # Homebrew на Apple Silicon
    "/Applications/Docker.app/Contents/Resources/bin/docker",
    "~/.docker/bin/docker",  # Docker Desktop ≥ 4.28
    "~/.rd/bin/docker",  # Rancher Desktop
    "~/.colima/default/bin/docker",  # Colima
    r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
)


class _DockerBinary:
    """Как звать докер. Отдельный объект — ради явного «нашли/не нашли».

    Успешный ответ кэшируется навсегда: переставить докер на ходу нельзя, не
    убив демон. А вот НЕудачу кэшировать запрещено — самый частый сценарий
    первого запуска ровно такой: пользователь открыл продукт, увидел, что докера
    нет, поставил его и вернулся во вкладку. Закэшировав «не нашли», мы заставили
    бы его перезапускать и приложение тоже.
    """

    def __init__(self) -> None:
        self._override: str | None = None
        self._resolved: str | None = None

    def configure(self, path: str | None) -> None:
        """Явно заданный путь из настроек; пустое значение возвращает автопоиск."""
        self._override = path or None
        self._resolved = None

    def get(self) -> str:
        if self._override is not None:
            return self._override
        if self._resolved is not None:
            return self._resolved
        found = self._discover()
        if found is None:
            return "docker"
        self._resolved = found
        if found != "docker":
            logger.info("docker CLI found outside PATH", path=found)
        return found

    @staticmethod
    def _discover() -> str | None:
        """Абсолютный путь нужен ТОЛЬКО когда докера нет на PATH.

        Если он там есть, возвращаем голое имя, а не результат `which`: команды
        в логах остаются читаемыми, а вызов продолжает уважать PATH, который у
        процесса может измениться (`docker context`, обёртки вроде Colima).
        """
        if shutil.which("docker") is not None:
            return "docker"
        for candidate in _KNOWN_LOCATIONS:
            expanded = Path(candidate).expanduser()
            if expanded.is_file():
                return str(expanded)
        return None


_docker_binary = _DockerBinary()


def docker_binary() -> str:
    """Имя или путь исполняемого файла докера для `create_subprocess_exec`."""
    return _docker_binary.get()


def configure_docker_binary(path: str | None) -> None:
    """Зафиксировать путь из настроек (`HSE_STUDIO__DOCKER_BINARY`)."""
    _docker_binary.configure(path)


@dataclass(frozen=True)
class ContainerState:
    present: bool
    running: bool
    status_text: str | None
    container_id: str | None
    image: str | None

    @classmethod
    def absent(cls) -> ContainerState:
        return cls(present=False, running=False, status_text=None, container_id=None, image=None)


async def run_docker(args: list[str], timeout: float = _DEFAULT_TIMEOUT_S) -> tuple[int | None, str, str]:
    """Run `docker <args>` and capture (returncode, stdout, stderr).

    Never raises: a missing docker CLI or a timeout returns rc=None. Shared by
    the managed-container infra (LanguageTool keeps its own copy; new managers
    use this one).
    """
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
        await terminate_process(proc)
        return None, "", "docker command timed out"
    return (
        proc.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def docker_available(timeout: float = _VERSION_TIMEOUT_S) -> bool:
    rc, _out, _err = await run_docker(["version", "--format", "{{.Server.Version}}"], timeout=timeout)
    return rc == 0


async def image_present(image: str, timeout: float = _INSPECT_TIMEOUT_S) -> bool:
    rc, _out, _err = await run_docker(["image", "inspect", image], timeout=timeout)
    return rc == 0


async def inspect_container(name: str, timeout: float = _INSPECT_TIMEOUT_S) -> ContainerState:
    rc, out, _err = await run_docker(
        [
            "ps",
            "-a",
            "--filter",
            f"name=^/{name}$",
            "--format",
            "{{.State}}|{{.Status}}|{{.ID}}|{{.Image}}",
        ],
        timeout=timeout,
    )
    if rc != 0:
        return ContainerState.absent()
    line = next((ln for ln in out.splitlines() if ln.strip()), "")
    if not line:
        return ContainerState.absent()
    parts = line.split("|")
    state = parts[0] if parts else ""
    return ContainerState(
        present=True,
        running=(state == "running"),
        status_text=parts[1] if len(parts) > 1 else None,
        container_id=parts[2] if len(parts) > 2 else None,
        image=parts[3] if len(parts) > 3 else None,
    )


async def published_host_port(name: str, container_port: int, timeout: float = _INSPECT_TIMEOUT_S) -> int | None:
    """Read the host port docker published for the container's service port."""
    template = f'{{{{(index (index .NetworkSettings.Ports "{container_port}/tcp") 0).HostPort}}}}'
    rc, out, _err = await run_docker(["inspect", "--format", template, name], timeout=timeout)
    port = out.strip()
    if rc != 0 or not port.isdigit():
        return None
    return int(port)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


async def terminate_process(proc: asubprocess.Process) -> None:
    if proc.returncode is not None:
        return
    with suppress(ProcessLookupError):
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=_PROCESS_TERMINATE_TIMEOUT_S)
    except asyncio.TimeoutError:
        with suppress(ProcessLookupError):
            proc.kill()
