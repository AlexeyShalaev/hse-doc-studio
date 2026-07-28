from __future__ import annotations

import asyncio
import socket
import time
from asyncio import subprocess as asubprocess
from contextlib import suppress
from dataclasses import dataclass

import httpx
import structlog

from hse_doc_studio.infra.docker.cli import docker_binary, managed_label_args
from hse_doc_studio.infra.docker.siblings import SiblingNetwork

logger = structlog.get_logger()

_PS_TIMEOUT_S = 10.0
_INSPECT_TIMEOUT_S = 5.0
_VERSION_TIMEOUT_S = 5.0
_RUN_TIMEOUT_S = 30.0
_START_TIMEOUT_S = 30.0
_STOP_TIMEOUT_S = 30.0
_RM_TIMEOUT_S = 30.0
_LOGS_TIMEOUT_S = 10.0
_PROCESS_TERMINATE_TIMEOUT_S = 5.0
_HEALTH_POLL_INTERVAL_S = 1.0
_REAPER_INTERVAL_S = 30.0


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


class LanguageToolContainerManager:
    """Auto-manages an on-demand LanguageTool container via the `docker` CLI.

    LanguageTool is a JVM HTTP server (not a one-shot CLI like the TeX build),
    so it is started lazily on the first check that needs it, published on a
    free local port, kept warm for subsequent checks, and stopped after an idle
    timeout to free RAM. There is no user-facing enable flag or URL — installing
    the image is the opt-in, and the endpoint is internal
    (``http://127.0.0.1:<free-port>``).

    `ensure_running()` is the entry point (called from the compile/check
    orchestrator); the check engine reads the resolved endpoint via
    `current_base_url`.
    """

    def __init__(
        self,
        *,
        container_name: str,
        container_port: int,
        health_path: str,
        model_volume_name: str,
        health_timeout_s: float,
        startup_timeout_s: float,
        idle_timeout_s: float,
        client: httpx.Client,
        siblings: SiblingNetwork,
    ) -> None:
        self._name = container_name
        self._container_port = container_port
        self._health_path = health_path
        self._model_volume = model_volume_name
        self._health_timeout_s = health_timeout_s
        self._startup_timeout_s = startup_timeout_s
        self._idle_timeout_s = idle_timeout_s
        self._client = client
        self._siblings = siblings
        self._base_url: str | None = None
        self._last_used: float | None = None
        self._lock = asyncio.Lock()

    @property
    def current_base_url(self) -> str | None:
        """The live endpoint set by the last successful ensure_running/reconcile.

        Read by the (synchronous) check engine; `None` means LanguageTool is not
        available for this run and its checks are skipped.
        """
        return self._base_url

    # ── lazy lifecycle ─────────────────────────────────────────────────────

    async def ensure_running(self, image: str) -> str | None:
        """Ensure a healthy LanguageTool container for `image`; return its URL.

        Returns None (and skips LanguageTool) if Docker is unavailable or the
        image isn't installed — installing the image is the opt-in. Idempotent
        and serialized: concurrent checks share one container.
        """
        async with self._lock:
            self._last_used = time.monotonic()
            if self._base_url is not None and await self._probe(self._base_url):
                return self._base_url
            if not await self._docker_available():
                return None
            if not await self._image_present(image):
                logger.info("languagetool: image not installed, skipping checks", image=image)
                return None

            base = await self._bring_up(image)
            if base is None:
                return None
            if await self._wait_healthy(base):
                self._base_url = base
                return base
            logger.warning("languagetool: container did not become healthy", url=base)
            return None

    async def _bring_up(self, image: str) -> str | None:
        state = await self.inspect_container()
        if state.present and state.running and state.image == image:
            return await self._endpoint()
        if state.present and state.image == image:  # stopped, same image — fast restart
            rc, _out, err = await self._run_docker_raw(["start", self._name], timeout=_START_TIMEOUT_S)
            if rc == 0:
                return await self._endpoint()
            # The recorded host port may have become unusable (Windows reserves
            # dynamic ports after a reboot) — recreate on a fresh free port.
            logger.warning("languagetool: docker start failed, recreating", err=err.strip())
        if state.present:  # stale container from a different image — recreate
            await self._run_docker_raw(["rm", "-f", self._name], timeout=_RM_TIMEOUT_S)
        return await self._run_new(image)

    async def _run_new(self, image: str) -> str | None:
        port = self._free_port()
        await self._siblings.ensure()
        rc, _out, err = await self._run_docker_raw(
            [
                "run",
                "-d",
                "--name",
                self._name,
                *managed_label_args(),
                *self._siblings.publish_args(port, self._container_port),
                "-v",
                f"{self._model_volume}:/ngrams",
                image,
            ],
            timeout=_RUN_TIMEOUT_S,
        )
        if rc != 0:
            logger.warning("languagetool: docker run failed", err=err.strip())
            return None
        return await self._endpoint(fallback_port=port)

    async def _wait_healthy(self, base_url: str) -> bool:
        deadline = time.monotonic() + self._startup_timeout_s
        while time.monotonic() < deadline:
            if await self._probe(base_url):
                return True
            await asyncio.sleep(_HEALTH_POLL_INTERVAL_S)
        return False

    async def idle_reaper_loop(self) -> None:
        """Background loop: stop the container after `idle_timeout_s` of no checks."""
        while True:
            await asyncio.sleep(_REAPER_INTERVAL_S)
            with suppress(Exception):
                await self._maybe_reap()

    async def _maybe_reap(self) -> None:
        if self._last_used is None:
            return
        if time.monotonic() - self._last_used < self._idle_timeout_s:
            return
        async with self._lock:
            state = await self.inspect_container()
            if state.running:
                logger.info("languagetool: idle stop", idle_timeout_s=self._idle_timeout_s)
                await self._run_docker_raw(["stop", self._name], timeout=_STOP_TIMEOUT_S)
            self._base_url = None
            self._last_used = None

    async def reconcile(self) -> ContainerState:
        """Startup hook: adopt an already-running container into the live URL."""
        state = await self.inspect_container()
        if state.present and state.running:
            self._base_url = await self._endpoint()
            self._last_used = time.monotonic()
            logger.info("languagetool: adopted running container", url=self._base_url, image=state.image)
        return state

    async def stop(self) -> tuple[bool, str | None]:
        state = await self.inspect_container()
        self._base_url = None
        self._last_used = None
        if not state.present or not state.running:
            return True, None
        rc, _out, err = await self._run_docker_raw(["stop", self._name], timeout=_STOP_TIMEOUT_S)
        if rc != 0:
            return False, err.strip() or "docker stop failed"
        return True, None

    # ── introspection ──────────────────────────────────────────────────────

    async def is_healthy(self) -> bool:
        state = await self.inspect_container()
        if not state.running:
            return False
        base = await self._endpoint()
        return base is not None and await self._probe(base)

    async def inspect_container(self) -> ContainerState:
        rc, out, _err = await self._run_docker_raw(
            [
                "ps",
                "-a",
                "--filter",
                f"name=^/{self._name}$",
                "--format",
                "{{.State}}|{{.Status}}|{{.ID}}|{{.Image}}",
            ],
            timeout=_PS_TIMEOUT_S,
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

    async def logs_tail(self, lines: int = 50) -> str:
        rc, out, err = await self._run_docker_raw(["logs", "--tail", str(lines), self._name], timeout=_LOGS_TIMEOUT_S)
        if rc != 0:
            return ""
        return "\n".join(p for p in (out.strip(), err.strip()) if p)

    async def _endpoint(self, fallback_port: int | None = None) -> str | None:
        """Адрес соседа: по имени в общей сети, иначе по опубликованному порту.

        В контейнере опубликованный `127.0.0.1:<порт>` — это loopback ХОСТА, а не
        наш: без сети LanguageTool был бы «здоров», но недостижим.
        """
        url = await self._siblings.resolve_url(self._name, self._container_port)
        if url is not None:
            return url
        published = await self._published_base_url()
        if published is not None:
            return published
        return f"http://127.0.0.1:{fallback_port}" if fallback_port else None

    async def _published_base_url(self) -> str | None:
        """Read the host port docker published for the container's service port."""
        template = f'{{{{(index (index .NetworkSettings.Ports "{self._container_port}/tcp") 0).HostPort}}}}'
        rc, out, _err = await self._run_docker_raw(
            ["inspect", "--format", template, self._name], timeout=_INSPECT_TIMEOUT_S
        )
        port = out.strip()
        if rc != 0 or not port.isdigit():
            return None
        return f"http://127.0.0.1:{port}"

    async def _docker_available(self) -> bool:
        rc, _out, _err = await self._run_docker_raw(
            ["version", "--format", "{{.Server.Version}}"], timeout=_VERSION_TIMEOUT_S
        )
        return rc == 0

    async def _image_present(self, image: str) -> bool:
        rc, _out, _err = await self._run_docker_raw(["image", "inspect", image], timeout=_INSPECT_TIMEOUT_S)
        return rc == 0

    async def _probe(self, base_url: str) -> bool:
        return await asyncio.to_thread(self._probe_sync, base_url)

    def _probe_sync(self, base_url: str) -> bool:
        try:
            resp = self._client.get(f"{base_url}{self._health_path}", timeout=self._health_timeout_s)
        except Exception as exc:  # noqa: BLE001 — health probe must never raise
            logger.debug("languagetool: health probe failed", exc=str(exc))
            return False
        return resp.status_code == 200

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    async def _run_docker_raw(self, args: list[str], timeout: float) -> tuple[int | None, str, str]:
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
