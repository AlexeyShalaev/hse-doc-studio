"""Порты Git-синхронизации: реализации в infra/git_sync, использование в use_cases/git_sync.

Здесь только форма. Сигнатуры уточняют срезы, которые первыми приносят реализацию порта.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import (
    AuthorProfile,
    CredentialStatus,
    CredentialUsage,
    GitCredential,
    GitHostKey,
    GitOperation,
    GitResult,
    OperationKind,
    OperationPhase,
    RemoteProbe,
    RemoteTarget,
    SyncState,
)
from hse_doc_studio.core.git_sync.error_classifier import GitOp
from hse_doc_studio.core.git_sync.secret import CipherStatus, Secret

# Прогресс сетевой операции: доля 0..100 и последняя строка git.
ProgressCallback = Callable[[float | None, str], None]


class ISecretCipher(Protocol):
    """Шифрование секретов в покое: токены и закрытые ключи на диск попадают только так.

    `aad` привязывает шифртекст к записи, которой он принадлежит.
    """

    def encrypt(self, plaintext: Secret, *, aad: str) -> str:
        """Бросает GitSyncError(secrets_unavailable), если ключ нельзя ни прочитать, ни создать."""
        ...

    def decrypt(self, token: str, *, aad: str) -> Secret:
        """Бросает GitSyncError(secrets_unavailable), если ключа нет, он не тот или шифртекст повреждён."""
        ...

    def can_read(self, token: str) -> bool:
        """Дёшево, без расшифровки: известен ли ключ, которым записан шифртекст."""
        ...

    def status(self) -> CipherStatus: ...


class IGitCredentialRepository(Protocol):
    """Хранилище учётных данных: метаданные открыты, секрет только шифртекстом."""

    def list(self) -> list[GitCredential]:
        """Без расшифровки. Запись с недоступным ключом приходит со статусом unreadable."""
        ...

    def get(self, credential_id: UUID) -> GitCredential | None: ...
    def add(self, credential: GitCredential, secret: Secret) -> None: ...
    def update(self, credential: GitCredential, secret: Secret | None = None) -> None:
        """`secret=None` оставляет сохранённый секрет."""
        ...

    def delete(self, credential_id: UUID) -> bool: ...
    def get_secret(self, credential_id: UUID) -> Secret:
        """Бросает NotFoundError, если записи нет, и GitSyncError(secrets_unavailable), если ключ не подходит."""
        ...

    def mark(self, credential_id: UUID, status: CredentialStatus, *, used_at: datetime | None = None) -> None:
        """Статус и время последнего использования без перезаписи секрета; неизвестная запись игнорируется."""
        ...


class IGitCredentialUsage(Protocol):
    """Какие проекты подключили удалённый репозиторий с этим доступом (из настроек хранилищ проектов)."""

    def by_credential(self) -> dict[UUID, list[CredentialUsage]]: ...


@dataclass(frozen=True)
class GeneratedSshKey:
    private_key: Secret
    public_key: str
    fingerprint_sha256: str


class ISshKeyGenerator(Protocol):
    def generate(self, comment: str) -> GeneratedSshKey: ...


@dataclass(frozen=True)
class KnownHost:
    host: str
    port: int | None
    key_types: tuple[str, ...]
    fingerprints_sha256: tuple[str, ...]
    added_at: datetime


class IKnownHostsStore(Protocol):
    """Собственный known_hosts Студии: пользовательский ~/.ssh не читается и не меняется."""

    def list(self) -> list[KnownHost]: ...
    def trust(self, host: str, port: int | None, keys: Sequence[str], *, replace: bool = False) -> None: ...
    def forget(self, host: str, port: int | None) -> None: ...
    def file_path(self) -> Path: ...


class IHostKeyScanner(Protocol):
    async def scan(self, host: str, port: int | None) -> list[GitHostKey]: ...


class IGitRemoteRunner(Protocol):
    """Единственный запускатель сетевого git: чистое окружение, секрет только через окружение процесса, таймаут, отмена.

    Любой сбой приходит как GitSyncError с кодом из закрытого списка; stderr в тексте ошибки очищен от секретов.
    """

    async def run(
        self,
        args: Sequence[str],
        *,
        op: GitOp,
        git_dir: Path,
        target: RemoteTarget,
        timeout_s: float,
        on_progress: ProgressCallback | None = None,
    ) -> GitResult:
        """Команда с сетью. `args` начинаются с подкоманды, `--git-dir` и защитные `-c` добавляет раннер."""
        ...

    async def run_local(
        self, args: Sequence[str], *, git_dir: Path | None, timeout_s: float, check: bool = True
    ) -> GitResult:
        """Команда без сети (init, cat-file) в том же защитном окружении. `check`: ненулевой код это ошибка."""
        ...


class IGitTransport(Protocol):
    """Сетевые операции над хранилищем проекта. Ошибки приходят как GitSyncError с кодом, кроме probe."""

    async def probe(self, target: RemoteTarget) -> RemoteProbe:
        """Что лежит по адресу, без записи в проект. Отказ сети или доступа приходит как `ok=False`, не исключением."""
        ...

    async def read_tip_file(self, target: RemoteTarget, *, branch: str, path: str) -> bytes | None:
        """Файл из вершины ветки через поверхностную выборку во временное хранилище; None, если файла нет."""
        ...

    async def fetch(
        self,
        git_dir: Path,
        target: RemoteTarget,
        *,
        branch: str,
        timeout_s: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Загрузить ветку в `refs/remotes/origin/<branch>`. Нет ветки: branch_missing."""
        ...

    async def push(
        self,
        git_dir: Path,
        target: RemoteTarget,
        *,
        local_sha: str,
        remote_branch: str,
        timeout_s: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Отправить коммит `local_sha` в `refs/heads/<remote_branch>` без force. Ветка ушла вперёд: remote_moved."""
        ...


class IGitSyncStateRepository(Protocol):
    """hse-sync.json внутри хранилища проекта; неизвестные ключи при записи сохраняются."""

    def get(self, project_folder: Path) -> SyncState | None: ...
    def save(self, project_folder: Path, state: SyncState) -> None: ...
    def clear(self, project_folder: Path) -> None: ...


class IGitRepoReader(Protocol):
    """Чтение объектов хранилища без обращения к рабочему дереву и без сети."""

    def rev_parse(self, project_folder: Path, ref: str) -> str | None: ...
    def merge_base(self, project_folder: Path, a: str, b: str) -> str | None: ...
    def is_ancestor(self, project_folder: Path, ancestor: str, descendant: str) -> bool: ...
    def ahead_behind(self, project_folder: Path, local: str, remote: str) -> tuple[int, int]: ...
    def changed_paths(self, project_folder: Path, a: str, b: str) -> list[tuple[str, str]]: ...
    def read_files(self, project_folder: Path, commit: str, paths: Sequence[str]) -> Mapping[str, bytes | None]: ...
    def path_last_changed_at(self, project_folder: Path, commit: str, path: str) -> datetime | None: ...


class IGitMergeCommitter(Protocol):
    """Запись коммита слияния инструментами низкого уровня и безопасное сдвигание ветки."""

    def commit_merge(
        self,
        project_folder: Path,
        *,
        ours: str,
        theirs: str,
        tree_files: Mapping[str, bytes],
        message: str,
        trailers: Mapping[str, str],
    ) -> str: ...

    def advance_branch(self, project_folder: Path, branch: str, *, expected: str, new: str) -> bool:
        """update-ref с проверкой старого значения: False, если ветка успела сдвинуться."""
        ...


class IGitOperationRegistry(Protocol):
    """Реестр длительных операций в памяти процесса. Одна операция на папку проекта."""

    def begin(self, kind: OperationKind, *, project_id: UUID | None, folder: Path | None) -> GitOperation:
        """Бросает GitSyncError(sync_busy, operation_id=...), если у папки уже идёт операция."""
        ...

    def update(
        self,
        operation_id: str,
        *,
        phase: OperationPhase | None = None,
        percent: float | None = None,
        message: str | None = None,
    ) -> None: ...

    def finish(self, operation_id: str, operation: GitOperation) -> None: ...
    def get(self, operation_id: str) -> GitOperation | None: ...
    def current_for(self, project_id: UUID) -> GitOperation | None: ...
    def is_busy(self, folder: Path) -> bool: ...


class IGitRemoteRegistry(Protocol):
    """Папки проектов, у которых подключён удалённый репозиторий: фоновая выборка обходит только их."""

    def add(self, folder: Path) -> None: ...
    def remove(self, folder: Path) -> None: ...
    def list(self) -> list[Path]: ...


@dataclass(frozen=True)
class SharedFolderInfo:
    provider: str
    root: Path
    evidence: tuple[str, ...]


class ISharedFolderDetector(Protocol):
    def detect(self, folder: Path) -> SharedFolderInfo | None: ...


class IGitBundleService(Protocol):
    def export_bundle(self, project_folder: Path, *, password: str | None = None) -> Path: ...
    def import_bundle(self, project_folder: Path, bundle: Path, *, password: str | None = None) -> str:
        """Кладёт содержимое бандла в `refs/hse/bundle/<ветка>` и возвращает его вершину."""
        ...


class ILocalAuthorProfile(Protocol):
    """Профиль человека на этой машине; None, пока он не заполнен."""

    def get(self) -> AuthorProfile | None: ...


@dataclass(frozen=True)
class MergeMeta:
    """Что известно о файле помимо содержимого: время последнего изменения каждой стороны."""

    ours_changed_at: datetime | None = None
    theirs_changed_at: datetime | None = None
    ours_commit: str | None = None
    theirs_commit: str | None = None


@dataclass(frozen=True)
class MergeDecision:
    """Решение по одному файлу: чистый итог или конфликт."""

    content: bytes | None
    conflict: bool = False
    deleted: bool = False
    # Путь копии, когда проигравшая версия бинарного файла сохранена рядом.
    copy_path: str | None = None
    copy_content: bytes | None = None


class IFileMergeStrategy(Protocol):
    """Слияние одного файла по его виду; единая точка расширения планировщика."""

    def merge(
        self, path: str, base: bytes | None, ours: bytes | None, theirs: bytes | None, meta: MergeMeta
    ) -> MergeDecision: ...
