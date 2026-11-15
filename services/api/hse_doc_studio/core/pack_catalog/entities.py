"""Источники каталога паков, разбор их ревизии и журнал действий (docs/design/template-studio.md, 10.3, срез T17).

Источник это откуда приходят паки сверх вшитых в образ: git (адрес, папка паков, тег, ветка или sha, доступ),
загруженный архив (закрытые контуры) или папка на диске (только локально, «Подключить к каталогу этой Студии»).
«Проверить» тянет ревизию источника, разбирает её лоадером этой Студии и строит план (`plan.CatalogPlan`);
«Применить» кладёт версии плана в хранилище и переключает каталог.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class SourceKind(StrEnum):
    git = "git"
    archive = "archive"
    folder = "folder"


@dataclass(frozen=True)
class SourceError:
    """Последний сбой проверки или применения: код из `contracts/pack-catalog/error_codes.json` (или код
    git-синхронизации) и текст на языке интерфейса того, кто нажал кнопку."""

    code: str
    detail: str


@dataclass(frozen=True)
class CatalogSource:
    id: UUID
    kind: SourceKind
    label: str
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None
    # Выключенный источник прячет свои паки из мастера проекта; версии остаются для проектов (10.4).
    enabled: bool = True
    # Пак с id вшитого пака подключается только с этой галочкой («Заменить встроенный»).
    replace_builtin: bool = False
    # Отслеживание раз в сутки: новые выпущенные версии проверяются и применяются сами, если план чистый.
    track: bool = False
    # Папка паков внутри репозитория, архива или папки: `packs` или `.` (корень).
    packs_path: str = "."
    # git: адрес без секретов, тег, ветка или sha (None: ветка по умолчанию), доступ.
    url: str | None = None
    ref: str | None = None
    credential_id: UUID | None = None
    service_access_id: UUID | None = None
    insecure_http: bool = False
    # archive: sha256 загруженного файла (он же ревизия) и исходное имя.
    archive_digest: str | None = None
    archive_name: str | None = None
    # folder: абсолютный путь папки (только локально) и рабочее пространство Студии шаблонов, из которого подключили.
    folder: str | None = None
    workspace_id: UUID | None = None
    # Состояние: применённая ревизия и последняя проверка.
    applied_revision: str | None = None
    applied_at: datetime | None = None
    checked_revision: str | None = None
    checked_at: datetime | None = None
    check_ok: bool | None = None
    # Сколько новых версий даст «Применить» на проверенной ревизии.
    pending_versions: int = 0
    error: SourceError | None = None


class EventAction(StrEnum):
    add = "add"
    update = "update"
    check = "check"
    apply = "apply"
    enable = "enable"
    disable = "disable"
    remove = "remove"
    track = "track"


@dataclass(frozen=True)
class CatalogEvent:
    """Строка истории источника: кто, когда, что сделал и с каким итогом (журнал только дописывается)."""

    id: UUID
    source_id: UUID
    action: EventAction
    at: datetime
    ok: bool
    actor_id: str | None = None
    revision: str | None = None
    # Сводка: добавленные версии, число ошибок, код отказа.
    summary: Mapping[str, Any] = field(default_factory=dict)


# ── разбор ревизии (в отдельном процессе, без сети) ─────────────────────────


@dataclass(frozen=True)
class InspectedVersion:
    template: str
    version: str
    # Есть в `releases.yaml` шаблона источника: только такие версии попадают в каталог.
    released: bool
    registry_digest: str | None
    # Дайджест каталога, посчитанный по файлам ревизии (None: каталога нет).
    digest: str | None
    kind: str | None = None
    manifest_format: int | None = None
    min_studio: str | None = None
    # Лоадер этой Студии разобрал версию (иначе её не увидит ни мастер, ни проекты).
    readable: bool = False
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class InspectedTemplate:
    id: str
    # Каталог шаблона от корня паков ревизии (`<пак>/templates/<шаблон>`).
    path: str
    versions: tuple[InspectedVersion, ...] = ()
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class InspectedPack:
    id: str
    # Каталог пака от корня паков ревизии.
    path: str
    name: Mapping[str, str] = field(default_factory=dict)
    templates: tuple[InspectedTemplate, ...] = ()
    problems: tuple[str, ...] = ()
    # Лоадер этой Студии разобрал `pack.yaml`.
    readable: bool = True


@dataclass(frozen=True)
class InspectedTree:
    packs: tuple[InspectedPack, ...] = ()
    problems: tuple[str, ...] = ()
