"""Порты организаций и групп. Репозитории APP-scope; многотабличные записи объединяет ambient `IUnitOfWork`."""

from __future__ import annotations

from typing import Protocol

from hse_doc_studio.core.listing import Found, Picked
from hse_doc_studio.core.orgs.entities import (
    AdminOrgSummary,
    Group,
    GroupMemberQuery,
    GroupMemberView,
    GroupPreview,
    GroupQuery,
    GroupSummary,
    MemberQuery,
    Org,
    OrgMember,
    OrgMemberView,
    OrgQuery,
    OrgRole,
    OrgSummary,
    UserOrgQuery,
    UserOrgView,
)


class IOrgRepository(Protocol):
    async def add(self, org: Org) -> None:
        """Занятый slug даёт `IdentityError(slug_taken)`."""
        ...

    async def get(self, org_id: str) -> Org | None: ...
    async def get_by_slug(self, slug: str) -> Org | None: ...
    async def update(self, org: Org) -> None: ...
    async def delete(self, org_id: str) -> None:
        """Вместе с членством и группами; проекты организации удалению мешают (`org_has_projects` решает сценарий)."""
        ...

    async def count_projects(self, org_id: str) -> int:
        """Проекты организации, включая архивные и удалённые, пока их не стёрли окончательно."""
        ...

    async def summary(self, org: Org, user_id: str) -> OrgSummary | None:
        """Организация с ролью человека и счётчиками; None, если человек не участник."""
        ...

    async def list_for_user(self, user_id: str) -> list[OrgSummary]: ...
    async def page_all(self, viewer_id: str, query: OrgQuery) -> Found[AdminOrgSummary]:
        """Страница организаций установки (для админа) с ролью смотрящего, если он в ней состоит.

        Счётчики считаются только для строк страницы; сортировка по счётчику считает их в самом запросе.
        """
        ...

    async def pick(self, q: str | None, limit: int) -> Picked[Org]:
        """Пикер админа: первые по названию организации, где `q` есть в названии или адресе."""
        ...

    async def page_for_user(self, user_id: str, query: UserOrgQuery) -> Found[UserOrgView]:
        """Организации человека с его ролью: карточка человека в админке."""
        ...

    async def summary_for_admin(self, org: Org, viewer_id: str) -> AdminOrgSummary: ...
    async def owner_counts(self, org_ids: list[str]) -> dict[str, int]:
        """Число владельцев каждой из организаций."""
        ...

    async def get_member(self, org_id: str, user_id: str) -> OrgMember | None: ...
    async def list_members(self, org_id: str) -> list[OrgMemberView]: ...
    async def page_members(self, org_id: str, query: MemberQuery) -> Found[OrgMemberView]: ...
    async def role_counts(self, org_id: str, q: str | None) -> dict[OrgRole, int]:
        """Число участников каждой роли под тем же поиском; роль без участников даёт 0."""
        ...

    async def members_among(self, org_id: str, user_ids: list[str]) -> set[str]:
        """Кто из `user_ids` состоит в организации: проверка состава группы без чтения всех участников."""
        ...

    async def add_member(self, member: OrgMember) -> None:
        """Повтор даёт `IdentityError(already_member)`."""
        ...

    async def set_role(self, org_id: str, user_id: str, role: OrgRole) -> None: ...
    async def remove_member(self, org_id: str, user_id: str) -> bool: ...
    async def lock_owners(self, org_id: str) -> list[str]:
        """Блокирует строки владельцев до конца транзакции и возвращает их id: двое владельцев, которые
        одновременно уходят, не оставят организацию без владельца."""
        ...


class IGroupRepository(Protocol):
    async def add(self, group: Group) -> None:
        """Занятое в организации имя (без учёта регистра) даёт `IdentityError(name_taken)`."""
        ...

    async def get(self, group_id: str) -> Group | None: ...
    async def list_for_org(self, org_id: str) -> list[GroupSummary]: ...
    async def page_for_org(self, org_id: str, query: GroupQuery) -> Found[GroupPreview]:
        """Страница групп организации: у каждой число участников и первые `GROUP_PREVIEW` по имени."""
        ...

    async def previews(self, group_ids: list[str]) -> dict[str, GroupPreview]:
        """То же для отдельных групп (ответ на создание и правку); неизвестные id пропускаются."""
        ...

    async def page_members(self, group_id: str, query: GroupMemberQuery) -> Found[GroupMemberView]: ...
    async def update(self, group: Group) -> None: ...
    async def delete(self, group_id: str) -> None: ...
    async def list_members(self, group_id: str) -> list[GroupMemberView]: ...
    async def add_member(self, group_id: str, user_id: str) -> None:
        """Повтор даёт `IdentityError(already_member)`."""
        ...

    async def remove_member(self, group_id: str, user_id: str) -> bool: ...
    async def names_for_user(self, user_id: str) -> dict[str, list[str]]:
        """Организация -> названия её групп, в которых состоит человек."""
        ...

    async def remove_user_from_org_groups(self, org_id: str, user_id: str) -> int:
        """Убирает человека из всех групп организации: вышедший из организации в группах не остаётся."""
        ...
