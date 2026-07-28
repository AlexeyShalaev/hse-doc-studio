from __future__ import annotations

import asyncio
import os
import platform
import sys
from asyncio import subprocess as asubprocess
from contextlib import suppress

import psutil
import structlog

from hse_doc_studio.core.entities import HardwareInfo
from hse_doc_studio.core.enums import GpuVendor
from hse_doc_studio.infra.docker.cli import docker_binary
from hse_doc_studio.infra.runtime.environment import self_container_ref

logger = structlog.get_logger()

_CMD_TIMEOUT_S = 5.0
# Разовый контейнер с nvidia-smi: холодный старт медленнее обычной команды.
_GPU_PROBE_TIMEOUT_S = 60.0
_MB_PER_BYTE = 1024 * 1024


class SystemHardwareProbe:
    """Best-effort host GPU/RAM/CPU detection for sizing local-model picks.

    Every probe is wrapped so detection NEVER raises — unknown values come back
    as ``None`` / ``GpuVendor.none``. NVIDIA VRAM comes from ``nvidia-smi``;
    Apple Silicon is detected from the platform (Metal uses unified memory, so
    there is no separate VRAM figure); other GPUs are best-effort by adapter
    name. RAM/CPU come from psutil/os.
    """

    def __init__(self) -> None:
        # Кеш докер-зонда GPU: контейнер поднимается один раз за процесс.
        self._docker_gpu_probe_done = False
        self._docker_gpu_probe_result: str | None = None

    async def detect(self) -> HardwareInfo:
        vendor, gpu_name, vram_mb = await self._detect_gpu()
        return HardwareInfo(
            gpu_vendor=vendor,
            gpu_name=gpu_name,
            vram_mb=vram_mb,
            total_ram_mb=self._total_ram_mb(),
            cpu_count=os.cpu_count(),
            docker_gpu_supported=self._docker_gpu_supported(vendor),
        )

    # ── memory ─────────────────────────────────────────────────────────────

    @staticmethod
    def _total_ram_mb() -> int | None:
        with suppress(Exception):
            return int(psutil.virtual_memory().total // _MB_PER_BYTE)
        return None

    # ── gpu ────────────────────────────────────────────────────────────────

    async def _detect_gpu(self) -> tuple[GpuVendor, str | None, int | None]:
        nvidia = await self._detect_nvidia()
        if nvidia is not None:
            return nvidia
        if self._is_apple_silicon():
            return GpuVendor.apple, "Apple Silicon (Metal)", None
        return await self._detect_other_gpu()

    async def _detect_nvidia(self) -> tuple[GpuVendor, str | None, int | None] | None:
        """Видеокарта NVIDIA: сначала своим `nvidia-smi`, потом через докер.

        В контейнере `nvidia-smi` отсутствует, и карта хоста была не видна вовсе —
        панель писала «GPU не обнаружен» на машине с RTX. Спрашиваем тогда у
        хостового докера: NVIDIA Container Toolkit подкладывает `nvidia-smi` в
        любой контейнер, запущенный с `--gpus all`. Заодно это самый честный ответ
        на вопрос «можно ли отдать карту контейнеру с моделью» — мы её реально отдаём.
        """
        rc, out, _err = await self._run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
        )
        if rc != 0:
            out = await self._nvidia_smi_via_docker()
            if out is None:
                return None
        return self._parse_nvidia_smi(out)

    @staticmethod
    def _parse_nvidia_smi(out: str) -> tuple[GpuVendor, str | None, int | None] | None:
        line = next((ln for ln in out.splitlines() if ln.strip()), "")
        if not line:
            return None
        parts = [p.strip() for p in line.split(",")]
        name = parts[0] if parts and parts[0] else None
        vram_mb: int | None = None
        if len(parts) > 1:
            with suppress(ValueError):
                vram_mb = int(float(parts[1]))  # nvidia-smi reports MiB with nounits
        return GpuVendor.nvidia, name, vram_mb

    async def _nvidia_smi_via_docker(self) -> str | None:
        """Разовый контейнер с `--gpus all`, печатающий nvidia-smi. None — карты нет.

        Образ берём СВОЙ: он заведомо есть на машине (мы из него и запущены), а
        `nvidia-smi` в него подложит сам toolkit. Результат кешируем: состав
        железа за время работы процесса не меняется, а поднимать контейнер на
        каждое открытие настроек незачем.
        """
        if self._docker_gpu_probe_done:
            return self._docker_gpu_probe_result
        self._docker_gpu_probe_done = True

        image = await self._self_image()
        if image is None:
            return None
        rc, out, _err = await self._run(
            [
                docker_binary(),
                "run",
                "--rm",
                "--gpus",
                "all",
                image,
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            timeout=_GPU_PROBE_TIMEOUT_S,
        )
        self._docker_gpu_probe_result = out if rc == 0 and out.strip() else None
        return self._docker_gpu_probe_result

    async def _self_image(self) -> str | None:
        self_ref = self_container_ref()
        if self_ref is None:
            return None
        rc, out, _err = await self._run([docker_binary(), "inspect", "--format", "{{.Config.Image}}", self_ref])
        image = out.strip()
        return image if rc == 0 and image else None

    @staticmethod
    def _is_apple_silicon() -> bool:
        return sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}

    async def _detect_other_gpu(self) -> tuple[GpuVendor, str | None, int | None]:
        # No NVIDIA / not Apple Silicon. On Windows we can still read the adapter
        # name to label AMD/Intel GPUs (no reliable VRAM without extra tooling).
        # Local var (vs. comparing `sys.platform` directly) keeps mypy from
        # narrowing to the build platform and flagging the rest as unreachable.
        plat = str(sys.platform)
        if plat != "win32":
            return GpuVendor.none, None, None
        rc, out, _err = await self._run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name)",
            ]
        )
        name = out.strip() if rc == 0 and out.strip() else None
        if name is None:
            return GpuVendor.none, None, None
        lowered = name.lower()
        if "amd" in lowered or "radeon" in lowered:
            return GpuVendor.amd, name, None
        # Intel iGPU or unknown — not useful for accelerated inference.
        return GpuVendor.none, name, None

    @staticmethod
    def _docker_gpu_supported(vendor: GpuVendor) -> bool:
        # Only NVIDIA can be passed into a Docker container, and only on Linux or
        # Windows (WSL2). Apple Metal is never exposed to containers; AMD has no
        # practical desktop passthrough — both fall back to CPU in a container.
        return vendor == GpuVendor.nvidia and sys.platform in {"linux", "win32"}

    # ── subprocess ─────────────────────────────────────────────────────────

    @staticmethod
    async def _run(args: list[str], timeout: float = _CMD_TIMEOUT_S) -> tuple[int | None, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asubprocess.PIPE,
                stderr=asubprocess.PIPE,
            )
        except OSError as exc:
            logger.debug("hardware probe: command not found", cmd=args[0], exc=str(exc))
            return None, "", str(exc)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            with suppress(ProcessLookupError):
                proc.kill()
            return None, "", "timed out"
        return (
            proc.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
