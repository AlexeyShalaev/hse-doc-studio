"""Порт членства проекта: права актора берутся только из хранилища сервера."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, ProjectAcl, Role


class IProjectAclRepository(Protocol):
    async def load_for(self, actor: Actor, project_id: UUID) -> ProjectAcl | None:
        """Членство проекта для одного актора; None, если проекта нет или актор не участник.

        В `grants` лежит единственная запись: право самого актора. Поля team и shared_enabled
        берутся из БД, `project.json` источником прав не служит.
        """
        ...

    async def set_shared_enabled(self, project_id: UUID, enabled: bool) -> None:
        """Единственный путь записи флага общих документов: файл потом перезаписывается значением из БД."""
        ...


@dataclass(frozen=True)
class ProjectOwnerView:
    kind: Literal["user", "org"]
    id: str
    name: str
    slug: str | None


@dataclass(frozen=True)
class ProjectMembership:
    """Кто владеет проектом и какая роль у спросившего: данные карточки в списке проектов."""

    project_id: UUID
    owner: ProjectOwnerView
    my_role: Role


class IProjectMemberships(Protocol):
    async def memberships_for(self, actor: Actor, project_ids: Sequence[UUID]) -> dict[UUID, ProjectMembership]:
        """Владелец и роль актора для каждого из проектов; проекта, где актор не участник, в ответе нет."""
        ...
