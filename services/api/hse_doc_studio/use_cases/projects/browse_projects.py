"""Список проектов серверного режима: страница из каталога, без чтения project.json каждой папки."""

from __future__ import annotations

from hse_doc_studio.core.access.context import ActorRequired, current_actor
from hse_doc_studio.core.listing import Found
from hse_doc_studio.core.projects.browse import IProjectBrowser, ProjectBrowseQuery, ProjectCard


class BrowseProjectsUC:
    def __init__(self, browser: IProjectBrowser) -> None:
        self._browser = browser

    async def execute(self, query: ProjectBrowseQuery) -> Found[ProjectCard]:
        actor = current_actor()
        if actor is None:
            raise ActorRequired("список проектов без актора")
        return await self._browser.page(actor, query)
