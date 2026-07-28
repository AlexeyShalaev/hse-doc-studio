from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Document
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class GetDocumentInput:
    project_id: UUID
    doc_id: str


@dataclass
class GetDocumentOutput:
    document: Document
    # Резолв определения/инстанса — как в ListDocumentsUC (DocumentListEntry):
    # локализованные имя/код определения из пака, пути от корня проекта
    # (team: с префиксом базы владельца) и ГОСТ-ссылка. Фронтенд обязан
    # использовать их вместо вывода из doc_id.
    name: dict[str, str] | None = None
    code: dict[str, str] | None = None
    source_file: str | None = None
    output_file: str | None = None
    gost_ref: str | None = None
    # Движок выбранного варианта (None — copy-only вариант pptx/reveal);
    # для доков без вариантов — движок из lock проекта.
    engine: str | None = None
    # PDF-предпросмотр не-PDF артефакта (pptx → соседний .pdf, генерируется
    # Gotenberg'ом на сборке и после сохранений из office-редактора). None —
    # предпросмотра нет, фронт показывает карточку скачивания.
    preview_file: str | None = None
    # mtime предпросмотра: колбэк OnlyOffice переконвертирует PDF без новой
    # компиляции, так что last_compile_id не меняется — фронт освежает вьювер
    # по этой метке.
    preview_updated_at: datetime | None = None
    # Есть ли на диске sibling PDF-превью кастомного файла (для конвертируемых
    # office-форматов). Вычисляется заново на каждый GET, не персистится.
    custom_preview_available: bool = False
    # True, если подписание возможно: custom_file не задан (обычный шаблонный
    # док), ИЛИ custom_file.ext == ".pdf", ИЛИ существует sibling-превью.
    # Не блокирует ничего — чисто сигнал для UI.
    signing_available: bool = True


class GetDocumentUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository | None = None,
    ) -> None:
        self._template_repo = template_repo
        self._template_service = ProjectTemplateService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    @staticmethod
    def _sibling_pdf_preview(project_folder: Path, output_rel_path: str) -> tuple[str | None, datetime | None]:
        """(preview_file, preview_updated_at) для sibling `.pdf` рядом с
        не-PDF артефактом (pptx-вариант ИЛИ кастомный office-файл) —
        сгенерированного конвертацией на сборке/аплоаде/office-редакторе.
        None — предпросмотра нет на диске.
        """
        if output_rel_path.lower().endswith(".pdf"):
            return None, None
        candidate = str(PurePosixPath(output_rel_path).with_suffix(".pdf"))
        candidate_abs = project_folder / candidate
        if not candidate_abs.is_file():
            return None, None
        try:
            return candidate, datetime.fromtimestamp(candidate_abs.stat().st_mtime, tz=UTC)
        except OSError:
            logger.warning("get_document: cannot stat preview file", path=str(candidate_abs))
            return candidate, None

    async def execute(self, inp: GetDocumentInput) -> GetDocumentOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    f"Документ {inp.doc_id!r} не найден в проекте {inp.project_id}",
                    f"Document '{inp.doc_id}' not found in project {inp.project_id}",
                )
            )

        version = (
            self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
            if self._template_repo is not None
            else None
        )
        source_file: str | None = None
        output_file: str | None = None
        doc_def = None
        if version is not None:
            doc_def = self._template_service.find_definition(version, doc)
            try:
                source_file, output_file = self._template_service.resolve_instance_source(project, doc, version)
            except (ValueError, NotFoundError):
                logger.warning("get_document: cannot resolve instance source", doc_id=doc.id)
        engine = self._template_service.resolve_document_engine(doc_def, doc.chosen_variant, project.lock.engine)

        preview_file: str | None = None
        preview_updated_at: datetime | None = None
        custom_preview_available = False
        signing_available = True

        if doc.custom_file is not None:
            # Кастомный файл замещает source_file/output_file/chosen_variant
            # целиком для IDE/preview/signing — шаблонный резолв выше
            # игнорируется (иначе «Скачать»/подписание уйдут на устаревший
            # шаблонный путь).
            source_file = doc.custom_file.stored_path
            output_file = doc.custom_file.stored_path
            if doc.custom_file.ext == ".pdf":
                preview_file = doc.custom_file.stored_path
            else:
                preview_file, preview_updated_at = self._sibling_pdf_preview(
                    project.folder, doc.custom_file.stored_path
                )
            custom_preview_available = preview_file is not None
            signing_available = doc.custom_file.ext == ".pdf" or custom_preview_available
        elif output_file is not None:
            # Не-PDF артефакт (pptx) может иметь соседний PDF-предпросмотр,
            # сгенерированный конвертацией на сборке (TriggerCompileUC) или
            # после сохранения из office-редактора (OfficeEditorCallbackUC).
            preview_file, preview_updated_at = self._sibling_pdf_preview(project.folder, output_file)

        return GetDocumentOutput(
            document=doc,
            name=dict(doc_def.name) if doc_def is not None else None,
            code=dict(doc_def.code) if doc_def is not None else None,
            source_file=source_file,
            output_file=output_file,
            gost_ref=doc_def.gost_ref if doc_def is not None else None,
            engine=str(engine) if engine is not None else None,
            preview_file=preview_file,
            preview_updated_at=preview_updated_at,
            custom_preview_available=custom_preview_available,
            signing_available=signing_available,
        )
