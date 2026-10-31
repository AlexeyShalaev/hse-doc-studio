from __future__ import annotations

from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.artifacts.entities import ArtifactKind, ProjectArtifact


class IProjectArtifactRepository(Protocol):
    async def add(self, artifact: ProjectArtifact) -> None: ...

    async def get(self, project_id: UUID, artifact_id: UUID) -> ProjectArtifact | None: ...

    async def latest(self, project_id: UUID, doc_id: str, kind: ArtifactKind) -> ProjectArtifact | None:
        """Самая свежая выгрузка документа; нужна, чтобы повтор того же файла не плодил записи."""
        ...

    async def list_for_project(self, project_id: UUID, *, doc_id: str | None = None) -> list[ProjectArtifact]:
        """От новых к старым."""
        ...

    async def delete(self, project_id: UUID, artifact_id: UUID) -> ProjectArtifact | None:
        """Удаляет запись и возвращает её (ключ объекта нужен вызывающему); None, если записи нет."""
        ...

    async def prune(self, project_id: UUID, doc_id: str, kind: ArtifactKind, *, keep: int) -> list[ProjectArtifact]:
        """Удаляет записи документа старше `keep` последних и возвращает их."""
        ...
