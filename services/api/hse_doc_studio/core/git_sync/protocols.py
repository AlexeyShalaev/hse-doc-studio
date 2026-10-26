"""Порты Git-синхронизации: реализации в infra/git_sync, использование в use_cases/git_sync.

Здесь только форма. Сигнатуры уточняют срезы, которые первыми приносят реализацию порта.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.ci import CiOptions, RenderedCiFile
from hse_doc_studio.core.git_sync.entities import (
    AuthorCount,
    AuthorProfile,
    CloneResult,
    CommitBrief,
    CredentialStatus,
    CredentialUsage,
    GitCredential,
    GitOperation,
    GitOperationError,
    GitResult,
    LargeBlob,
    OperationKind,
    OperationPhase,
    OperationStatus,
    PathStamp,
    RemoteProbe,
    RemoteTarget,
    ScannedHostKey,
    StoreAudit,
    StoreFinding,
    StoreRemoteConfig,
    SyncResult,
    SyncState,
    SyncWarning,
    TreeEntry,
)
from hse_doc_studio.core.git_sync.error_classifier import GitOp
from hse_doc_studio.core.git_sync.merge.choices import FieldChoice
from hse_doc_studio.core.git_sync.merge.jsonmerge import AutoField, FieldConflict
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
    def find(self, host: str, port: int | None) -> KnownHost | None: ...
    def trust(self, host: str, port: int | None, keys: Sequence[ScannedHostKey], *, replace: bool = False) -> None:
        """Записать ключи. `replace`: сначала убрать все прежние ключи этого хоста."""
        ...

    def forget(self, host: str, port: int | None) -> None: ...
    def file_path(self) -> Path: ...


class IHostKeyScanner(Protocol):
    async def scan(self, host: str, port: int | None) -> list[ScannedHostKey]:
        """Ключи, которые хост предъявляет сейчас. Нет связи: offline, нет ssh-keyscan: ssh_unavailable."""
        ...


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
    def current_branch(self, project_folder: Path) -> str | None:
        """Ветка, на которой стоит HEAD; None при отсоединённом HEAD."""
        ...

    def merge_base(self, project_folder: Path, a: str, b: str) -> str | None: ...
    def merge_bases(self, project_folder: Path, a: str, b: str) -> list[str]:
        """Все лучшие общие предки: больше одного у перекрёстных слияний."""
        ...

    def is_ancestor(self, project_folder: Path, ancestor: str, descendant: str) -> bool: ...
    def ahead_behind(self, project_folder: Path, local: str, remote: str) -> tuple[int, int]: ...
    def changed_paths(self, project_folder: Path, a: str, b: str) -> list[tuple[str, str]]: ...
    def tree_entries(self, project_folder: Path, commit: str) -> list[TreeEntry]: ...
    def read_files(self, project_folder: Path, commit: str, paths: Sequence[str]) -> Mapping[str, bytes | None]: ...
    def path_stamp(
        self, project_folder: Path, tip: str, path: str, *, exclude_reachable_from: str | None = None
    ) -> PathStamp | None:
        """Последний коммит от `tip`, менявший путь; с `exclude_reachable_from` только среди новых за этой точкой."""
        ...

    def path_last_changed_at(self, project_folder: Path, commit: str, path: str) -> datetime | None: ...
    def large_blobs(
        self, project_folder: Path, tip: str, *, min_bytes: int, exclude_reachable_from: str | None = None
    ) -> list[LargeBlob]: ...

    def author_counts(self, project_folder: Path, rev: str) -> list[AuthorCount]:
        """Число коммитов по авторам, больше всех первым. `rev` может быть диапазоном `a..b`."""
        ...

    def commit_briefs(self, project_folder: Path, rev: str, *, limit: int) -> list[CommitBrief]:
        """Последние `limit` коммитов диапазона `rev` (`a..b` или один коммит), новые первыми."""
        ...

    def count_commits(self, project_folder: Path, rev: str) -> int: ...


class IGitMergeCommitter(Protocol):
    """Запись коммита слияния инструментами низкого уровня и безопасное сдвигание ветки."""

    def commit_merge(
        self,
        project_folder: Path,
        *,
        ours: str,
        theirs: str,
        changes: Mapping[str, bytes | None],
        message: str,
        trailers: Mapping[str, str],
    ) -> str:
        """Коммит с родителями `ours` и `theirs`; дерево `ours` с поправками `changes` (None удаляет файл).

        Ветку не двигает: это делает `advance_branch`. Трейлер `Hse-Kind: sync` ставится сам.
        """
        ...

    def advance_branch(self, project_folder: Path, branch: str, *, expected: str, new: str) -> bool:
        """update-ref с проверкой старого значения: False, если ветка успела сдвинуться.

        Если это ветка текущего HEAD, индекс приводится к дереву `new`; рабочее дерево не трогается.
        """
        ...

    def fast_forward(self, project_folder: Path, branch: str, *, expected: str, new: str) -> bool:
        """Перемотка ветки на потомка `expected` после того, как файлы записаны в рабочее дерево."""
        ...


class IGitStoreGuard(Protocol):
    """Проверка хранилища, приехавшего с чужой папкой: его config и хуки могут запускать код."""

    def audit(self, project_folder: Path) -> StoreAudit: ...
    def harden(self, project_folder: Path) -> tuple[StoreFinding, ...]:
        """Переписывает config по белому списку и убирает хуки; возвращает, что было убрано."""
        ...

    def ensure_trusted(self, project_folder: Path) -> None:
        """Бросает GitSyncError(store_untrusted), если аудит нашёл недоверенное."""
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
        cancellable: bool | None = None,
    ) -> None: ...

    def finish(
        self,
        operation_id: str,
        *,
        status: OperationStatus = OperationStatus.succeeded,
        result: SyncResult | CloneResult | None = None,
        error: GitOperationError | None = None,
    ) -> None:
        """Закрывает операцию: папка свободна, итог остаётся доступным ещё некоторое время."""
        ...

    def attach_task(self, operation_id: str, task: asyncio.Task[object]) -> None:
        """Задача, которую отменит `cancel`: вместе с ней гибнут дочерние процессы git."""
        ...

    def cancel(self, operation_id: str) -> GitOperation | None:
        """Отменяет задачу. None, если операции нет. Бросает GitSyncError(operation_not_cancellable)."""
        ...

    def get(self, operation_id: str) -> GitOperation | None:
        """Снимок операции: изменения реестра после вызова в него не попадают."""
        ...

    def current_for(self, project_id: UUID) -> GitOperation | None: ...
    def is_busy(self, folder: Path) -> bool: ...


class IGitRemoteRegistry(Protocol):
    """Папки проектов, у которых подключён удалённый репозиторий: фоновая выборка обходит только их."""

    def add(self, folder: Path) -> None: ...
    def remove(self, folder: Path) -> None: ...
    def list(self) -> list[Path]: ...


class IGitStoreRemotes(Protocol):
    """Подключение проекта в config его хранилища и отслеживаемые ветки. Секретов здесь нет."""

    def git_dir(self, project: Project) -> Path: ...
    def read(self, project: Project) -> StoreRemoteConfig | None:
        """None, если адрес не подключён. Без запуска git, пока в config нет секции remote."""
        ...

    def write(self, project: Project, config: StoreRemoteConfig) -> None: ...
    def clear(self, project: Project) -> None:
        """Убирает адрес, привязку и отслеживаемые ветки. Сам удалённый репозиторий не затрагивается."""
        ...

    def drop_tracking_refs(self, project: Project) -> None: ...


class IGitCloneStore(Protocol):
    """Хранилище нового проекта, которое клонирование собирает в пустой папке; проект ещё не зарегистрирован."""

    def init(self, folder: Path, branch: str) -> None:
        """Пустое хранилище на ветке `branch` без корневого коммита."""
        ...

    def write_exclude(self, folder: Path, patterns: Sequence[str]) -> None:
        """Исключения хранилища: пишутся до checkout, иначе служебные файлы попадут в рабочее дерево как новые."""
        ...

    def checkout(self, folder: Path, branch: str) -> None:
        """Рабочее дерево и индекс по `refs/remotes/origin/<branch>`; локальная ветка получает то же имя."""
        ...

    def write_remote(self, folder: Path, config: StoreRemoteConfig) -> None: ...


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


class ICiRenderer(Protocol):
    """Файл CI под выбранного провайдера; одинаковые параметры дают одинаковый текст."""

    def render(self, options: CiOptions) -> RenderedCiFile: ...


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
    # Структурированный файл: вид конфликта (значение ConflictType; без него — fields), спорные поля,
    # поля, которые правила решили без человека, и предупреждения об итоге.
    conflict_type: str | None = None
    fields: tuple[FieldConflict, ...] = ()
    auto: tuple[AutoField, ...] = ()
    warnings: tuple[SyncWarning, ...] = ()
    # Файл не разобрался как структура: планировщик сольёт его как текст.
    as_text: bool = False


class IFileMergeStrategy(Protocol):
    """Слияние одного файла по его виду; единая точка расширения планировщика."""

    def merge(
        self, path: str, base: bytes | None, ours: bytes | None, theirs: bytes | None, meta: MergeMeta
    ) -> MergeDecision: ...


class IFieldResolver(Protocol):
    """Повторное слияние структурированного файла с решениями человека по полям."""

    def resolve(
        self,
        path: str,
        base: bytes | None,
        ours: bytes | None,
        theirs: bytes | None,
        meta: MergeMeta,
        choices: Mapping[str, FieldChoice],
    ) -> MergeDecision:
        """Остались спорные поля — conflict=True. Неподходящее решение — InvalidFieldChoiceError."""
        ...
