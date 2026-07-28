from __future__ import annotations

from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository

logger = structlog.get_logger()


def describe_run_error(exc: BaseException) -> str:
    """Человекочитаемая причина падения рана.

    Уезжает в run.error и оттуда — терминальным событием в чат: пользователь
    должен видеть «модель не поддерживает инструменты», а не «BadRequestError».
    """
    name = type(exc).__name__
    detail = str(exc).strip()
    if not detail:
        return name
    return f"{name}: {detail[:400]}"


def find_project_folder(
    project_id: UUID,
    project_repo: IProjectRepository,
    project_index_repo: IProjectIndexRepository,
) -> Path | None:
    """Resolve a project_id to its on-disk folder by scanning the known index.

    Same approach the compile use cases use (GetCompileStreamUC._find_folder):
    the project file lives in a user-chosen folder, so we match by id over the
    registered folders rather than keeping a separate id→path map.
    """
    for folder in project_index_repo.list_known():
        try:
            project = project_repo.get(folder)
        except Exception as exc:
            logger.warning("chat: error loading project", folder=str(folder), exc=str(exc))
            continue
        if project is not None and project.id == project_id:
            return folder
    return None
