"""Шрифты ХОСТА, увиденные контейнером через docker-сокет.

Раньше вкладка «Системные» в контейнере была пуста всегда, а вместо шрифтов
пользователю показывали команду: смонтируй, мол, свой каталог оверлеем и
перезапусти стек. Это ровно та ручная работа, ради устранения которой продукт и
существует, — тем более что каталог шрифтов у каждой ОС ровно один и известен
заранее.

Приём тот же, что у обзора папок в мастере настройки: одноразовый контейнер с
бинд-маунтом. Демон резолвит `-v` против ХОСТА, поэтому смонтировать
`C:/Windows/Fonts` можно, ничего не спрашивая. Внутри работает наш собственный
образ, значит там же доступен и разбор имён шрифтов.

Какая это ОС, приложение не спрашивает ни у кого: оно перебирает известные
каталоги и берёт первый, который смонтировался и оказался непустым. Ответ
кэшируется на процесс — переустановка Windows посреди сеанса не предполагается.
"""

from __future__ import annotations

import base64
import json
from pathlib import PurePosixPath

import structlog

from hse_doc_studio.core.fonts.entities import SystemFontFile
from hse_doc_studio.infra.docker.cli import run_docker
from hse_doc_studio.infra.runtime.environment import self_container_ref

logger = structlog.get_logger()

_MOUNT_POINT = "/hostfonts"
_MODULE = "hse_doc_studio.infra.fonts.host_scan"
_SCAN_TIMEOUT_S = 90.0
_READ_TIMEOUT_S = 60.0
_INSPECT_TIMEOUT_S = 5.0
_FALLBACK_IMAGE = "alpine:latest"

# Порядок значим: первый смонтировавшийся и непустой каталог и есть ответ. Внутри
# каждой ОС сначала общесистемный каталог, потом пользовательский.
HOST_FONT_DIRS: tuple[str, ...] = (
    "C:/Windows/Fonts",  # Windows
    "/System/Library/Fonts/Supplemental",  # macOS: сюда Apple кладёт Times New Roman и Arial
    "/System/Library/Fonts",
    "/Library/Fonts",
    "/usr/share/fonts",  # Linux
    "/usr/local/share/fonts",
)


class DockerHostFontProvider:
    """`ISystemFontProvider` поверх docker-сокета — для запуска в контейнере."""

    def __init__(self, *, root_override: str | None = None, fallback_image: str = _FALLBACK_IMAGE) -> None:
        # Явно заданный каталог перебивает перебор. Автоопределение знает только
        # стандартные места, а шрифты можно держать где угодно.
        self._override = (root_override or "").strip() or None
        self._fallback_image = fallback_image
        self._image: str | None = None
        self._root: str | None = None
        self._root_resolved = False
        self._cache: list[SystemFontFile] | None = None

    async def host_font_dir(self) -> str | None:
        """Каталог шрифтов этой машины; None — ни один не подошёл."""
        if self._root_resolved:
            return self._root
        self._root_resolved = True
        for candidate in (self._override,) if self._override else HOST_FONT_DIRS:
            fonts = await self._scan(candidate)
            if fonts:
                self._root = candidate
                self._cache = fonts
                logger.info("host fonts found", directory=candidate, count=len(fonts))
                return candidate
        logger.info("host fonts not found in any known directory")
        return None

    async def source_dir(self) -> str | None:
        return await self.host_font_dir()

    async def list_fonts(self) -> list[SystemFontFile]:
        root = await self.host_font_dir()
        if root is None:
            return []
        if self._cache is None:
            self._cache = await self._scan(root)
        return list(self._cache)

    async def read_font(self, path: str) -> bytes:
        root = await self.host_font_dir()
        if root is None:
            msg = "host font directory is not available"
            raise ValueError(msg)
        relative = self._relative_to_root(path, root)
        rc, out, err = await self._run(root, ["read", _MOUNT_POINT, relative], _READ_TIMEOUT_S)
        if rc != 0:
            msg = f"cannot read host font {path!r}: {err.strip()}"
            raise ValueError(msg)
        return base64.b64decode(out.strip())

    @staticmethod
    def _relative_to_root(path: str, root: str) -> str:
        """Путь внутри каталога шрифтов. Всё, что вне его, — отказ.

        Ручка импорта принимает путь от клиента, и без этой проверки её можно
        было бы попросить прочитать произвольный файл хоста.
        """
        normalised = path.replace("\\", "/")
        prefix = root.rstrip("/") + "/"
        if not normalised.startswith(prefix):
            msg = f"path is not inside the host font directory: {path!r}"
            raise ValueError(msg)
        return str(PurePosixPath(normalised[len(prefix) :]))

    async def _scan(self, root: str) -> list[SystemFontFile]:
        rc, out, _err = await self._run(root, ["scan", _MOUNT_POINT], _SCAN_TIMEOUT_S)
        if rc != 0:
            return []
        try:
            payload = json.loads(out or "[]")
        except json.JSONDecodeError:
            return []
        prefix = root.rstrip("/")
        return [
            SystemFontFile(
                name=str(item.get("name") or ""),
                # Наружу отдаём ХОСТОВЫЙ путь: он же приедет обратно в импорт, и
                # человеку в подсказке показывать надо его, а не `/hostfonts/...`.
                path=f"{prefix}/{item.get('rel') or ''}",
                family=str(item.get("family") or ""),
            )
            for item in payload
            if item.get("name")
        ]

    async def _run(self, root: str, args: list[str], timeout: float) -> tuple[int | None, str, str]:
        image = await self._probe_image()
        return await run_docker(
            [
                "run",
                "--rm",
                "--entrypoint",
                "python",
                # От root: каталог шрифтов Windows принадлежит системе, и
                # непривилегированный `app` из нашего образа его не прочтёт.
                "--user",
                "0:0",
                "-v",
                f"{root}:{_MOUNT_POINT}:ro",
                image,
                "-m",
                _MODULE,
                *args,
            ],
            timeout=timeout,
        )

    async def _probe_image(self) -> str:
        """Свой образ: в нём есть и Python, и наш разбор имён шрифтов."""
        if self._image is not None:
            return self._image
        self_ref = self_container_ref()
        if self_ref is not None:
            rc, out, _err = await run_docker(
                ["inspect", "-f", "{{.Config.Image}}", self_ref],
                timeout=_INSPECT_TIMEOUT_S,
            )
            own = out.strip()
            if rc == 0 and own:
                self._image = own
                return own
        self._image = self._fallback_image
        return self._image
