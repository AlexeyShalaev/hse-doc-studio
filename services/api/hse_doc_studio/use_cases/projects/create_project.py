from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.catalog import DocumentDefinition, TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import (
    DocumentStatus,
    EngineType,
    Lang,
    ProjectKind,
    ProjectStaffing,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.meta_defaults import apply_meta_defaults
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.team import doc_instance_id, normalize_team_authors, project_bases
from hse_doc_studio.core.value_objects import (
    Author,
    ChecksOverride,
    Person,
    ProjectLock,
)
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.infra.project_init.template_renderer import (
    TemplateRenderer,
    instantiate_base,
    instantiate_nda,
    regenerate_dynamic_includes,
)

logger = structlog.get_logger()


@dataclass
class CreateProjectInput:
    folder: Path
    pack_id: str
    template_id: str
    version: str
    name: str
    kind: ProjectKind
    staffing: ProjectStaffing
    lang: Lang
    engine: EngineType
    authors: list[Author]
    supervisor: Person | None
    co_supervisor: Person | None
    meta: dict[str, Any]
    academic_supervisor: Person | None = None
    pres_variant: str | None = None
    # Team mode: вести ли общие (shared) документы в этом проекте.
    shared_enabled: bool = True


@dataclass
class CreateProjectOutput:
    project: Project


class CreateProjectUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        template_renderer: TemplateRenderer,
        vcs_service: IVcsService,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._template_renderer = template_renderer
        self._vcs = vcs_service

    async def execute(self, inp: CreateProjectInput) -> CreateProjectOutput:
        folder = inp.folder.expanduser().resolve()

        # 1. Папка обязана быть пустой и незарегистрированной. САМУ папку создаём
        # ниже, уже после проверок шаблона: отказ не должен оставлять на диске
        # пустой каталог, который потом мешает повторному созданию.
        _validate_folder_free(folder, self._project_index_repo.list_known())

        # 2. Get TemplateVersion
        template_version = self._template_repo.get_version(inp.pack_id, inp.template_id, inp.version)
        if template_version is None:
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена: {inp.pack_id}/{inp.template_id}/{inp.version}",
                    f"Template version not found: {inp.pack_id}/{inp.template_id}/{inp.version}",
                )
            )

        # 2a. Team mode: шаблон обязан объявлять поддержку, авторов ≥ 2,
        # у каждого — валидный уникальный слаг (выводится из фамилии).
        authors = _validate_team_authors(inp, template_version)
        _validate_lang(inp, template_version)

        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            logger.debug("created project folder", folder=str(folder))

        # 3. Build documents from template definitions
        documents = _build_documents(
            template_version,
            inp.pres_variant,
            staffing=inp.staffing,
            authors=authors,
            shared_enabled=inp.shared_enabled,
            kind=inp.kind,
        )

        # 4. Create Project aggregate
        now = datetime.now(tz=timezone.utc)
        # Materialise template defaults / computed `auto` values (e.g. degree type,
        # educational programme, defense year) for any meta field the caller left
        # blank, so the compiled PDF carries sensible values even when the client
        # sends nothing. Values the caller did supply are preserved verbatim.
        effective_meta = apply_meta_defaults(template_version, inp.meta, now.date())
        project = Project(
            id=uuid.uuid4(),
            name=inp.name,
            folder=folder,
            lock=ProjectLock(
                pack_id=inp.pack_id,
                template_id=inp.template_id,
                version=inp.version,
                engine=inp.engine,
            ),
            kind=inp.kind,
            staffing=inp.staffing,
            lang=inp.lang,
            authors=authors,
            meta=effective_meta,
            supervisor=inp.supervisor,
            co_supervisor=inp.co_supervisor,
            academic_supervisor=inp.academic_supervisor,
            documents=documents,
            created_at=now,
            updated_at=now,
            shared_enabled=inp.shared_enabled,
        )

        # 5. Save project metadata
        self._project_repo.save(project)

        # 6. Register in index
        self._project_index_repo.register(folder)

        # 7. Copy template files
        _render_template_files(
            template_version=template_version,
            template_repo=self._template_repo,
            renderer=self._template_renderer,
            project=project,
        )

        # 8. Initialize the isolated VCS store (.hse-studio/git/) with a root
        # snapshot of the freshly seeded files. Best-effort: a VCS failure must
        # never block project creation.
        try:
            if self._vcs.is_available(project):
                await asyncio.to_thread(self._vcs.init, project, list(DEFAULT_VCS_EXCLUDE))
        except Exception as exc:  # noqa: BLE001
            logger.warning("vcs init failed on create", project_id=str(project.id), exc=str(exc))

        logger.info(
            "project created",
            project_id=str(project.id),
            folder=str(folder),
        )
        return CreateProjectOutput(project=project)


def _validate_folder_free(folder: Path, known: list[Path]) -> None:
    """Папка годится под новый проект: пуста (или отсутствует) и не в реестре."""
    if folder.exists() and any(not f.name.startswith(".") for f in folder.iterdir()):
        raise ValueError(
            localized_error(
                f"Папка '{folder}' не пуста. Используйте подключение существующего проекта.",
                f"Folder '{folder}' is not empty. Use connect instead.",
            )
        )
    if folder in [p.resolve() for p in known]:
        raise ValueError(
            localized_error(f"Папка '{folder}' уже зарегистрирована.", f"Folder '{folder}' is already registered.")
        )


def _validate_lang(inp: CreateProjectInput, template_version: TemplateVersion) -> None:
    """Язык проекта обязан входить в объявленные шаблоном `langs:`.

    Раньше это не проверялось, и Project Proposal (по регламенту ОП — только
    английский) спокойно создавался с lang=ru: файлы приезжали по фолбэку
    английскими, а проверки и интерфейс считали проект русским. Симметрично
    проверке командного режима выше.
    """
    if not template_version.langs:
        # v1-раскладка без объявленных языков — гейтить нечем.
        return
    if inp.lang.value not in template_version.langs:
        declared = ", ".join(template_version.langs)
        raise ValueError(
            localized_error(
                f"Шаблон {inp.pack_id}/{inp.template_id}@{inp.version} не поддерживает язык "
                f"«{inp.lang.value}» (доступно: {declared})",
                f"Template {inp.pack_id}/{inp.template_id}@{inp.version} does not support language "
                f"'{inp.lang.value}' (available: {declared})",
            )
        )


def _validate_team_authors(inp: CreateProjectInput, template_version: TemplateVersion) -> list[Author]:
    """Solo — авторы как есть; team — гарантирует поддержку пака, ≥2 авторов
    и валидные уникальные слаги (выводятся транслитом фамилии).

    Нормализация терпима к черновикам (пустое имя → slug=None, managed=False —
    так живёт автосейв настроек), но ПРИ СОЗДАНИИ ведомый автор без слага —
    ошибка: его комплект молча не материализовался бы.
    """
    if inp.staffing != ProjectStaffing.team:
        return inp.authors
    if "team" not in template_version.supported_staffing:
        raise ValueError(
            localized_error(
                f"Шаблон {inp.pack_id}/{inp.template_id}@{inp.version} не поддерживает командный режим",
                f"Template {inp.pack_id}/{inp.template_id}@{inp.version} does not support team mode",
            )
        )
    if len(inp.authors) < 2:
        raise ValueError(
            localized_error(
                "Командный проект требует минимум двух авторов",
                "A team project requires at least two authors",
            )
        )
    normalized = normalize_team_authors(inp.authors)
    for original, author in zip(inp.authors, normalized, strict=True):
        if original.managed and not author.slug:
            raise ValueError(
                localized_error(
                    f"Не удалось вывести слаг папки для автора {original.name!r} — укажите ФИО или слаг явно",
                    f"Could not derive a folder slug for author {original.name!r} — "
                    f"specify the full name or slug explicitly",
                )
            )
    return normalized


def _build_documents(  # noqa: C901
    template_version: TemplateVersion,
    pres_variant: str | None,
    staffing: ProjectStaffing,
    authors: list[Author],
    shared_enabled: bool,
    kind: ProjectKind,
) -> list[Document]:
    """Инстансы документов: solo — по одному на определение (id == def id);
    team — scope=personal размножается на каждого ведомого автора
    (id "{def}--{slug}"), scope=shared — один экземпляр в shared-базе.

    Документы, чей формат (`supported_kinds`) не включает выбранный `kind`,
    не инстанцируются вовсе — так проектный формат получает ЕСПД-комплект, а
    исследовательский — Аннотацию вместо ТЗ и без софт-документации."""
    team = staffing == ProjectStaffing.team
    documents: list[Document] = []
    for doc_def in template_version.documents:
        if kind.value not in doc_def.supported_kinds:
            continue
        chosen_variant = _resolve_variant(doc_def, pres_variant)
        if not team:
            if "solo" in doc_def.supported_staffing:
                documents.append(_make_instance(doc_def.id, doc_def.id, None, chosen_variant))
            continue
        if "team" not in doc_def.supported_staffing:
            continue
        if doc_def.scope == "personal":
            documents.extend(
                _make_instance(doc_instance_id(doc_def.id, a.slug), doc_def.id, a.slug, chosen_variant)
                for a in authors
                if a.managed and a.slug
            )
        elif shared_enabled:
            documents.append(_make_instance(doc_def.id, doc_def.id, None, chosen_variant))
    return documents


def _resolve_variant(doc_def: DocumentDefinition, pres_variant: str | None) -> str | None:
    if not doc_def.variants:
        return None
    if pres_variant and doc_def.id == "presentation":
        variant_ids = [v.id for v in doc_def.variants]
        return pres_variant if pres_variant in variant_ids else doc_def.variants[0].id
    return doc_def.variants[0].id


def _make_instance(instance_id: str, def_id: str, owner: str | None, chosen_variant: str | None) -> Document:
    return Document(
        id=instance_id,
        status=DocumentStatus.draft,
        chosen_variant=chosen_variant,
        last_compile_id=None,
        checks_override=ChecksOverride(),
        def_id=def_id,
        owner=owner,
    )


def _render_template_files(
    template_version: TemplateVersion,
    template_repo: ITemplateRepository,
    renderer: TemplateRenderer,
    project: Project,
) -> None:
    """Материализация файлов пака: solo — одна база (корень проекта, как
    раньше); team — по базе на shared/ и папку каждого ведомого автора, каждая
    со своим Jinja-контекстом (тема/меты владельца). Копируются каталоги ВСЕХ
    вариантов документов — выбранный вариант лишь указывает, что собирать,
    смена варианта в настройках lossless. NDA остаётся корневым и
    условным, dynamic includes генерятся после копирования (по всем базам)."""
    for base_dir, author in project_bases(project):
        instantiate_base(
            project=project,
            version=template_version,
            template_repo=template_repo,
            renderer=renderer,
            base_dir=base_dir,
            author=author,
        )

    # Generate the dynamic includes once now so the project compiles immediately
    # after creation; trigger_compile regenerates them on every subsequent build.
    regenerate_dynamic_includes(project, template_version, template_repo)

    # Materialise the NDA file group if the project is marked NDA (no-op otherwise).
    instantiate_nda(project, template_version, template_repo)
