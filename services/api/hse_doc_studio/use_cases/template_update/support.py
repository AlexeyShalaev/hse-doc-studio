"""Общие шаги обновления и отмены: lock проекта, история до обновления."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsCommitKind, VcsTagKind
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.template_update.protocols import ITemplateBaseStore
from hse_doc_studio.core.value_objects import ProjectLock
from hse_doc_studio.core.vcs.constants import vcs_exclude_for
from hse_doc_studio.core.vcs.errors import VcsCommandError
from hse_doc_studio.core.vcs.protocols import IVcsService

logger = structlog.get_logger()


def lock_for(lock: ProjectLock, version: TemplateVersion, template_repo: ITemplateRepository) -> ProjectLock:
    """lock проекта на версии `version`: номер, дайджест содержимого, min_studio."""
    return replace(
        lock,
        version=version.version,
        digest=template_repo.content_digest(version.pack_id, version.template_id, version.version),
        min_studio=version.min_studio,
    )


def ensure_history(vcs: IVcsService, project: Project, version: TemplateVersion) -> None:
    """Обновлению нужна история: снимок до него и коммит самого обновления.

    Заодно освежает исключения (журнал обновления `.hse-studio/update/` не должен
    попасть в коммит у проекта, чья история создана старой Студией).
    """
    if vcs.is_initialized(project):
        vcs.write_ignore(project, vcs_exclude_for(version))
    else:
        vcs.init(project, vcs_exclude_for(version))


def pre_update_snapshot(vcs: IVcsService, base_store: ITemplateBaseStore, project: Project, label: str) -> str:
    """Снимок проекта до обновления (или текущий HEAD, если менять нечего) + тег."""
    commit = vcs.commit(project, message=f"Снимок перед: {label}", kind=VcsCommitKind.manual)
    head = commit.id if commit is not None else base_store.head(project)
    if head is None:
        raise VcsCommandError("commit", "project history has no commits")
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        vcs.create_tag(project, name=f"pre-template-update-{stamp}", commit_id=head, kind=VcsTagKind.tag)
    except VcsCommandError as exc:
        # Тег — закладка для человека; без него откат всё равно возможен.
        logger.warning("pre-update tag not created", exc=str(exc))
    return head
