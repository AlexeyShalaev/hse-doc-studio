"""Порты подсистемы бэкапов (реализации в infra)."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Protocol

from hse_doc_studio.core.backup.crypto import EncryptingWriter
from hse_doc_studio.core.backup.entities import (
    BackupDestination,
    BackupRun,
    DestinationSecrets,
    DestinationSpec,
    ManifestPart,
    RunStatus,
    StoredDestination,
)
from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.core.storage.ports import IObjectStore


class IBackupDestinationRepository(Protocol):
    async def list_all(self) -> list[BackupDestination]: ...
    async def get(self, destination_id: str) -> StoredDestination | None: ...
    async def get_default(self) -> StoredDestination | None: ...
    async def add(self, stored: StoredDestination) -> None:
        """Единственное назначение становится умолчанием само."""
        ...

    async def update(self, stored: StoredDestination) -> None: ...
    async def delete(self, destination_id: str) -> None:
        """Удаляет назначение; если оно было умолчанием, метка переходит на самое старое из оставшихся."""
        ...

    async def set_default(self, destination_id: str) -> None: ...
    async def record_check(self, destination_id: str, *, at: datetime, ok: bool, error: str | None) -> None: ...
    async def name_taken(self, name: str, *, except_id: str | None = None) -> bool: ...


class IBackupRunRepository(Protocol):
    async def start(self, run: BackupRun) -> bool:
        """Записывает запуск `running`; False, если уже идёт другой (атомарно)."""
        ...

    async def set_stage(self, run_id: str, stage: str) -> None: ...
    async def finish(
        self,
        run_id: str,
        *,
        status: RunStatus,
        at: datetime,
        size_bytes: int | None,
        backup_id: str | None,
        error: str | None,
        manifest_sha256: str | None,
    ) -> BackupRun: ...

    async def get(self, run_id: str) -> BackupRun | None: ...
    async def page(self, window: Window) -> Found[BackupRun]: ...
    async def alive_for(self, destination_id: str) -> list[BackupRun]:
        """Успешные запуски назначения с живым бэкапом."""
        ...

    async def mark_removed(self, run_id: str, at: datetime) -> None: ...
    async def interrupt_running(self, at: datetime) -> int: ...
    async def running(self) -> BackupRun | None: ...
    async def last_finished(self) -> BackupRun | None: ...


class IBackupStoreFactory(Protocol):
    def open(self, spec: DestinationSpec, secrets: DestinationSecrets) -> IObjectStore:
        """Хранилище назначения; ключ объектов это `префикс/backup_id/файл`. Для local путь проверен внутри корня."""
        ...

    def is_primary(self, spec: DestinationSpec) -> bool:
        """Назначение совпадает с основным объектным хранилищем или лежит в данных установки."""
        ...


class IPartProducer(Protocol):
    """Выдаёт открытый текст одной части бэкапа в шифрующий поток."""

    name: str

    async def produce(self, writer: EncryptingWriter) -> dict[str, int]:
        """Пишет часть в `writer`; возвращает числа для заметок манифеста (например, число файлов)."""
        ...


class IPartUploader(Protocol):
    async def upload(
        self, store: IObjectStore, base: str, producer: IPartProducer, key: bytes
    ) -> tuple[ManifestPart, dict[str, int]]:
        """Часть → временный зашифрованный файл → загрузка → проверка чтением обратно."""
        ...


class IPartFetcher(Protocol):
    async def fetch(self, store: IObjectStore, key: str, part: ManifestPart) -> AbstractContextManager[BinaryIO]:
        """Скачивает шифртекст части во временный файл, сверяя размер и sha256 с манифестом (`BackupError` integrity);
        контекст отдаёт открытый файл и удаляет его на выходе."""
        ...


class IBackupEnvironment(Protocol):
    app_version: str

    async def schema_revision(self) -> str | None: ...
    async def installation_id(self) -> str | None: ...


class IBackupKeySource(Protocol):
    async def installation_keys(self) -> list[bytes]:
        """Сырые 32 байта ключей установки, первичный первым; пусто, если ключа нет."""
        ...

    async def passphrase(self) -> str | None: ...


class IAdminDirectory(Protocol):
    async def active_admin_ids(self) -> list[str]: ...


@dataclass(frozen=True)
class BackupPlan:
    producers: Sequence[IPartProducer]


class IBackupPlanFactory(Protocol):
    async def create(self) -> BackupPlan:
        """Части в порядке снятия: база, файлы, объекты, настройки."""
        ...


class IRestoreTarget(Protocol):
    """Установка, в которую восстанавливают. Все проверки и записи через этот порт."""

    async def api_is_running(self) -> bool: ...
    async def describe(self) -> "TargetState": ...
    async def restore_database(self, source: BinaryIO) -> None: ...
    async def restore_files(self, source: BinaryIO, *, move_existing: bool, stamp: str) -> int: ...
    async def restore_objects(self, source: BinaryIO) -> int: ...
    async def current_revision_known(self, revision: str | None) -> bool: ...


@dataclass(frozen=True)
class TargetState:
    users: int
    projects: int
    objects: int

    @property
    def empty(self) -> bool:
        return self.users == 0 and self.projects == 0 and self.objects == 0
