from __future__ import annotations

import asyncio
import socket
import time
from asyncio import subprocess as asubprocess
from contextlib import suppress
from pathlib import Path

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
_HEALTH_POLL_INTERVAL_S = 1.0
_REAPER_INTERVAL_S = 30.0

_CONVERT_ROUTE = "/forms/libreoffice/convert"

# Office formats Gotenberg/LibreOffice can convert to PDF — shared by the
# compile pipeline (pptx/office preview) and the packaging preflight/assembler
# so the allowlist lives in exactly one place.
CONVERTIBLE_OFFICE_EXTS: frozenset[str] = frozenset(
    {".doc", ".docx", ".odt", ".rtf", ".ppt", ".pptx", ".odp", ".xls", ".xlsx", ".ods"}
)

# ext -> (DocsAPI document.fileType, documentType) for formats ONLYOFFICE
# Document Server can actually EDIT (not just view/convert) — shared between
# the office-editor config/callback and the frontend tab gating.
OFFICE_DOCUMENT_TYPES: dict[str, tuple[str, str]] = {
    ".doc": ("doc", "word"),
    ".docx": ("docx", "word"),
    ".odt": ("odt", "word"),
    ".rtf": ("rtf", "word"),
    ".xls": ("xls", "cell"),
    ".xlsx": ("xlsx", "cell"),
    ".ods": ("ods", "cell"),
    ".ppt": ("ppt", "slide"),
    ".pptx": ("pptx", "slide"),
    ".odp": ("odp", "slide"),
}


class OfficeConvertManager:
    """Auto-manages an on-demand Gotenberg (LibreOffice) container.

    Даёт pptx→PDF-предпросмотр презентации: на «Собрать» copy-only pptx-варианта
    файл конвертируется в соседний PDF для встроенного вьювера. Жизненный цикл —
    как у LanguageTool (`infra/languagetool/container_manager.py`): контейнер
    поднимается лениво на свободном порту при первой конвертации, гасится
    reaper'ом после простоя; opt-in — установленный образ (`docker pull
    gotenberg/gotenberg:8`), тумблера и URL в настройках нет. Файл уходит в
    контейнер HTTP-запросом (multipart), поэтому — в отличие от texlive-сборки —
    маппинг путей проекта не нужен; в контейнер бинд-мунтится только папка
    управляемых шрифтов (fontconfig сканирует /usr/local/share/fonts), чтобы
    HSE Sans / Times New Roman из «Настройки → Шрифты» попадали в PDF.
    """

    def __init__(
        self,
        *,
        image: str,
        container_name: str,
        container_port: int,
        health_path: str,
        convert_timeout_s: float,
        health_timeout_s: float,
        startup_timeout_s: float,
        idle_timeout_s: float,
        fonts_dir: Path | None,
        fonts_host_dir: str | None,
        client: httpx.Client,
        siblings: SiblingNetwork,
    ) -> None:
        self._image = image
        self._name = container_name
        self._container_port = container_port
        self._health_path = health_path
        self._convert_timeout_s = convert_timeout_s
        self._health_timeout_s = health_timeout_s
        self._startup_timeout_s = startup_timeout_s
        self._idle_timeout_s = idle_timeout_s
        self._fonts_dir = fonts_dir
        self._fonts_host_dir = fonts_host_dir
        self._client = client
        self._siblings = siblings
        self._base_url: str | None = None
        self._last_used: float | None = None
        self._lock = asyncio.Lock()

    # ── conversion ─────────────────────────────────────────────────────────

    async def convert_to_pdf(self, source: Path, image: str | None = None) -> bytes | None:
        """Convert an office file to PDF; None when conversion is unavailable.

        Best-effort by design: Docker down, image not installed, container
        unhealthy or a LibreOffice error must never fail the caller's build —
        the pptx itself remains the deliverable, only the preview is skipped.
        `image` — runtime-выбранный образ (Settings → активный); None → образ
        из конструктора (деплой-дефолт).
        """
        base = await self.ensure_running(image)
        if base is None:
            return None
        try:
            return await asyncio.to_thread(self._convert_sync, base, source)
        except Exception as exc:  # noqa: BLE001 — предпросмотр не роняет сборку
            logger.warning("office-convert: conversion failed", source=str(source), exc=str(exc))
            return None

    def _convert_sync(self, base_url: str, source: Path) -> bytes | None:
        with source.open("rb") as fh:
            resp = self._client.post(
                f"{base_url}{_CONVERT_ROUTE}",
                files={"files": (source.name, fh)},
                timeout=self._convert_timeout_s,
            )
        if resp.status_code != 200:
            logger.warning(
                "office-convert: gotenberg returned error",
                status=resp.status_code,
                detail=resp.text[:300],
            )
            return None
        return resp.content

    # ── lazy lifecycle (mirrors LanguageToolContainerManager) ──────────────

    async def ensure_running(self, image: str | None = None) -> str | None:
        """Ensure a healthy Gotenberg container; return its base URL.

        Returns None (preview silently skipped) when Docker is unavailable or
        the image isn't installed — installing the image is the opt-in.
        Idempotent and serialized: concurrent builds share one container.
        `image` — runtime-выбранный образ (Settings → активный); None → образ
        из конструктора. Контейнер от ДРУГОГО образа сносится и пересоздаётся
        из эффективного образа вызова.
        """
        effective_image = image or self._image
        async with self._lock:
            self._last_used = time.monotonic()
            if self._base_url is not None and await self._probe(self._base_url):
                return self._base_url
            if not await self._docker_available():
                return None
            if not await self._image_present(effective_image):
                logger.info("office-convert: image not installed, preview skipped", image=effective_image)
                return None

            base = await self._bring_up(effective_image)
            if base is None:
                return None
            if await self._wait_healthy(base):
                self._base_url = base
                return base
            logger.warning("office-convert: container did not become healthy", url=base)
            return None

    async def _bring_up(self, image: str) -> str | None:
        state = await self._inspect(image)
        if state == "running":
            return await self._endpoint()
        if state == "stopped":  # same-name container, same image — fast restart
            rc, _out, err = await self._run_docker_raw(["start", self._name], timeout=_START_TIMEOUT_S)
            if rc != 0:
                logger.warning("office-convert: docker start failed", err=err.strip())
                return None
            return await self._endpoint()
        return await self._run_new(image)

    async def _run_new(self, image: str) -> str | None:
        port = self._free_port()
        await self._siblings.ensure()
        args = [
            "run",
            "-d",
            "--name",
            self._name,
            *managed_label_args(),
            *self._siblings.publish_args(port, self._container_port),
            *self._fonts_mount_args(),
            image,
        ]
        rc, _out, err = await self._run_docker_raw(args, timeout=_RUN_TIMEOUT_S)
        if rc != 0:
            logger.warning("office-convert: docker run failed", err=err.strip())
            return None
        return await self._endpoint(fallback_port=port)

    def _fonts_mount_args(self) -> list[str]:
        """Bind-mount управляемых шрифтов (как у texlive-сборки).

        `fonts_host_dir` — путь ХОСТА, когда бэкенд сам живёт в контейнере
        (docker -v резолвится демоном против хоста); нативно — сам fonts_dir.
        Пустая/отсутствующая папка не монтируется.
        """
        if self._fonts_dir is None:
            return []
        try:
            has_fonts = self._fonts_dir.is_dir() and any(self._fonts_dir.iterdir())
        except OSError:
            return []
        if not has_fonts:
            return []
        host_path = self._fonts_host_dir or str(self._fonts_dir)
        return ["-v", f"{host_path}:/usr/local/share/fonts/hse:ro"]

    async def _wait_healthy(self, base_url: str) -> bool:
        deadline = time.monotonic() + self._startup_timeout_s
        while time.monotonic() < deadline:
            if await self._probe(base_url):
                return True
            await asyncio.sleep(_HEALTH_POLL_INTERVAL_S)
        return False

    async def idle_reaper_loop(self) -> None:
        """Background loop: stop the container after `idle_timeout_s` without conversions."""
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
            if await self._inspect() == "running":
                logger.info("office-convert: idle stop", idle_timeout_s=self._idle_timeout_s)
                await self._run_docker_raw(["stop", self._name], timeout=_STOP_TIMEOUT_S)
            self._base_url = None
            self._last_used = None

    async def reconcile(self) -> None:
        """Startup hook: adopt an already-running managed container."""
        if await self._inspect() == "running":
            self._base_url = await self._endpoint()
            self._last_used = time.monotonic()
            logger.info("office-convert: adopted running container", url=self._base_url)

    async def stop(self) -> None:
        """Shutdown hook: stop the managed container (auto-starts again on demand)."""
        self._base_url = None
        self._last_used = None
        if await self._inspect() == "running":
            await self._run_docker_raw(["stop", self._name], timeout=_STOP_TIMEOUT_S)

    # ── docker plumbing ─────────────────────────────────────────────────────

    async def inspect_state(self) -> tuple[bool, bool, str | None]:
        """(present, running, status_text) — чистое чтение для status-API.

        В отличие от `_inspect` НЕ сверяет образ и ничего не удаляет: статусный
        эндпоинт не должен иметь побочных эффектов.
        """
        rc, out, _err = await self._run_docker_raw(
            [
                "ps",
                "-a",
                "--filter",
                f"name=^/{self._name}$",
                "--format",
                "{{.State}}|{{.Status}}",
            ],
            timeout=_PS_TIMEOUT_S,
        )
        if rc != 0:
            return False, False, None
        line = next((ln for ln in out.splitlines() if ln.strip()), "")
        if not line:
            return False, False, None
        state, _, status = line.partition("|")
        return True, state.strip() == "running", status.strip() or None

    async def _inspect(self, expected_image: str | None = None) -> str:
        """'running' | 'stopped' | 'absent' — состояние именованного контейнера.

        При заданном `expected_image` контейнер от ДРУГОГО образа сносится
        сразу (absent → пересоздание), чтобы смена активного образа (runtime-
        настройка или office_convert.image) подхватывалась без ручного rm.
        Без `expected_image` (reaper/stop/reconcile) образ не сверяется —
        обслуживаем контейнер, каким бы образом он ни был запущен.
        """
        rc, out, _err = await self._run_docker_raw(
            [
                "ps",
                "-a",
                "--filter",
                f"name=^/{self._name}$",
                "--format",
                "{{.State}}|{{.Image}}",
            ],
            timeout=_PS_TIMEOUT_S,
        )
        if rc != 0:
            return "absent"
        line = next((ln for ln in out.splitlines() if ln.strip()), "")
        if not line:
            return "absent"
        state, _, image = line.partition("|")
        if expected_image is not None and image.strip() != expected_image:
            await self._run_docker_raw(["rm", "-f", self._name], timeout=_RM_TIMEOUT_S)
            return "absent"
        return "running" if state.strip() == "running" else "stopped"

    async def _endpoint(self, fallback_port: int | None = None) -> str | None:
        """Адрес соседа: по имени в общей сети, иначе по опубликованному порту."""
        url = await self._siblings.resolve_url(self._name, self._container_port)
        if url is not None:
            return url
        published = await self._published_base_url()
        if published is not None:
            return published
        return f"http://127.0.0.1:{fallback_port}" if fallback_port else None

    async def _published_base_url(self) -> str | None:
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
            logger.debug("office-convert: health probe failed", exc=str(exc))
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
            if proc.returncode is None:
                with suppress(ProcessLookupError):
                    proc.kill()
            return None, "", "docker command timed out"
        return (
            proc.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
