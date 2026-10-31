"""Сущности Git-синхронизации.

Значения перечислений совпадают со строками контракта (contracts/git-sync). Секретов здесь нет:
токены и закрытые ключи живут только за портами ISecretCipher и IGitCredentialRepository.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.merge.choices import FileResolution
from hse_doc_studio.core.git_sync.providers import GitProvider, Sufficiency
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl


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
    # Срок токена, если сервер его назвал при проверке; для ключей None.
    expires_at: datetime | None = None
    # `device`: токен сервера HSE Doc Studio, полученный входом по коду; иначе введён человеком.
    origin: str | None = None


@dataclass(frozen=True)
class CredentialUsage:
    """Проект, у которого к удалённому репозиторию привязан этот доступ."""

    project_id: UUID
    name: str


@dataclass(frozen=True)
class RemoteBinding:
    """Привязка доступа к проекту: для какой схемы, хоста и порта владелец разрешил им пользоваться."""

    project_id: UUID
    credential_id: UUID
    bound_by: str | None
    scheme: str
    host: str
    port: int | None


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
    # Проект, чей это удалённый репозиторий: по нему сервер находит привязку доступа.
    project_id: UUID | None = None


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
    # Ключ актора, начавшего операцию (`Actor.key`); None в локальном режиме и без запроса.
    # Другим акторам операция не видна.
    owner: str | None = None


@dataclass(frozen=True)
class PendingSession:
    """Незавершённое слияние с конфликтами: рядом с хранилищем, дерево проекта не тронуто."""

    session_id: str
    files_total: int
    files_open: int
    # Коммиты, между которыми шло слияние: по ним план пересобирается из объектов хранилища.
    ours: str | None = None
    theirs: str | None = None
    base: str | None = None
    # Отпечаток конфликтных файлов: пока он тот же, повторная синхронизация оставляет ту же сессию.
    fingerprint: str | None = None
    # Черновики решений человека по путям: участки и поля в них названы ключами, а не номерами, поэтому
    # переживают пересчёт плана.
    drafts: Mapping[str, FileResolution] = field(default_factory=dict)
    drafts_saved_at: datetime | None = None
    # Откуда пришла чужая сторона, если не с сервера: ветка из переносного файла (`refs/hse/bundle/<ветка>`).
    # Без неё слияние идёт с отслеживаемой веткой удалённого репозитория.
    theirs_ref: str | None = None


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
class TlsCertificate:
    """Сертификат сервера для показа человеку: по нему решают, добавить CA или закрепить отпечаток."""

    fingerprint_sha256: str
    subject: str
    issuer: str
    not_before: datetime
    not_after: datetime
    self_signed: bool


@dataclass(frozen=True)
class ServerCertificate(TlsCertificate):
    """Сертификат, который сервер предъявил на самом деле; PEM нужен для закрепления и наружу не отдаётся."""

    pem: str

    def public(self) -> TlsCertificate:
        return TlsCertificate(
            self.fingerprint_sha256, self.subject, self.issuer, self.not_before, self.not_after, self.self_signed
        )


class TokenState(StrEnum):
    """Что сервер сказал о токене: годен, не принят, истёк или проверить нельзя (старый сервер, узкий токен)."""

    valid = "valid"
    rejected = "rejected"
    expired = "expired"
    unknown = "unknown"


@dataclass(frozen=True)
class TokenIntrospection:
    """Ответ сервера о токене: владелец, права (None: сервер их не назвал) и срок."""

    state: TokenState
    login: str | None = None
    scopes: tuple[str, ...] | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class TokenInfo:
    """Что известно о токене после проверки и хватает ли его для чтения и записи."""

    login: str | None
    scopes: tuple[str, ...]
    expires_at: datetime | None
    sufficiency: Sufficiency
    missing: tuple[str, ...] = ()


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
    certificate: TlsCertificate | None = None
    # tls_pin_mismatch: закреплённый отпечаток и тот, что сервер предъявил сейчас.
    expected_fingerprint: str | None = None
    actual_fingerprint: str | None = None
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
class PdfUploadRecord:
    """Итог последней выгрузки PDF на сервер Студии (docs/design/local-sync.md, P7)."""

    doc_id: str
    at: datetime
    ok: bool
    size: int | None = None
    code: str | None = None
    detail: str | None = None


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
    # Удалённый репозиторий был пуст при подключении и с тех пор не получал изменений: отправка первая.
    remote_empty: bool = False
    # Человек согласился слить с удалённым проектом, у которого нет общей истории с локальным.
    adopted_unrelated: bool = False
    # На конце удалённой ветки проект записан более новой Студией: данные нельзя ни читать, ни писать.
    remote_schema_newer: bool = False
    remote_required_studio: str | None = None
    # Автосинхронизация окна Студии; None значит «по умолчанию» (включена для проектов с сервера Студии).
    auto_sync: bool | None = None
    # Выгрузка PDF после локальной сборки; None: по умолчанию включена для проектов с сервера Студии.
    pdf_upload: bool | None = None
    last_pdf_upload: PdfUploadRecord | None = None


@dataclass(frozen=True)
class StoreRemoteConfig:
    """Подключение, записанное в config хранилища: то, что нужно самому git и сопровождает папку при переносе."""

    url: str
    credential_id: UUID | None = None
    local_branch: str | None = None
    remote_branch: str | None = None


@dataclass(frozen=True)
class TreeEntry:
    """Файл или gitlink в дереве коммита. `size` есть только у blob."""

    path: str
    mode: str
    kind: str
    sha: str
    size: int | None = None


@dataclass(frozen=True)
class CommitBrief:
    """Коротко о коммите для списков «пришло» и «уйдёт»: автор как записан в истории."""

    id: str
    short_id: str
    message: str
    author: str
    author_email: str | None
    created_at: datetime
    kind: str


@dataclass(frozen=True)
class LargeBlob:
    path: str
    sha: str
    size: int


@dataclass(frozen=True)
class AuthorCount:
    name: str
    email: str
    commits: int


@dataclass(frozen=True)
class PathStamp:
    """Последнее изменение файла: время коммита и его sha, пара определяет «новее» без ничьих."""

    committed_at: datetime
    sha: str


class SharedFolderProvider(StrEnum):
    """Служба синхронизации папок, в которой лежит проект."""

    yandex_disk = "yandex_disk"
    dropbox = "dropbox"
    syncthing = "syncthing"
    onedrive = "onedrive"
    google_drive = "google_drive"
    icloud = "icloud"
    nextcloud = "nextcloud"
    unknown = "unknown"


@dataclass(frozen=True)
class SharedFolderInfo:
    """Папка внутри синхронизируемого каталога: путь в терминах хозяина машины, как его знает пользователь."""

    provider: SharedFolderProvider
    root: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class ContentsFile:
    path: str
    bytes: int


@dataclass(frozen=True)
class RepoContents:
    """Что уйдёт в удалённый репозиторий: отслеживаемые файлы и история ветки проекта."""

    files: int
    bytes: int
    commits: int
    bot_authored_commits: int
    signatures: int
    nda_files: int
    pdf_tracked: bool
    largest: tuple[ContentsFile, ...]
    # Блобы истории от `limit_bytes`: хостинги отклоняют файлы около 100 МБ.
    over_limit: tuple[ContentsFile, ...]
    limit_bytes: int
    lfs_pointers: int


class StoreFindingKind(StrEnum):
    config_key = "config_key"
    config_value = "config_value"
    config_unreadable = "config_unreadable"
    hook = "hook"


@dataclass(frozen=True)
class StoreFinding:
    """Недоверенная настройка хранилища. `subject` называет ключ или хук, но не значение: в нём бывают секреты."""

    kind: StoreFindingKind
    subject: str


@dataclass(frozen=True)
class StoreAudit:
    findings: tuple[StoreFinding, ...] = ()

    @property
    def trusted(self) -> bool:
        return not self.findings
