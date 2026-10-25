from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.template_update.entities import (
    TemplateBase,
    TemplateTrackingState,
    UpdateJournal,
)
from hse_doc_studio.core.template_update.planner import MergeOutcome


@dataclass(frozen=True)
class RootSnapshot:
    """Корневой коммит истории проекта — кандидат в «чистый рендер при создании»."""

    commit: str
    message: str
    # Проект из `.hse-studio/project.json` корневого коммита (None — его там нет
    # или он нечитаем); папка — текущая папка проекта.
    project: Project | None
    # Пути корня, кроме `.hse-studio/`, → содержимое.
    files: Mapping[str, bytes]


class ITemplateBaseStore(Protocol):
    """Базы обновления и чтение истории в скрытом git проекта.

    Базы живут в `refs/hse/template/<версия>` — вне `refs/heads`, поэтому не видны
    ни в ветках, ни в истории интерфейса и не мешают пользовательскому git.
    """

    def load(self, project: Project, version: str) -> TemplateBase | None: ...
    def save(self, project: Project, base: TemplateBase, *, message: str, set_ref: bool = True) -> str: ...
    def record_from_head(
        self, project: Project, version: str, keep: Callable[[str], bool], *, message: str
    ) -> str | None: ...
    def set_ref(self, project: Project, version: str, commit: str) -> None: ...
    def root_snapshot(self, project: Project) -> RootSnapshot | None: ...
    def head(self, project: Project) -> str | None: ...
    def commit_message(self, project: Project, commit: str) -> str: ...
    def is_ancestor(self, project: Project, ancestor: str, descendant: str) -> bool: ...
    def files_at(self, project: Project, commit: str, paths: Iterable[str]) -> dict[str, bytes]: ...
    def changed_paths(self, project: Project, from_commit: str, to_commit: str) -> list[str]: ...
    def find_commit(self, project: Project, trailer: str, value: str) -> str | None: ...


class IMergeEngine(Protocol):
    def merge(self, ours: bytes, base: bytes, theirs: bytes) -> MergeOutcome: ...


class ITemplateTreeRenderer(Protocol):
    """Чистый рендер версии шаблона для проекта: ровно то, что пишет создание
    проекта (все базы команды, NDA), без выходов dynamic include."""

    def render(self, project: Project, version: TemplateVersion) -> dict[str, bytes]: ...


class ITemplateTrackingRepository(Protocol):
    def get(self, folder: Path) -> TemplateTrackingState: ...
    def save(self, folder: Path, state: TemplateTrackingState) -> None: ...


class IUpdateJournalRepository(Protocol):
    def get(self, folder: Path) -> UpdateJournal | None: ...
    def save(self, folder: Path, journal: UpdateJournal) -> None: ...
    def backup(self, folder: Path, rel_paths: Iterable[str]) -> None: ...
    def restore(self, folder: Path, rel_path: str) -> bool: ...
    def clear(self, folder: Path) -> None: ...
    def list_active(self, folders: Iterable[Path]) -> list[Path]: ...
