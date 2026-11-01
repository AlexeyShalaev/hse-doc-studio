"""Проекты для локальной Студии и адрес клонирования проекта (S21, раздел 7.6).

Список отдаётся по git-токену вызовом `/git/-/projects`, а не `/api/v1/projects`: git-токен API не открывает.
В него попадают только проекты, где у человека есть право исходников по членству, группе или организации;
ссылочные права не учитываются (S3).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.git_remote.push_policy import clone_url
from hse_doc_studio.core.listing import MAX_LIMIT, Found, Window
from hse_doc_studio.core.projects.browse import IProjectBrowser, ProjectBrowseQuery
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

# Сколько проектов человека перебирается для списка: личных проектов у человека немного.
_SCAN_LIMIT = 2000


@dataclass(frozen=True)
class GitProjectView:
    id: UUID
    name: str
    owner_name: str
    role: Role
    can_push: bool
    clone_url: str
    updated_at: datetime | None


class ListGitProjectsUC:
    def __init__(self, browser: IProjectBrowser, acl: IProjectAclRepository, public_url: str) -> None:
        self._browser = browser
        self._acl = acl
        self._public_url = public_url

    async def execute(self, actor: Actor, *, q: str | None, window: Window, can_write: bool) -> Found[GitProjectView]:
        found: list[GitProjectView] = []
        offset = 0
        while offset < _SCAN_LIMIT:
            page = await self._browser.page(
                actor, ProjectBrowseQuery(q=q or None, window=Window(limit=MAX_LIMIT, offset=offset))
            )
            for card in page.items:
                acl = await self._acl.load_for(actor, card.id, include_links=False)
                if decide(actor, Action.GIT_FETCH, acl) is not Decision.allow:
                    continue
                grant = acl.grant_for(actor) if acl is not None else None
                found.append(
                    GitProjectView(
                        id=card.id,
                        name=card.name,
                        owner_name=card.owner.name,
                        role=grant.role if grant is not None else card.my_role,
                        can_push=can_write and decide(actor, Action.GIT_PUSH, acl) is Decision.allow,
                        clone_url=clone_url(self._public_url, card.id),
                        updated_at=card.updated_at,
                    )
                )
            offset += MAX_LIMIT
            if offset >= page.total:
                break
        return Found(items=found[window.offset : window.offset + window.limit], total=len(found))


@dataclass(frozen=True)
class ProjectGitRemoteView:
    enabled: bool
    clone_url: str | None
    can_push: bool
    branch: str | None


class GetProjectGitRemoteUC:
    """Адрес клонирования для настроек проекта; право GIT_FETCH проверил гард маршрута."""

    def __init__(  # noqa: PLR0913 — порты и настройки одного ответа
        self,
        acl: IProjectAclRepository,
        project_repo: IProjectRepository,
        project_index: IProjectIndexRepository,
        vcs: IVcsService,
        *,
        enabled: bool,
        public_url: str,
    ) -> None:
        self._acl = acl
        self._projects = GetProjectUC(project_repo, project_index)
        self._vcs = vcs
        self._enabled = enabled
        self._public_url = public_url

    async def execute(self, actor: Actor, project_id: UUID) -> ProjectGitRemoteView:
        if not self._enabled:
            return ProjectGitRemoteView(enabled=False, clone_url=None, can_push=False, branch=None)
        acl = await self._acl.load_for(actor, project_id, include_links=False)
        project = (await self._projects.execute(GetProjectInput(project_id=project_id))).project
        branch: str | None = None
        if self._vcs.is_initialized(project):
            branch = next(
                (b.name for b in await asyncio.to_thread(self._vcs.list_branches, project) if b.is_current), None
            )
        return ProjectGitRemoteView(
            enabled=decide(actor, Action.GIT_FETCH, acl) is Decision.allow,
            clone_url=clone_url(self._public_url, project_id),
            can_push=decide(actor, Action.GIT_PUSH, acl) is Decision.allow,
            branch=branch or "master",
        )
