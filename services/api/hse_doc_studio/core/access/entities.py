"""Сущности модели доступа: актор, роль, право участника и членство проекта.

Имена намеренно не пересекаются с `core.project_access` (там `ProjectAccess` —
режим проекта full / read_only / files_only, а не права человека). `Project`
членства не хранит, поэтому оно приходит отдельным `ProjectAcl`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class ActorKind(StrEnum):
    local = "local"
    user = "user"
    guest = "guest"


class ActorSource(StrEnum):
    """Чем подтверждён актор: сессией, персональным токеном, гостевой ссылкой или локальным запуском."""

    session = "session"
    pat = "pat"
    link = "link"
    local = "local"
    # Фоновая задача от имени пользователя, поставившего её: применение результата и хуки после рестарта.
    job = "job"


class Role(StrEnum):
    reader = "reader"
    reviewer = "reviewer"
    editor = "editor"
    owner = "owner"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    id: str | None = None
    name: str | None = None
    email: str | None = None
    link_id: str | None = None
    # Админ установки; доступа к содержимому чужих проектов это не даёт.
    is_instance_admin: bool = False
    source: ActorSource | None = None
    # Ограничения персонального токена (`api`, `git:read`, `git:write`); у сессии пусто.
    scopes: frozenset[str] = frozenset()

    @classmethod
    def local(cls) -> Actor:
        return cls(kind=ActorKind.local, source=ActorSource.local)

    @classmethod
    def user(
        cls,
        id: str,
        name: str | None = None,
        email: str | None = None,
        *,
        is_instance_admin: bool = False,
        source: ActorSource | None = None,
        scopes: frozenset[str] = frozenset(),
    ) -> Actor:
        return cls(
            kind=ActorKind.user,
            id=id,
            name=name,
            email=email,
            is_instance_admin=is_instance_admin,
            source=source,
            scopes=scopes,
        )

    @classmethod
    def guest(cls, link_id: str, name: str | None = None) -> Actor:
        return cls(kind=ActorKind.guest, link_id=link_id, name=name, source=ActorSource.link)

    @property
    def is_local(self) -> bool:
        return self.kind is ActorKind.local

    @property
    def is_guest(self) -> bool:
        return self.kind is ActorKind.guest

    @property
    def key(self) -> str | None:
        """Ключ в `ProjectAcl.grants`: id пользователя или `link:<link_id>` для гостя."""
        if self.kind is ActorKind.user:
            return self.id
        if self.kind is ActorKind.guest and self.link_id:
            return f"link:{self.link_id}"
        return None


@dataclass(frozen=True)
class Grant:
    role: Role
    # Персона проекта (слаг автора, научрук), к которой привязан участник.
    persona_slug: str | None = None
    # Читателю и гостю-читателю исходники и история открыты только по этому флагу.
    show_sources: bool = False
    can_share: bool = False
    # Редактору team-проекта правка вне своей папки и shared/.
    can_edit_all: bool = False


@dataclass(frozen=True)
class ProjectAcl:
    project_id: str
    owner_id: str | None = None
    team: bool = False
    shared_enabled: bool = True
    grants: Mapping[str, Grant] = field(default_factory=dict)

    def grant_for(self, actor: Actor) -> Grant | None:
        key = actor.key
        return self.grants.get(key) if key is not None else None
