"""Порты каталогов паков (срез T17): источники, подготовка ревизии, разбор, хранилище, журнал аудита."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.pack_catalog.entities import CatalogEvent, CatalogSource, InspectedTree
from hse_doc_studio.core.pack_catalog.plan import CatalogPlan
from hse_doc_studio.core.pack_catalog.store import CatalogState

# Псевдонимы: внутри класса имя `list` занято методом и в аннотациях означало бы его.
_Events = list[CatalogEvent]
_Sources = list[CatalogSource]


class ICatalogSourceRepository(Protocol):
    """Источники каталога и их история. Живут рядом с хранилищем на томе данных (`packs-store/`), поэтому бэкап
    тома переносит каталог целиком, а все процессы api видят одно и то же."""

    async def list(self) -> _Sources: ...
    async def get(self, source_id: UUID) -> CatalogSource | None: ...
    async def add(self, source: CatalogSource) -> None: ...
    async def update(self, source: CatalogSource) -> None:
        """Перезаписывает источник; удалённый тем временем не воскрешает."""
        ...

    async def delete(self, source_id: UUID) -> bool: ...
    async def add_event(self, event: CatalogEvent) -> None: ...
    async def events(self, source_id: UUID, *, limit: int) -> _Events:
        """Новые первыми."""
        ...


@dataclass(frozen=True)
class StagedRevision:
    """Ревизия источника, разложенная во временную папку: корень паков и сама ревизия (sha коммита, sha256
    архива, хеш снимка папки)."""

    revision: str
    root: Path


@dataclass(frozen=True)
class StageLimits:
    max_files: int
    max_bytes: int
    max_archive_bytes: int


class IRevisionStager(Protocol):
    """Ревизия источника во временной папке `dest` (создаётся заново): git (неглубокая разреженная выборка
    тега, ветки или sha), архив (распаковка с защитой от выхода за папку и ссылок), папка (снимок копией).

    Отказы это `CatalogError` (`ref_not_found`, `packs_path_missing`, `archive_*`, `tree_*`) или `GitSyncError`.
    """

    async def stage(self, source: CatalogSource, dest: Path, limits: StageLimits) -> StagedRevision: ...


class IRevisionInspector(Protocol):
    """Разбор паков ревизии лоадером этой Студии, `pack_lint` и `releases check` в отдельном процессе с пределами
    времени и памяти (раздел 9: Jinja пака только разбирается в песочнице, не исполняется)."""

    async def inspect(self, root: Path) -> InspectedTree: ...


@dataclass(frozen=True)
class AppliedPacks:
    state: CatalogState
    # Версии, которых раньше в хранилище не было: `<пак>/<шаблон>@<версия>`.
    added: tuple[str, ...]


class ICatalogStore(Protocol):
    """Хранилище `data_dir/packs-store` и активный каталог. Запись идёт под замком хранилища (один писатель на все
    процессы); после неё каталог этого процесса перечитывается сразу, остальные процессы замечают новую ревизию."""

    def state(self) -> CatalogState: ...

    def apply(self, source: CatalogSource, plan: CatalogPlan, root: Path) -> AppliedPacks:
        """Версии плана в хранилище, паки источника в каталоге. Перед записью план сверяется со свежим каталогом
        под замком: тот же номер с другим дайджестом или чужой пак дают `CatalogError(plan_blocked)`."""
        ...

    def set_listed(self, source_id: str, *, listed: bool, origin_label: str | None = None) -> CatalogState:
        """Паки источника видны мастеру проекта или скрыты (выключение, удаление). Версии остаются."""
        ...


class ICatalogReloader(Protocol):
    """Каталог шаблонов этого процесса: перечитать подключённые паки после записи хранилища."""

    def reload(self) -> int: ...


class IArchiveStore(Protocol):
    """Загруженные архивы источников: `packs-store/.archives/<sha256>.<расширение>` (их тоже переносит бэкап)."""

    def upload_path(self) -> Path:
        """Новый пустой путь для приёма загрузки на том же томе (потом `save` переносит его в хранилище)."""
        ...

    def save(self, upload: Path, *, name: str) -> str:
        """Переносит принятый файл в хранилище архивов, возвращает его sha256. Не .zip и не .tar.gz:
        `archive_invalid`."""
        ...

    def path(self, digest: str) -> Path | None: ...


class ICatalogAudit(Protocol):
    """Журнал аудита установки (на сервере); локально журнала нет, остаётся история источника."""

    async def record(
        self, action: str, *, actor_id: str | None, target: str | None, details: Mapping[str, object]
    ) -> None: ...
