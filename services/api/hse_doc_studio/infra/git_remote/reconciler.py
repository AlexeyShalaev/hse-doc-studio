"""После push: права из БД обратно в project.json и копия name/kind/lang в каталоге проектов."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.repositories import IProjectRepository
from hse_doc_studio.infra.projects.catalog_sync import MirroringProjectRepository, ProjectCatalogMirror


class ExternalChangeReconciler:
    def __init__(self, projects: IProjectRepository, mirror: ProjectCatalogMirror) -> None:
        self._projects = projects
        self._mirror = mirror

    async def after_external_change(self, project_id: UUID, folder: Path, *, project_json_changed: bool) -> None:
        if not project_json_changed:
            return
        if isinstance(self._projects, MirroringProjectRepository):
            # team и shared_enabled живут в БД: присланный project.json их не меняет (как после git-синхронизации).
            await asyncio.to_thread(self._projects.enforce_acl, folder)
        project = await asyncio.to_thread(self._projects.get, folder)
        if project is not None:
            await self._mirror.mirror(project_id, project)
