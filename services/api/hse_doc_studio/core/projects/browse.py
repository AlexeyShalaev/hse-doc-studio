"""Список проектов серверного режима: поиск, фильтры, сортировка и страница по каталогу в базе.

Список не читает project.json каждой папки. Поля, которые меняются в файле проекта (название, закрепление,
архив, руководитель, время правки), каталог получает копией на каждый save и при сверке на старте.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.repositories import ProjectOwnerView
from hse_doc_studio.core.listing import Found, SortKey, Window

PROJECT_SORTS = ("name", "updated_at", "created_at")
ProjectOwnerFilter = Literal["me", "org", "shared"]


@dataclass(frozen=True)
class ProjectBrowseQuery:
    """Фильтры списка проектов; всё сочетается по И.

    `owner`: `me` свои, `org` проекты организаций, `shared` чужие личные проекты, открытые смотрящему.
    `q` ищет подстроку в названии, имени владельца и имени руководителя.
    """

    q: str | None = None
    archived: bool | None = None
    owner: ProjectOwnerFilter | None = None
    org_slug: str | None = None
    pinned: bool | None = None
    sort: SortKey = field(default_factory=lambda: SortKey("updated_at", descending=True))
    window: Window = field(default_factory=Window)


@dataclass(frozen=True)
class ProjectCard:
    """Строка списка проектов на сервере: всё из каталога, без пути папки."""

    id: UUID
    name: str
    kind: str
    staffing: Literal["solo", "team"]
    lang: str
    owner: ProjectOwnerView
    my_role: Role
    updated_at: datetime
    pinned: bool
    archived: bool
    shared_enabled: bool
    # Роль держится на ссылке, а не на членстве: в списке значок «По ссылке».
    via_link: bool = False


class IProjectBrowser(Protocol):
    async def page(self, actor: Actor, query: ProjectBrowseQuery) -> Found[ProjectCard]:
        """Страница проектов, которые актор видит (те же источники прав, что у загрузчика прав)."""
        ...
