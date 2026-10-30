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


@dataclass(frozen=True)
class ProjectOwnership:
    """Кому принадлежит проект: ровно одно из двух полей заполнено."""

    owner_user_id: str | None
    owner_org_id: str | None


@dataclass(frozen=True)
class ProjectMemberGrant:
    """Запись участника проекта: человек или группа и его роль (владелец записью не назначается)."""

    principal_kind: Literal["user", "group"]
    principal_id: str
    role: Role
    persona: str | None = None
    can_share: bool = False
    show_sources: bool = True
    can_edit_all: bool = False


@dataclass(frozen=True)
class ProjectMemberView:
    grant: ProjectMemberGrant
    name: str


class IProjectMemberRepository(Protocol):
    async def get_ownership(self, project_id: UUID) -> ProjectOwnership | None:
        """None, если проекта нет или он удалён."""
        ...

    async def set_member(self, project_id: UUID, grant: ProjectMemberGrant) -> None:
        """Заводит запись или заменяет роль и флаги существующей."""
        ...

    async def remove_member(self, project_id: UUID, principal_kind: str, principal_id: str) -> bool:
        """False, если такой записи не было. Доступ закрывается сразу: загрузчик прав кэша между запросами не держит."""
        ...
