"""Куда документы проекта выпускают результат: тот же резолв, что у списка и карточки документа."""

from __future__ import annotations

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.services import ProjectTemplateService

logger = structlog.get_logger()


class DocumentOutputs:
    """Путь результата каждого документа от корня проекта, без повторного чтения проекта на каждый документ.

    Шаблонный документ выпускает файл выбранного варианта (`tz/tz.pdf`, `presentation/presentation.pptx`),
    загруженный свой файл и есть результат. `None`: определения документа в установленном паке нет.
    """

    def __init__(self, template_repo: ITemplateRepository | None) -> None:
        self._template_repo = template_repo
        self._service = ProjectTemplateService()

    def of(self, project: Project) -> dict[str, str | None]:
        lock = project.lock
        version = (
            self._template_repo.get_version(lock.pack_id, lock.template_id, lock.version)
            if self._template_repo is not None
            else None
        )
        return {doc.id: self._output(project, doc, version) for doc in project.documents}

    def _output(self, project: Project, doc: Document, version: TemplateVersion | None) -> str | None:
        if doc.custom_file is not None:
            return doc.custom_file.stored_path
        if version is None:
            return None
        try:
            return self._service.resolve_instance_source(project, doc, version)[1]
        except (ValueError, NotFoundError):
            logger.warning("document output unresolved", doc_id=doc.id)
            return None
