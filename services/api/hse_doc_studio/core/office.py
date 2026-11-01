from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from hse_doc_studio.core.catalog import SubmissionDocItem
from hse_doc_studio.core.entities import Project

# Office formats Gotenberg/LibreOffice can convert to PDF — shared by the
# compile pipeline (pptx/office preview) and the packaging preflight/planner
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

    def base_url_for(self, key: str) -> str | None:
        """Адрес редактора для документа с этим ключом: у пула реплика определяется ключом (липкая)."""
        ...

    @property
    def session_limit(self) -> int | None:
        """Сколько сессий редактирования допускает установка; None, когда лимита нет (локальный контейнер)."""
        ...

    def try_open_session(self, key: str, doc_id: str | None = None) -> bool:
        """Занять место под сессию редактирования; False, когда установка исчерпала лимит одновременных сессий."""
        ...

    def mark_active(self, key: str) -> None: ...

    def mark_closed(self, key: str) -> None: ...

    def touch(self, doc_id: str | None = None) -> None: ...


class IBackendReachability(Protocol):
    # Как соседний контейнер достучится до ЭТОГО бэкенда (скачать документ,
    # отдать save-колбэк): адрес зависит от рантайма, поэтому async.
    async def base_url(self) -> str: ...


def sibling_pdf_path(path: str) -> str:
    """Путь PDF-превью рядом с office-файлом: та же папка и имя, суффикс `.pdf`."""
    return str(PurePosixPath(path).with_suffix(".pdf"))


def resolve_custom_doc_decision(doc_id: str, remembered: bool | None, decisions: dict[str, bool] | None) -> bool | None:
    """Конвертировать ли custom-файл в PDF: явное решение, иначе запомненное."""
    if decisions is not None and doc_id in decisions:
        return decisions[doc_id]
    return remembered


@dataclass(frozen=True)
class ConvertRequest:
    """Что надо сконвертировать перед сборкой пакета: путь исходника и путь его PDF."""

    doc_id: str
    stored_path: str
    output_path: str


def custom_docs_to_convert(
    project: Project,
    doc_items: Iterable[SubmissionDocItem],
    decisions: dict[str, bool] | None,
    is_file: Callable[[str], bool],
) -> list[ConvertRequest]:
    """Документы пакета, которым нужна конвертация custom-файла, в порядке `doc_items`.

    Единственное место, где решается «нужна ли конвертация»: custom-файл
    конвертируемого не-PDF формата, решение «конвертировать», исходник на месте,
    а PDF рядом ещё нет (готовый PDF переиспользуется как есть, даже устаревший).
    `is_file` получает путь от корня проекта.
    """
    requests: list[ConvertRequest] = []
    seen: set[str] = set()
    for item in doc_items:
        doc = next((d for d in project.documents if d.id == item.doc_id), None)
        custom_file = doc.custom_file if doc is not None else None
        if doc is None or custom_file is None:
            continue
        if custom_file.ext not in CONVERTIBLE_OFFICE_EXTS:
            continue
        if not resolve_custom_doc_decision(doc.id, custom_file.convert_to_pdf_at_package, decisions):
            continue
        output_path = sibling_pdf_path(custom_file.stored_path)
        if output_path in seen or is_file(output_path) or not is_file(custom_file.stored_path):
            continue
        seen.add(output_path)
        requests.append(ConvertRequest(doc_id=doc.id, stored_path=custom_file.stored_path, output_path=output_path))
    return requests
