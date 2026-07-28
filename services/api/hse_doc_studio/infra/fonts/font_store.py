from __future__ import annotations

from pathlib import Path

import structlog

from hse_doc_studio.core.fonts.entities import InstalledFont
from hse_doc_studio.core.fonts.repositories import IFontStore
from hse_doc_studio.infra.fonts.font_names import read_family_name

logger = structlog.get_logger()

_DEFAULT_EXTENSIONS: frozenset[str] = frozenset({".ttf", ".otf", ".ttc"})


class LocalFontStore(IFontStore):
    """Filesystem-backed font store under `<data_dir>/fonts/`.

    Only font files (by extension) are listed/written; filenames are reduced to
    their basename on write/delete so a crafted path can never escape the folder.
    """

    def __init__(self, fonts_dir: Path, allowed_extensions: frozenset[str] = _DEFAULT_EXTENSIONS) -> None:
        self._fonts_dir = fonts_dir
        self._allowed = {e.lower() for e in allowed_extensions}

    @property
    def fonts_dir(self) -> Path:
        return self._fonts_dir

    def _is_font(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in self._allowed

    def list_fonts(self) -> list[InstalledFont]:
        if not self._fonts_dir.exists():
            return []
        fonts = [
            InstalledFont(name=p.name, size_bytes=p.stat().st_size, family=read_family_name(p) or "")
            for p in sorted(self._fonts_dir.iterdir())
            if self._is_font(p)
        ]
        return fonts

    def save_font(self, filename: str, content: bytes) -> InstalledFont:
        safe = Path(filename).name  # strip any directory components
        if not safe or Path(safe).suffix.lower() not in self._allowed:
            raise ValueError(f"unsupported font file: {filename!r} (allowed: {sorted(self._allowed)})")
        self._fonts_dir.mkdir(parents=True, exist_ok=True)
        target = self._fonts_dir / safe
        target.write_bytes(content)
        logger.info("font saved", name=safe, size=len(content))
        return InstalledFont(name=safe, size_bytes=len(content), family=read_family_name(target) or "")

    def delete_font(self, filename: str) -> bool:
        safe = Path(filename).name
        target = self._fonts_dir / safe
        if self._is_font(target):
            target.unlink()
            logger.info("font deleted", name=safe)
            return True
        return False

    def read_font(self, filename: str) -> bytes | None:
        safe = Path(filename).name  # never escape the fonts dir
        target = self._fonts_dir / safe
        if self._is_font(target):
            return target.read_bytes()
        return None

    def has_fonts(self) -> bool:
        if not self._fonts_dir.exists():
            return False
        return any(self._is_font(p) for p in self._fonts_dir.iterdir())
