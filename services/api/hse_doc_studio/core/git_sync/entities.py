"""Сущности Git-синхронизации.

Значения перечислений совпадают со строками контракта (contracts/git-sync). Секретов здесь нет:
токены и закрытые ключи живут только за портами ISecretCipher и IGitCredentialRepository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.url import GitProvider, RemoteKind, RemoteUrl


class GitCredentialKind(StrEnum):
    pat = "pat"
    ssh_key = "ssh_key"


class CredentialStatus(StrEnum):
    unverified = "unverified"
    ok = "ok"
    auth_failed = "auth_failed"
    unreadable = "unreadable"


class SyncRelation(StrEnum):
    """Как локальная ветка соотносится с отслеживаемой удалённой (по ссылкам, без сети)."""

    none = "none"
    unfetched = "unfetched"
    remote_empty = "remote_empty"
    in_sync = "in_sync"
    ahead = "ahead"
    behind = "behind"
    diverged = "diverged"


class SyncHealth(StrEnum):
    """Итог последнего обращения к удалённому репозиторию."""

    ok = "ok"
    unauthenticated = "unauthenticated"
    offline = "offline"
    error = "error"
    host_key_changed = "host_key_changed"
    remote_missing = "remote_missing"
    branch_missing = "branch_missing"


class SyncUiState(StrEnum):
    no_remote = "no_remote"
    unfetched = "unfetched"
    up_to_date = "up_to_date"
    ahead = "ahead"
    behind = "behind"
    diverged = "diverged"
    syncing = "syncing"
    conflicts = "conflicts"
    auth_failed = "auth_failed"
    offline = "offline"
    error = "error"
    blocked = "blocked"


class SyncBlockReason(StrEnum):
    off_branch = "off_branch"
    read_only = "read_only"
    remote_schema_newer = "remote_schema_newer"
    store_untrusted = "store_untrusted"
    profile_required = "profile_required"


class OperationKind(StrEnum):
    sync = "sync"
    resolve = "resolve"
    connect = "connect"
    clone = "clone"
    bundle_import = "bundle_import"


class OperationStatus(StrEnum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class OperationPhase(StrEnum):
    queued = "queued"
    snapshot = "snapshot"
    fetch = "fetch"
    merge = "merge"
    push = "push"
    download = "download"
    verify = "verify"
    register = "register"


class SyncOutcome(StrEnum):
    up_to_date = "up_to_date"
    pushed = "pushed"
    fast_forwarded = "fast_forwarded"
    merged = "merged"
    conflicts = "conflicts"


class AutoAction(StrEnum):
    take_theirs = "take_theirs"
    merged = "merged"
    delete = "delete"
    binary_newest = "binary_newest"


class SyncWarningCode(StrEnum):
    template_missing_after_merge = "template_missing_after_merge"
    unsafe_path = "unsafe_path"
    case_collision = "case_collision"
    signatures_stale = "signatures_stale"
    frozen_documents = "frozen_documents"
    team_foreign_edit = "team_foreign_edit"


class CloneWarningCode(StrEnum):
    template_missing = "template_missing"
    lfs_pointers = "lfs_pointers"


class SchemaAccess(StrEnum):
    full = "full"
    read_only = "read_only"
    files_only = "files_only"


class ProbeRelation(StrEnum):
    """Что лежит в удалённом репозитории относительно подключаемого проекта."""

    empty = "empty"
    studio_project = "studio_project"
    same_project = "same_project"
    same_project_unrelated_history = "same_project_unrelated_history"
    other_project = "other_project"
    not_studio_project = "not_studio_project"
    unknown = "unknown"


@dataclass(frozen=True)
class GitCredential:
    """Сохранённые учётные данные; секрет в сущность не входит."""

    id: UUID
    kind: GitCredentialKind
    label: str
    host: str
    username: str | None
    status: CredentialStatus
    created_at: datetime
    # Только префикс семейства токена (github_pat), не сам токен.
    token_family: str | None = None
    public_key: str | None = None
    fingerprint_sha256: str | None = None
    port: int | None = None
    last_used_at: datetime | None = None


@dataclass(frozen=True)
class CredentialUsage:
    """Проект, у которого к удалённому репозиторию привязан этот доступ."""

    project_id: UUID
    name: str


@dataclass(frozen=True)
class GitRemoteRef:
    """Подключённый к проекту удалённый репозиторий (адрес без секретов)."""

    display_url: str
    kind: RemoteKind
    host: str | None
    provider: GitProvider
    branch: str
    local_branch: str
    credential_id: UUID | None = None
    insecure_http: bool = False


@dataclass(frozen=True)
class RemoteTarget:
    """Куда и с каким доступом ходит сетевой git: адрес без секретов, доступ по идентификатору."""

    url: RemoteUrl
    credential_id: UUID | None = None
    # Явное согласие на открытый http: токен пойдёт по сети без шифрования.
    insecure_http: bool = False


@dataclass(frozen=True)
class GitHostKey:
    type: str
    fingerprint_sha256: str


@dataclass(frozen=True)
class ScannedHostKey:
    """Ключ, который хост предъявил при сканировании: пока ему никто не доверяет."""

    type: str
    # Блок ключа в base64, как в known_hosts.
    key: str
    fingerprint_sha256: str

    def public(self) -> GitHostKey:
        return GitHostKey(self.type, self.fingerprint_sha256)


@dataclass(frozen=True)
class GitOperationError:
    code: GitErrorCode
    detail: str


@dataclass(frozen=True)
class SyncAutoChange:
    path: str
    action: AutoAction
    copy_path: str | None = None


@dataclass(frozen=True)
class SyncWarning:
    code: SyncWarningCode | CloneWarningCode
    paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConflictCounts:
    files_total: int
    files_open: int


@dataclass(frozen=True)
class SyncResult:
    outcome: SyncOutcome
    pulled_commits: int = 0
    pushed_commits: int = 0
    merge_commit: str | None = None
    files_changed: int = 0
    auto: tuple[SyncAutoChange, ...] = ()
    conflicts: ConflictCounts | None = None
    warnings: tuple[SyncWarning, ...] = ()


@dataclass(frozen=True)
class CloneResult:
    project_id: UUID
    folder: str
    access: SchemaAccess
    required_studio: str | None = None
    warnings: tuple[SyncWarning, ...] = ()


@dataclass
class GitOperation:
    """Длительная операция (синхронизация, клонирование, импорт бандла). Живёт в памяти процесса."""

    id: str
    kind: OperationKind
    project_id: UUID | None
    started_at: datetime
    status: OperationStatus = OperationStatus.running
    phase: OperationPhase = OperationPhase.queued
    percent: float | None = None
    message: str | None = None
    cancellable: bool = True
    finished_at: datetime | None = None
    result: SyncResult | CloneResult | None = None
    error: GitOperationError | None = None


@dataclass(frozen=True)
class PendingSession:
    """Незавершённое слияние с конфликтами: рядом с хранилищем, дерево проекта не тронуто."""

    session_id: str
    files_total: int
    files_open: int


@dataclass(frozen=True)
class LastSync:
    id: str
    at: datetime
    outcome: SyncOutcome
    pulled_commits: int
    pushed_commits: int


@dataclass(frozen=True)
class LastError:
    code: GitErrorCode
    detail: str
    at: datetime


@dataclass(frozen=True)
class RemoteProbe:
    """Итог проверки адреса (probe): без записи в проект."""

    ok: bool
    reachable: bool = False
    auth_ok: bool = False
    empty: bool = False
    default_branch: str | None = None
    branches: tuple[str, ...] = ()
    relation: ProbeRelation = ProbeRelation.unknown
    error: GitOperationError | None = None
    host_keys: tuple[GitHostKey, ...] = ()
    schema_access: SchemaAccess | None = None
    required_studio: str | None = None
    template_available: bool | None = None


@dataclass(frozen=True)
class AuthorProfile:
    """Подпись автора коммитов этого человека на этой машине."""

    name: str
    email: str


@dataclass(frozen=True)
class GitResult:
    """Итог запуска git: stderr уже декодирован, секреты из него убирает вызывающий (scrub)."""

    returncode: int
    stdout: bytes = b""
    stderr: str = ""


@dataclass(frozen=True)
class SyncState:
    """Постоянное состояние синхронизации проекта (<git_dir>/hse-sync.json)."""

    local_branch: str
    remote_branch: str
    credential_id: UUID | None = None
    insecure_http: bool = False
    health: SyncHealth = SyncHealth.ok
    last_fetch_at: datetime | None = None
    last_fetch_ok_at: datetime | None = None
    last_error: LastError | None = None
    last_sync: LastSync | None = None
    pending: PendingSession | None = None
    auto_fetch: bool = True
    fetch_interval_s: int | None = None
    shared_folder_ack: bool = False
