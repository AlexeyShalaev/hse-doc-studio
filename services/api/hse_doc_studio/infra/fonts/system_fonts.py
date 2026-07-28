from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import structlog

from hse_doc_studio.core.fonts.entities import SystemFontFile
from hse_doc_studio.core.fonts.repositories import ISystemFontProvider
from hse_doc_studio.infra.fonts.font_names import read_family_name

logger = structlog.get_logger()

_FONT_EXTENSIONS: frozenset[str] = frozenset({".ttf", ".otf", ".ttc"})


def _candidate_dirs() -> list[Path]:
    """OS-standard font directories (whether or not they exist)."""
    home = Path.home()
    # Assigning to a local var (vs. comparing `sys.platform` directly) keeps mypy
    # from narrowing to the build platform and flagging the other branches as
    # unreachable — this code is genuinely cross-platform at runtime.
    plat = str(sys.platform)
    if plat == "win32":
        dirs = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
        return dirs
    if plat == "darwin":
        return [
            Path("/System/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Fonts"),
            home / "Library" / "Fonts",
        ]
    # linux / other
    return [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / ".fonts",
        home / ".local" / "share" / "fonts",
    ]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class OsSystemFontProvider(ISystemFontProvider):
    """Отдаёт шрифты, установленные на машине ПОЛЬЗОВАТЕЛЯ.

    Нативно это стандартные каталоги ОС. В контейнере их содержимое принадлежит
    образу, а не пользователю, — показывать оттуда DejaVu под видом «ваших
    системных шрифтов» значит врать. Поэтому шрифты хоста монтируются внутрь
    (см. `compose.system-fonts.yml`), а путь монтирования приходит в `extra_roots`
    и ЗАМЕНЯЕТ каталоги ОС. Пустой список источников — вкладка честно сообщает,
    что системных шрифтов не видно.
    """

    def __init__(self, max_results: int = 4000, extra_roots: Sequence[str] = ()) -> None:
        self._max_results = max_results
        self._extra_roots = tuple(extra_roots)

    def _candidates(self) -> list[Path]:
        if self._extra_roots:
            return [Path(r) for r in self._extra_roots]
        return _candidate_dirs()

    def _roots(self) -> list[Path]:
        roots: list[Path] = []
        for d in self._candidates():
            try:
                if d.is_dir():
                    roots.append(d.resolve())
            except OSError:
                continue
        return roots

    def _is_font_file(self, p: Path) -> bool:
        try:
            return p.is_file() and p.suffix.lower() in _FONT_EXTENSIONS
        except OSError:
            return False

    def _scan_root(self, root: Path, seen: dict[str, SystemFontFile]) -> None:
        try:
            for p in root.rglob("*"):
                if len(seen) >= self._max_results:
                    return
                key = p.name.lower()
                if key not in seen and self._is_font_file(p):
                    seen[key] = SystemFontFile(name=p.name, path=str(p), family=read_family_name(p) or "")
        except OSError:
            return

    async def list_fonts(self) -> list[SystemFontFile]:
        # В поток: обход дерева каталогов с открытием каждого файла ради имени
        # семейства — на реальном C:/Windows/Fonts это заметная пауза, и держать
        # на ней event loop нельзя.
        return await asyncio.to_thread(self._list_fonts_blocking)

    def _list_fonts_blocking(self) -> list[SystemFontFile]:
        seen: dict[str, SystemFontFile] = {}
        for root in self._roots():
            self._scan_root(root, seen)
        return sorted(seen.values(), key=lambda f: f.name.lower())

    async def source_dir(self) -> str | None:
        roots = await asyncio.to_thread(self._roots)
        return str(roots[0]) if roots else None

    async def read_font(self, path: str) -> bytes:
        p = Path(path).resolve()
        if p.suffix.lower() not in _FONT_EXTENSIONS:
            raise ValueError(f"not a font file: {path!r}")
        # Security: only allow reading files inside a known system font directory.
        if not any(_is_within(p, root) for root in self._roots()):
            raise ValueError(f"path is not inside a known system font directory: {path!r}")
        if not p.is_file():
            raise ValueError(f"system font not found: {path!r}")
        return p.read_bytes()
