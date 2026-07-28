from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from contextlib import suppress

import httpx
import structlog

from hse_doc_studio.core.ai_runtime import IHardwareProbe
from hse_doc_studio.core.entities import LoadedModel, OllamaRuntimeStatus
from hse_doc_studio.core.enums import Lang, OllamaRuntimeMode
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.infra.docker.cli import (
    docker_available,
    free_port,
    image_present,
    inspect_container,
    is_port_free,
    managed_label_args,
    published_host_port,
    run_docker,
)
from hse_doc_studio.infra.docker.siblings import (
    SiblingNetwork,
    host_gateway_url,
)
from hse_doc_studio.infra.runtime.environment import in_container

logger = structlog.get_logger()

# Streamed pull-progress strings shown in the «Локальные модели» UI. The pull
# task inherits the request's interface language (asyncio copies the contextvar
# at task creation), so these resolve to the language active when the pull began.
_RUNTIME_UNAVAILABLE = {
    Lang.ru: "Локальный рантайм недоступен — установите движок и попробуйте снова",
    Lang.en: "Local runtime unavailable — install the engine and try again",
}
_PULL_START_FAILED = {
    Lang.ru: "Не удалось начать загрузку (HTTP {code})",
    Lang.en: "Could not start the download (HTTP {code})",
}
_RUNTIME_CONNECTION_ERROR = {
    Lang.ru: "Ошибка соединения с локальным рантаймом",
    Lang.en: "Connection error with the local runtime",
}
_PULL_INTERRUPTED = {
    Lang.ru: "Загрузка прервана: модель не появилась в списке установленных",
    Lang.en: "Download interrupted: the model did not appear in the installed list",
}
_PULL_ERROR = {
    Lang.ru: "Ошибка: {error}",
    Lang.en: "Error: {error}",
}


def _msg(mapping: dict[Lang, str]) -> str:
    return mapping.get(current_interface_language(), mapping[Lang.ru])


_RUN_TIMEOUT_S = 30.0
_START_TIMEOUT_S = 30.0
_STOP_TIMEOUT_S = 30.0
_RM_TIMEOUT_S = 30.0
_HEALTH_POLL_INTERVAL_S = 1.0
_REAPER_INTERVAL_S = 30.0
# Where Ollama stores pulled models inside the official image.
_MODELS_MOUNT = "/root/.ollama"


class OllamaRuntimeManager:
    """Orchestrates a local Ollama runtime over the `docker` CLI + Ollama HTTP API.

    Hybrid by design:
      * if a **native** Ollama is already serving on the configured local URL we
        talk to it directly (best GPU on every OS: CUDA, Metal, ROCm) and never
        manage its lifecycle;
      * otherwise we fall back to a backend-managed **`ollama/ollama` container**
        (same pattern as LanguageTool): started lazily on an explicit user
        action, GPU-accelerated with `--gpus all` when an NVIDIA card is usable
        in Docker (auto-downgrades to CPU if the runtime isn't installed), kept
        warm and stopped after an idle timeout.

    Model dispatch reaches Ollama through the existing OpenAI-compatible client;
    this manager only covers lifecycle plus the native pull/list/delete API.
    """

    def __init__(
        self,
        *,
        image: str,
        container_name: str,
        container_port: int,
        host_port: int,
        local_base_url: str,
        health_path: str,
        model_volume_name: str,
        health_timeout_s: float,
        request_timeout_s: float,
        startup_timeout_s: float,
        idle_timeout_s: float,
        keep_alive: str,
        hardware_probe: IHardwareProbe,
        siblings: SiblingNetwork,
    ) -> None:
        self._image = image
        self._name = container_name
        self._container_port = container_port
        self._host_port = host_port
        self._local_base_url = local_base_url.rstrip("/")
        self._health_path = health_path
        self._model_volume = model_volume_name
        self._health_timeout_s = health_timeout_s
        self._request_timeout_s = request_timeout_s
        self._startup_timeout_s = startup_timeout_s
        self._idle_timeout_s = idle_timeout_s
        self._keep_alive = keep_alive
        self._hardware_probe = hardware_probe
        self._siblings = siblings
        self._base_url: str | None = None
        self._last_used: float | None = None
        self._mode: OllamaRuntimeMode = OllamaRuntimeMode.none
        self._gpu_args: list[str] | None = None  # cached after first detect
        self._lock = asyncio.Lock()

    @property
    def current_base_url(self) -> str | None:
        return self._base_url

    def _native_candidates(self) -> list[str]:
        """Где искать Ollama, установленную ПОЛЬЗОВАТЕЛЕМ на самой машине.

        Нативная Ollama слушает loopback хоста, а мы живём в контейнере — там
        `127.0.0.1` это мы сами. Поэтому в контейнере пробуем ещё и хостовый
        шлюз. Чтобы этот адрес отвечал, у Ollama на хосте должен быть поднят
        `OLLAMA_HOST=0.0.0.0` — по умолчанию она слушает только loopback.
        """
        candidates = [self._local_base_url]
        if in_container():
            candidates.append(host_gateway_url(self._local_base_url))
        return candidates

    async def _probe_native(self) -> str | None:
        """Первый ответивший нативный адрес, иначе None."""
        for candidate in self._native_candidates():
            if await self._probe(candidate):
                return candidate
        return None

    # ── status ───────────────────────────────────────────────────────────────

    async def status(self) -> OllamaRuntimeStatus:
        docker_ok = await docker_available()
        img_installed = await image_present(self._image) if docker_ok else False

        state = await inspect_container(self._name)
        if state.running:
            base = await self._published_base()
            if base and await self._probe(base):
                return OllamaRuntimeStatus(
                    mode=OllamaRuntimeMode.docker,
                    base_url=base,
                    version=await self._version(base),
                    docker_available=docker_ok,
                    engine_image_installed=img_installed,
                    installed_models=await self._list_models(base),
                )

        native = await self._probe_native()
        if native is not None:
            return OllamaRuntimeStatus(
                mode=OllamaRuntimeMode.native,
                base_url=native,
                version=await self._version(native),
                docker_available=docker_ok,
                engine_image_installed=img_installed,
                installed_models=await self._list_models(native),
            )

        return OllamaRuntimeStatus(
            mode=OllamaRuntimeMode.none,
            base_url=None,
            version=None,
            docker_available=docker_ok,
            engine_image_installed=img_installed,
            installed_models=[],
        )

    async def list_installed_models(self) -> list[str]:
        return (await self.status()).installed_models

    # ── lifecycle ──────────────────────────────────────────────────────────────

    async def ensure_running(self) -> str | None:
        """Make the runtime reachable and return its base URL (or None).

        Native first, then adopt/start the managed container. Does NOT pull the
        `ollama/ollama` image — that's an explicit, streamed install step; if the
        image is missing here we return None and the status reports it.
        """
        async with self._lock:
            self._last_used = time.monotonic()
            existing = await self._resolve_existing()
            if existing is not None:
                return existing

            # Fall back to the managed container.
            if not await docker_available():
                return None
            if not await image_present(self._image):
                logger.info("ollama: engine image not installed, skipping start", image=self._image)
                return None

            base = await self._bring_up()
            if base is None:
                return None
            if await self._wait_healthy(base):
                self._base_url, self._mode = base, OllamaRuntimeMode.docker
                return base
            logger.warning("ollama: container did not become healthy", url=base)
            return None

    async def _resolve_existing(self) -> str | None:
        """Reuse a warm endpoint / running managed container / native server, else None."""
        if self._base_url and await self._probe(self._base_url):
            return self._base_url
        # A managed container already running owns the port — classify as docker.
        state = await inspect_container(self._name)
        if state.running:
            base = await self._published_base()
            if base and await self._probe(base):
                self._base_url, self._mode = base, OllamaRuntimeMode.docker
                return base
        # Prefer a user-run native Ollama.
        native = await self._probe_native()
        if native is not None:
            self._base_url, self._mode = native, OllamaRuntimeMode.native
            return native
        return None

    async def _bring_up(self) -> str | None:
        state = await inspect_container(self._name)
        if state.present and state.running and state.image == self._image:
            return await self._published_base()
        if state.present and state.image == self._image:  # stopped, same image — fast restart
            rc, _out, err = await run_docker(["start", self._name], timeout=_START_TIMEOUT_S)
            if rc != 0:
                logger.warning("ollama: docker start failed", err=err.strip())
                return None
            return await self._published_base()
        if state.present:  # stale container from a different image — recreate
            await run_docker(["rm", "-f", self._name], timeout=_RM_TIMEOUT_S)
        return await self._run_new()

    async def _run_new(self) -> str | None:
        port = self._host_port if is_port_free(self._host_port) else free_port()
        base_args = [
            "run",
            "-d",
            "--name",
            self._name,
            *managed_label_args(),
            *self._siblings.publish_args(port, self._container_port),
            "-v",
            f"{self._model_volume}:{_MODELS_MOUNT}",
            "-e",
            f"OLLAMA_KEEP_ALIVE={self._keep_alive}",
        ]
        await self._siblings.ensure()
        gpu_args = await self._gpu_run_args()
        rc, _out, err = await run_docker([*base_args, *gpu_args, self._image], timeout=_RUN_TIMEOUT_S)
        if rc != 0 and gpu_args:
            # The NVIDIA container runtime (nvidia-container-toolkit) isn't
            # installed — retry CPU-only so the user still gets a working runtime.
            # A failed `--gpus` run usually leaves a half-created container under
            # our name, so remove it first or the retry hits a name conflict.
            logger.warning("ollama: GPU run failed, retrying CPU-only", err=err.strip())
            self._gpu_args = []
            await run_docker(["rm", "-f", self._name], timeout=_RM_TIMEOUT_S)
            rc, _out, err = await run_docker([*base_args, self._image], timeout=_RUN_TIMEOUT_S)
        if rc != 0:
            logger.warning("ollama: docker run failed", err=err.strip())
            return None
        return await self._published_base() or f"http://127.0.0.1:{port}"

    async def _gpu_run_args(self) -> list[str]:
        if self._gpu_args is not None:
            return self._gpu_args
        hw = await self._hardware_probe.detect()
        self._gpu_args = ["--gpus", "all"] if hw.docker_gpu_supported else []
        return self._gpu_args

    async def _wait_healthy(self, base_url: str) -> bool:
        deadline = time.monotonic() + self._startup_timeout_s
        while time.monotonic() < deadline:
            if await self._probe(base_url):
                return True
            await asyncio.sleep(_HEALTH_POLL_INTERVAL_S)
        return False

    async def stop(self) -> tuple[bool, str | None]:
        was_native = self._mode == OllamaRuntimeMode.native
        self._base_url = None
        self._last_used = None
        self._mode = OllamaRuntimeMode.none
        if was_native:
            # A native runtime is the user's — never stop it.
            return True, None
        state = await inspect_container(self._name)
        if not state.present or not state.running:
            return True, None
        rc, _out, err = await run_docker(["stop", self._name], timeout=_STOP_TIMEOUT_S)
        if rc != 0:
            return False, err.strip() or "docker stop failed"
        return True, None

    async def reconcile(self) -> OllamaRuntimeStatus:
        """Startup hook: adopt an already-running managed container."""
        st = await self.status()
        if st.mode == OllamaRuntimeMode.docker and st.base_url:
            self._base_url, self._mode = st.base_url, OllamaRuntimeMode.docker
            self._last_used = time.monotonic()
            logger.info("ollama: adopted running container", url=st.base_url)
        return st

    async def idle_reaper_loop(self) -> None:
        """Background loop: stop the managed container after `idle_timeout_s`."""
        while True:
            await asyncio.sleep(_REAPER_INTERVAL_S)
            with suppress(Exception):
                await self._maybe_reap()

    async def _maybe_reap(self) -> None:
        if self._last_used is None:
            return
        if time.monotonic() - self._last_used < self._idle_timeout_s:
            return
        if self._mode != OllamaRuntimeMode.docker:
            # Native runtime isn't ours to stop; just drop our warm reference.
            self._base_url = None
            self._last_used = None
            return
        async with self._lock:
            # Re-validate under the lock: a pull or management call may have
            # refreshed _last_used between the pre-lock check and acquiring it.
            if self._last_used is None or time.monotonic() - self._last_used < self._idle_timeout_s:
                return
            state = await inspect_container(self._name)
            if state.running:
                logger.info("ollama: idle stop", idle_timeout_s=self._idle_timeout_s)
                await run_docker(["stop", self._name], timeout=_STOP_TIMEOUT_S)
            self._base_url = None
            self._last_used = None

    # ── model management ───────────────────────────────────────────────────────

    async def pull_model(self, name: str) -> AsyncGenerator[str, None]:
        """Stream `ollama pull <name>` progress (terminal `__DONE__`/`__FAILED__`)."""
        return self._pull_stream(name)

    async def _pull_stream(self, name: str) -> AsyncGenerator[str, None]:  # noqa: C901 — streaming state machine, flat by design
        base = await self.ensure_running()
        if base is None:
            yield _msg(_RUNTIME_UNAVAILABLE)
            yield "__FAILED__"
            return

        # No read timeout: a pull streams for minutes; only the connect is bounded.
        timeout = httpx.Timeout(None, connect=self._request_timeout_s)
        last = ""
        errored = False
        try:
            async with (
                httpx.AsyncClient(timeout=timeout) as client,
                client.stream("POST", f"{base}/api/pull", json={"name": name, "stream": True}) as resp,
            ):
                if resp.status_code != 200:
                    yield _msg(_PULL_START_FAILED).format(code=resp.status_code)
                    yield "__FAILED__"
                    return
                async for line in resp.aiter_lines():
                    self._last_used = time.monotonic()  # keep the container warm during a long pull
                    msg, is_error = _parse_pull_event(line.strip())
                    if is_error:
                        errored = True
                        if msg:
                            yield msg
                        break
                    if msg and msg != last:
                        last = msg
                        yield msg
        except httpx.HTTPError as exc:
            logger.warning("ollama pull failed", error_type=type(exc).__name__)
            yield _msg(_RUNTIME_CONNECTION_ERROR)
            yield "__FAILED__"
            return
        if errored:
            yield "__FAILED__"
            return
        # Don't infer success from "the loop ended without an error" — a clean
        # mid-stream disconnect ends the loop too. Confirm the model actually
        # landed in the local store before declaring success.
        if _installed_matches(name, await self._list_models(base)):
            yield "__DONE__"
        else:
            yield _msg(_PULL_INTERRUPTED)
            yield "__FAILED__"

    async def delete_model(self, name: str) -> bool:
        base = await self._resolve_base()
        if base is None:
            return False
        timeout = httpx.Timeout(self._request_timeout_s, connect=self._request_timeout_s)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request("DELETE", f"{base}/api/delete", json={"name": name})
        except httpx.HTTPError as exc:
            logger.warning("ollama delete failed", error_type=type(exc).__name__)
            return False
        else:
            return resp.status_code == 200

    async def list_loaded_models(self) -> list[LoadedModel]:
        base = await self._resolve_base()
        if base is None:
            return []
        data = await self._get_json(base, "/api/ps")
        if not data:
            return []
        raw = data.get("models", [])
        if not isinstance(raw, list):
            return []
        out: list[LoadedModel] = []
        for m in raw:
            if not isinstance(m, dict) or not isinstance(m.get("name"), str):
                continue
            out.append(
                LoadedModel(
                    name=str(m["name"]),
                    size_bytes=_as_int(m.get("size")),
                    vram_bytes=_as_int(m.get("size_vram")),
                    expires_at=m["expires_at"] if isinstance(m.get("expires_at"), str) else None,
                )
            )
        return out

    async def unload_model(self, name: str) -> bool:
        base = await self._resolve_base()
        if base is None:
            return False
        # An empty generate with keep_alive=0 evicts the model from memory now.
        timeout = httpx.Timeout(self._request_timeout_s, connect=self._request_timeout_s)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{base}/api/generate", json={"model": name, "keep_alive": 0})
        except httpx.HTTPError as exc:
            logger.warning("ollama unload failed", error_type=type(exc).__name__)
            return False
        else:
            return resp.status_code == 200

    # ── http helpers ───────────────────────────────────────────────────────────

    async def _resolve_base(self) -> str | None:
        """Cheaply find a reachable endpoint (warm → native → managed container).

        Treats a successful resolve as activity (bumps the idle timer) so a user
        actively managing models — listing loaded, deleting, unloading — keeps
        the runtime warm instead of letting the reaper stop it mid-session.
        """
        if self._base_url and await self._probe(self._base_url):
            self._last_used = time.monotonic()
            return self._base_url
        native = await self._probe_native()
        if native is not None:
            self._last_used = time.monotonic()
            return native
        base = await self._published_base()
        if base and await self._probe(base):
            self._last_used = time.monotonic()
            return base
        return None

    async def _published_base(self) -> str | None:
        """Адрес управляемого контейнера: по имени в общей сети, иначе по порту."""
        url = await self._siblings.resolve_url(self._name, self._container_port)
        if url is not None:
            return url
        port = await published_host_port(self._name, self._container_port)
        return f"http://127.0.0.1:{port}" if port else None

    async def _probe(self, base_url: str) -> bool:
        timeout = httpx.Timeout(self._health_timeout_s, connect=self._health_timeout_s)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{base_url}{self._health_path}")
        except httpx.HTTPError as exc:
            logger.debug("ollama health probe failed", exc=str(exc))
            return False
        else:
            return resp.status_code == 200

    async def _get_json(self, base_url: str, path: str) -> dict[str, object] | None:
        timeout = httpx.Timeout(self._request_timeout_s, connect=self._request_timeout_s)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(f"{base_url}{path}")
            if resp.status_code != 200:
                return None
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.debug("ollama get failed", path=path, exc=str(exc))
            return None
        return data if isinstance(data, dict) else None

    async def _list_models(self, base_url: str) -> list[str]:
        data = await self._get_json(base_url, "/api/tags")
        if not data:
            return []
        raw = data.get("models", [])
        if not isinstance(raw, list):
            return []
        names = [m["name"] for m in raw if isinstance(m, dict) and isinstance(m.get("name"), str)]
        return sorted(names)

    async def _version(self, base_url: str) -> str | None:
        data = await self._get_json(base_url, "/api/version")
        if not data:
            return None
        version = data.get("version")
        return version if isinstance(version, str) else None


def _as_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _installed_matches(name: str, installed: list[str]) -> bool:
    # `installed` holds full tags (e.g. "qwen2.5:7b", "qwen3.5:latest"). A pull
    # of a tagged name matches it exactly; a bare name (pull defaults to :latest)
    # matches any of its tags.
    return any(tag == name or tag.startswith(f"{name}:") for tag in installed)


def _parse_pull_event(text: str) -> tuple[str | None, bool]:
    """Parse one NDJSON line from `/api/pull` into (message, is_error)."""
    if not text:
        return None, False
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None, False
    if not isinstance(obj, dict):
        return None, False
    err = obj.get("error")
    if err:
        return _msg(_PULL_ERROR).format(error=err), True
    return _progress_message(obj), False


def _progress_message(obj: dict[str, object]) -> str | None:
    status = obj.get("status")
    if not isinstance(status, str) or not status:
        return None
    total = obj.get("total")
    completed = obj.get("completed")
    if isinstance(total, (int, float)) and isinstance(completed, (int, float)) and total > 0:
        pct = int(completed * 100 / total)
        return f"{status}: {pct}%"
    return status
