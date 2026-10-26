from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

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


class IOfficeConvertService(Protocol):
    # Конвертация офисного файла в PDF (Gotenberg): только то, что нужно
    # use cases. Статус и жизненный цикл контейнера остаются на менеджере.
    async def convert_to_pdf(self, source: Path, image: str | None = None) -> bytes | None: ...


class IOfficeEditorService(Protocol):
    # Редактор документов (ONLYOFFICE Document Server): конфиг, колбэк, keepalive.
    @property
    def base_url(self) -> str | None: ...

    @property
    def jwt_secret(self) -> str: ...

    async def is_image_missing(self, image: str | None = None) -> bool: ...

    async def ensure_running(self, image: str | None = None) -> str | None: ...

    async def apply_ai_settings(self, desired: dict[str, Any]) -> bool: ...

    def mark_active(self, key: str) -> None: ...

    def mark_closed(self, key: str) -> None: ...

    def touch(self) -> None: ...


class IBackendReachability(Protocol):
    # Как соседний контейнер достучится до ЭТОГО бэкенда (скачать документ,
    # отдать save-колбэк): адрес зависит от рантайма, поэтому async.
    async def base_url(self) -> str: ...
