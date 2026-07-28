from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Document
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.team import author_by_slug, is_doc_active
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class ListDocumentsInput:
    project_id: UUID


@dataclass
class DocumentListEntry:
    """Документ + резолв инстанса для фронтенда.

    Пути — от корня проекта (team: с префиксом базы владельца); фронтенд
    перестаёт выводить их из doc_id («{id}/{id}.tex» больше не работает для
    инстансов). `owner_name` — ФИО владельца для подписи в навигации.
    `name`/`code` — локализованные имя и код ОПРЕДЕЛЕНИЯ из пака: пак —
    единственный источник правды для новых типов доков (tz_shared), фронтовый
    i18n-словарь — лишь фолбэк.
    """

    document: Document
    source_file: str | None = None
    output_file: str | None = None
    owner_name: str | None = None
    name: dict[str, str] | None = None
    code: dict[str, str] | None = None
    # Движок выбранного варианта (None — copy-only вариант pptx/reveal);
    # для доков без вариантов — движок из lock проекта.
    engine: str | None = None
    # Визуальный блок из определения пака — фронтенд рисует дивайдер между
    # соседними доками разных групп.
    group: str | None = None


@dataclass
class ListDocumentsOutput:
    documents: list[Document]
    entries: list[DocumentListEntry]


class ListDocumentsUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository | None = None,
    ) -> None:
        self._template_repo = template_repo
        self._template_service = ProjectTemplateService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: ListDocumentsInput) -> ListDocumentsOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project
        version = (
            self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
            if self._template_repo is not None
            else None
        )
        # Неактивные руководства (РП/РО, не выбранные владельцем в «Составе
        # документов») скрыты из IDE — но остаются в project.documents на диске,
        # чтобы при повторном выборе вернуть содержимое.
        visible_docs = [doc for doc in project.documents if is_doc_active(project, doc)]
        # Порядок = roster текущей версии пака, а не порядок инстанцирования в
        # project.json (он зафиксирован при создании и после переупорядочивания
        # roster в паке устаревает — визуальные блоки group рвались бы).
        # Стабильная сортировка сохраняет порядок авторов внутри одного def;
        # доки без определения в текущем паке уходят в конец без перестановок.
        if version is not None:
            roster_index = {d.id: i for i, d in enumerate(version.documents)}
            fallback = len(roster_index)
            visible_docs.sort(key=lambda doc: roster_index.get(doc.def_id or doc.id, fallback))
        entries: list[DocumentListEntry] = []
        for doc in visible_docs:
            source_file: str | None = None
            output_file: str | None = None
            doc_def = None
            if version is not None:
                doc_def = self._template_service.find_definition(version, doc)
                try:
                    source_file, output_file = self._template_service.resolve_instance_source(project, doc, version)
                except (ValueError, NotFoundError):
                    logger.warning("list_documents: cannot resolve instance source", doc_id=doc.id)
            if doc.custom_file is not None:
                # Кастомный файл замещает и source_file, и output_file целиком —
                # шаблонный резолв выше игнорируется (иначе «Скачать»/подписание
                # уйдут на устаревший шаблонный путь).
                source_file = doc.custom_file.stored_path
                output_file = doc.custom_file.stored_path
            owner = author_by_slug(project, doc.owner)
            engine = self._template_service.resolve_document_engine(doc_def, doc.chosen_variant, project.lock.engine)
            entries.append(
                DocumentListEntry(
                    document=doc,
                    source_file=source_file,
                    output_file=output_file,
                    owner_name=owner.name if owner is not None else None,
                    name=dict(doc_def.name) if doc_def is not None else None,
                    code=dict(doc_def.code) if doc_def is not None else None,
                    engine=str(engine) if engine is not None else None,
                    group=doc_def.group if doc_def is not None else None,
                )
            )
        return ListDocumentsOutput(documents=visible_docs, entries=entries)
