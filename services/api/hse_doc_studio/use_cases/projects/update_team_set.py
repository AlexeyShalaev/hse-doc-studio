from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import DocumentDefinition, TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import DocumentStatus, ProjectStaffing, VcsCommitKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.team import (
    SHARED_DIR,
    author_by_slug,
    doc_instance_id,
)
from hse_doc_studio.core.value_objects import Author, ChecksOverride
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.infra.project_init.template_renderer import (
    TemplateRenderer,
    instantiate_base,
    instantiate_missing_base_parts,
    regenerate_dynamic_includes,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class UpdateTeamSetInput:
    project_id: UUID
    # Слаг автора, чей комплект включаем/выключаем; None — общие (shared) доки.
    author_slug: str | None
    enabled: bool


@dataclass
class UpdateTeamSetOutput:
    project: Project


class UpdateTeamSetUC:
    """Довключение/выключение комплекта документов ПОСЛЕ создания проекта.

    Включение: помечает автора managed (или shared_enabled), материализует
    базу из пака, ЕСЛИ её ещё нет на диске (существующая база не трогается —
    правки не клобберятся), регистрирует инстансы документов и перегенерирует
    dynamic includes. Выключение НЕ удаляет файлы — только дерегистрирует
    документы (комплект пропадает из навигации/сборки/сдачи); страховка —
    VCS-снапшот до и после изменения состава.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_renderer: TemplateRenderer,
        vcs_service: IVcsService,
    ) -> None:
        self._project_repo = project_repo
        self._template_repo = template_repo
        self._template_renderer = template_renderer
        self._vcs = vcs_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UpdateTeamSetInput) -> UpdateTeamSetOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        if project.staffing != ProjectStaffing.team:
            raise ValueError(
                localized_error(
                    "Управление комплектами доступно только в командных проектах",
                    "Managing document sets is only available in team projects",
                )
            )

        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            raise NotFoundError(localized_error("Версия шаблона не найдена", "Template version not found"))

        author: Author | None = None
        if inp.author_slug is not None:
            author = author_by_slug(project, inp.author_slug)
            if author is None or not author.slug:
                raise NotFoundError(
                    localized_error(
                        f"Автор со слагом {inp.author_slug!r} не найден в проекте",
                        f"Author with slug {inp.author_slug!r} not found in the project",
                    )
                )

        if inp.enabled:
            await asyncio.to_thread(self._enable, project, version, author)
        else:
            self._disable(project, inp.author_slug)

        # Обновляем флаги состава.
        if author is not None:
            project.authors = [replace(a, managed=inp.enabled) if a.slug == author.slug else a for a in project.authors]
        else:
            project.shared_enabled = inp.enabled

        project.updated_at = datetime.now(tz=timezone.utc)
        self._project_repo.save(project)

        # Страховочный снапшот: и включение, и выключение восстановимы через
        # «Версии». Best-effort — сбой VCS не блокирует операцию.
        await self._snapshot(project, author, enabled=inp.enabled)

        logger.info(
            "team set updated",
            project_id=str(project.id),
            author_slug=inp.author_slug,
            enabled=inp.enabled,
        )
        return UpdateTeamSetOutput(project=project)

    async def _snapshot(self, project: Project, author: Author | None, *, enabled: bool) -> None:
        try:
            if self._vcs.is_available(project) and self._vcs.is_initialized(project):
                label = "общих документов" if author is None else f"комплекта {author.name}"
                action = "Включение" if enabled else "Выключение"
                await asyncio.to_thread(
                    self._vcs.commit,
                    project,
                    message=f"{action} {label}",
                    kind=VcsCommitKind.manual,
                    allow_empty=True,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("team set vcs snapshot failed", project_id=str(project.id), exc=str(exc))

    # ------------------------------------------------------------------ enable

    def _enable(self, project: Project, version: TemplateVersion, author: Author | None) -> None:
        base_dir = author.slug if author is not None and author.slug else SHARED_DIR
        base_path = project.folder / base_dir
        if not base_path.exists():
            # Свежая база — материализуем из пака. Существующую НЕ трогаем:
            # render_and_copy перезаписал бы правки студента.
            instantiate_base(
                project=project,
                version=version,
                template_repo=self._template_repo,
                renderer=self._template_renderer,
                base_dir=base_dir,
                author=author,
            )
        else:
            # База уже есть: точечно докладываем каталоги доков, появившихся
            # в паке после её материализации (существующие файлы не трогаем).
            instantiate_missing_base_parts(
                project=project,
                version=version,
                template_repo=self._template_repo,
                renderer=self._template_renderer,
                base_dir=base_dir,
                author=author,
            )

        existing_ids = {d.id for d in project.documents}
        for doc_def in version.documents:
            if not self._def_belongs(doc_def, author):
                continue
            owner = author.slug if author is not None else None
            instance_id = doc_instance_id(doc_def.id, owner)
            if instance_id in existing_ids:
                continue
            chosen = self._inherit_variant(project, doc_def)
            project.documents.append(
                Document(
                    id=instance_id,
                    status=DocumentStatus.draft,
                    chosen_variant=chosen,
                    last_compile_id=None,
                    checks_override=ChecksOverride(),
                    def_id=doc_def.id,
                    owner=owner,
                )
            )

        # meta.tex/fonts.tex новой базы: managed-флаг ещё не выставлен, поэтому
        # временно включаем его в копии проекта для перегенерации.
        preview = replace_project_flags(project, author, enabled=True)
        regenerate_dynamic_includes(preview, version, self._template_repo)

    @staticmethod
    def _def_belongs(doc_def: DocumentDefinition, author: Author | None) -> bool:
        if "team" not in doc_def.supported_staffing:
            return False
        return (doc_def.scope == "personal") == (author is not None)

    @staticmethod
    def _inherit_variant(project: Project, doc_def: DocumentDefinition) -> str | None:
        if not doc_def.variants:
            return None
        existing = next((d.chosen_variant for d in project.documents if d.def_id == doc_def.id), None)
        return existing or doc_def.variants[0].id

    # ------------------------------------------------------------------ disable

    @staticmethod
    def _disable(project: Project, author_slug: str | None) -> None:
        if author_slug is not None:
            project.documents[:] = [d for d in project.documents if d.owner != author_slug]
        else:
            # Общие доки — инстансы без владельца.
            project.documents[:] = [d for d in project.documents if d.owner is not None]


def replace_project_flags(project: Project, author: Author | None, *, enabled: bool) -> Project:
    """Лёгкая копия проекта с уже применённым managed/shared_enabled флагом.

    Нужна, чтобы project_bases() увидел включаемую базу ДО сохранения проекта.
    """
    preview = copy.copy(project)
    if author is not None:
        preview.authors = [replace(a, managed=enabled) if a.slug == author.slug else a for a in project.authors]
    else:
        preview.shared_enabled = enabled
    return preview
