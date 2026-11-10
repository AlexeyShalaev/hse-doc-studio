"""Свежесть сборки: собрана ли она из тех же входов, что лежат в проекте сейчас (connected-devices.md, часть 3).

Одно правило для статуса сборок в облаке, для статуса и получения сборок в локальной Студии. Входы сборки
определяет `core.builds.inputs`: служебные записи (состояние подписей, статус документа в `project.json`, коммиты
сборок соседних документов) вершину истории двигают и дерево пачкают, но сборку устаревшей не делают.

Сначала дешёвая проверка: коммит сборки это вершина и дерево чистое. Иначе сравнение входов в истории проекта,
одно на коммит за запрос. Без истории или без коммита сборки ответ «неизвестно» (None); сбой сравнения даёт
прежний строгий ответ по вершине.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.protocols import IVcsService

logger = structlog.get_logger()


@dataclass
class BuildFreshness:
    """Свежесть сборок одного проекта на время одного запроса: вершина читается один раз, сравнение кэшируется."""

    vcs: IVcsService
    project: Project
    head: str | None = None
    dirty: bool = False
    _known: dict[str, bool] = field(default_factory=dict)

    @classmethod
    async def load(cls, vcs: IVcsService, project: Project) -> BuildFreshness:
        settings = VcsSettings.from_meta(project.meta)
        try:
            state = await asyncio.to_thread(vcs.status, project, settings)
        except Exception:  # noqa: BLE001 — без истории свежесть неизвестна, статус сборок от этого не падает
            logger.warning("project head unavailable", exc_info=True)
            return cls(vcs, project)
        if not (state.available and state.initialized):
            return cls(vcs, project)
        return cls(vcs, project, state.head, state.dirty)

    async def of(self, commit: str | None) -> bool | None:
        """True: сборка из коммита `commit` собрана из текущих входов; False: входы изменились; None: неизвестно."""
        if not commit or not self.head:
            return None
        if commit == self.head and not self.dirty:
            return True
        if commit not in self._known:
            self._known[commit] = not await self._changed(commit)
        return self._known[commit]

    async def _changed(self, commit: str) -> bool:
        settings = VcsSettings.from_meta(self.project.meta)
        try:
            return await asyncio.to_thread(self.vcs.build_inputs_changed, self.project, settings, commit)
        except Exception:  # noqa: BLE001 — сравнение не вышло: строгий ответ по вершине, как до сравнения входов
            logger.warning("build inputs not compared", commit=commit, exc_info=True)
            return commit != self.head or self.dirty
