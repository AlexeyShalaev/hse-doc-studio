"""Контракт Git-синхронизации: тела запросов и ответов всех эндпоинтов /git.

Источник правды для обеих сторон — contracts/git-sync (эталонные JSON и список кодов
ошибок). Контрактный тест проверяет, что эталоны проходят эти модели и возвращаются
из них без потерь, а такой же тест фронтенда разбирает те же файлы через zod.
Любое изменение формы сначала правит эталоны и оба набора тестов в одном коммите.

Перечислимые значения лежат строками: клиент обязан терпеть незнакомое значение от
более новой Студии. Допустимые значения перечислены в комментариях у полей.
Секреты (токены, пароли) возвращать нельзя: они только входят в запросы.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from hse_doc_studio.api.schemas.vcs import VcsCommitResponse


class _Contract(BaseModel):
    """Строгая основа: лишнее поле в теле считается ошибкой контракта."""

    model_config = ConfigDict(extra="forbid")


# --- ошибки ------------------------------------------------------------------


class GitCredentialUsage(_Contract):
    project_id: UUID
    name: str


class GitHostKey(_Contract):
    type: str
    fingerprint_sha256: str


class GitTlsCertificate(_Contract):
    """Сертификат, который предъявил сервер: по нему человек решает, добавить CA или закрепить отпечаток."""

    fingerprint_sha256: str
    subject: str
    issuer: str
    not_before: datetime
    not_after: datetime
    self_signed: bool


class GitProviderInfo(_Contract):
    """Что за сервер и как это узнали."""

    id: str  # github | gitlab | gitea | bitbucket | other
    detected_by: str  # override | host | api | unknown
    version: str | None  # версия сервера, если он её назвал


class GitTokenInfo(_Contract):
    """Что известно о токене после проверки: чей он, какие права, до какого срока."""

    login: str | None
    scopes: list[str]
    expires_at: datetime | None
    sufficiency: str  # sufficient | too_narrow | too_broad | unknown
    missing: list[str]  # каких прав не хватает для чтения и записи


class GitErrorBody(_Contract):
    """Тело ошибки: {detail, code} и дополнительные поля конкретного кода."""

    detail: str
    code: str
    operation_id: str | None = None  # sync_busy
    required_studio: str | None = None  # remote_schema_newer
    expected: str | None = None  # host_key_changed
    actual: str | None = None  # host_key_changed
    projects: list[GitCredentialUsage] | None = None  # credential_in_use
    can_adopt: bool | None = None  # unrelated_histories
    paths: list[str] | None = None  # unresolved_conflicts, invalid_resolution, unresolved_markers
    host_keys: list[GitHostKey] | None = None  # host_key_unknown
    missing: list[str] | None = None  # token_insufficient_scope
    certificate: GitTlsCertificate | None = None  # tls_untrusted_ca


class ProfileFieldError(_Contract):
    loc: list[str | int]
    code: str
    msg: str


class ProfileValidationError(_Contract):
    """422 на PUT /profile: стандартный список ошибок FastAPI с кодом правила."""

    detail: list[ProfileFieldError]


# --- профиль автора ----------------------------------------------------------


class ProfileResponse(_Contract):
    name: str | None
    email: str | None
    effective_name: str
    effective_email: str
    is_default: bool
    commit_preview: str


class ProfileRequest(_Contract):
    name: str
    email: str


# --- доступы, ключи серверов, секреты ---------------------------------------


class GitCredentialResponse(_Contract):
    id: UUID
    kind: str  # pat | ssh_key
    label: str
    host: str
    username: str | None
    status: str  # unverified | ok | auth_failed | unreadable
    token_family: str | None  # только префикс токена, например github_pat
    public_key: str | None
    fingerprint_sha256: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None  # срок токена, если известен
    used_by: list[GitCredentialUsage]


class GitCredentialCheckResponse(_Contract):
    """Итог кнопки «Проверить» у сохранённого токена; отказ сервера приходит ошибкой с кодом, а не этим ответом."""

    credential: GitCredentialResponse  # с обновлёнными сроком и статусом
    provider_info: GitProviderInfo
    token_info: GitTokenInfo | None  # None: у этого провайдера токен проверить нельзя


class CreatePatCredentialRequest(_Contract):
    kind: Literal["pat"]
    label: str
    host: str
    username: str | None = None
    token: str


class CreateSshCredentialRequest(_Contract):
    kind: Literal["ssh_key"]
    label: str
    host: str
    port: int | None = None


CreateCredentialRequest = Annotated[
    CreatePatCredentialRequest | CreateSshCredentialRequest,
    Field(discriminator="kind"),
]


class UpdateCredentialRequest(_Contract):
    """Пустой или отсутствующий token оставляет сохранённый."""

    label: str | None = None
    username: str | None = None
    token: str | None = None


class GitHostResponse(_Contract):
    host: str
    port: int | None
    key_types: list[str]
    fingerprints_sha256: list[str]
    added_at: datetime


class TrustHostRequest(_Contract):
    host: str
    port: int | None = None
    fingerprint_sha256: str
    replace: bool | None = None
    confirm_host: str | None = None


class GitHostSettingsResponse(_Contract):
    """Настройки сервера, общие для всех проектов: подмена провайдера, свой CA, закреплённый сертификат."""

    host: str
    port: int | None
    provider_override: str | None
    provider_info: GitProviderInfo
    ca_present: bool  # свой сертификат центра выдачи лежит в data_dir
    pinned_fingerprint: str | None  # SHA256:... закреплённого сертификата сервера


class UpdateGitHostSettingsRequest(_Contract):
    """Отсутствующее поле оставляет значение, null сбрасывает его; ca_pem принимает только PEM сертификата."""

    host: str
    port: int | None = None
    provider_override: str | None = None
    ca_pem: str | None = None
    pinned_fingerprint: str | None = None


class SharedFolderInfo(_Contract):
    provider: str
    root: str


class SecretsStatusResponse(_Contract):
    ok: bool
    source: str  # file | env
    permissions_enforced: bool
    credentials_total: int
    credentials_unreadable: int
    data_dir_shared_folder: SharedFolderInfo | None


class SharedFolderResponse(_Contract):
    detected: bool
    # yandex_disk | dropbox | syncthing | onedrive | google_drive | icloud | nextcloud | unknown
    provider: str | None
    root: str | None
    evidence: list[str]


# --- проверка адреса ---------------------------------------------------------


class ProbeRequest(_Contract):
    url: str
    credential_id: UUID | None = None
    project_id: UUID | None = None
    branch: str | None = None


class ProbeError(_Contract):
    code: str
    detail: str
    host_keys: list[GitHostKey] | None = None
    certificate: GitTlsCertificate | None = None  # tls_untrusted_ca
    expected: str | None = None  # tls_pin_mismatch: закреплённый отпечаток
    actual: str | None = None  # tls_pin_mismatch: отпечаток, который сервер предъявил сейчас


class ProbeUrl(_Contract):
    display_url: str  # без userinfo
    kind: str  # https | ssh | file | http
    host: str | None
    provider: str  # github | gitlab | gitea | bitbucket | other
    owner: str | None
    repo: str | None
    token_stripped: bool


class ProbeProject(_Contract):
    id: UUID
    name: str
    pack_id: str
    template_id: str
    template_version: str
    kind: str
    staffing: str
    authors_count: int


class ProbeResponse(_Contract):
    ok: bool
    error: ProbeError | None
    url: ProbeUrl
    provider_info: GitProviderInfo  # url.provider совпадает с provider_info.id
    token_info: GitTokenInfo | None  # только для проверки с токеном
    reachable: bool
    auth_ok: bool
    empty: bool
    default_branch: str | None
    branches: list[str]
    # empty | studio_project | same_project | same_project_unrelated_history
    # | other_project | not_studio_project | unknown
    relation: str
    project: ProbeProject | None
    schema_access: str | None  # full | read_only | files_only
    required_studio: str | None
    template_available: bool | None


# --- операции ----------------------------------------------------------------


class OperationStartedResponse(_Contract):
    operation_id: str


class OperationWarning(_Contract):
    # template_missing_after_merge | unsafe_path | case_collision | signatures_stale
    # | frozen_documents | team_foreign_edit | template_missing | lfs_pointers
    code: str
    paths: list[str]


class AutoMergedFile(_Contract):
    path: str
    action: str  # take_theirs | merged | delete | binary_newest
    copy_path: str | None


class ConflictCounts(_Contract):
    files_total: int
    files_open: int


class SyncResult(_Contract):
    outcome: str  # up_to_date | pushed | fast_forwarded | merged | conflicts
    pulled_commits: int
    pushed_commits: int
    merge_commit: str | None
    files_changed: int
    auto: list[AutoMergedFile]  # не больше 200
    conflicts: ConflictCounts | None
    warnings: list[OperationWarning]


class CloneResult(_Contract):
    project_id: UUID
    folder: str
    access: str  # full | read_only | files_only
    required_studio: str | None
    warnings: list[OperationWarning]


class OperationError(_Contract):
    code: str
    detail: str


class OperationResponse(_Contract):
    id: str
    kind: str  # sync | resolve | connect | clone | bundle_import
    project_id: UUID | None
    status: str  # running | succeeded | failed | cancelled
    # queued | snapshot | fetch | merge | push | download | verify | register
    phase: str
    percent: float | None
    message: str | None
    cancellable: bool
    started_at: datetime
    finished_at: datetime | None
    result: SyncResult | CloneResult | None
    error: OperationError | None


class CloneRequest(_Contract):
    url: str
    credential_id: UUID | None = None
    branch: str | None = None
    folder: str
    name: str | None = None


class CloneDefaultsResponse(_Contract):
    folder: str


# --- состояние проекта -------------------------------------------------------


class GitCommitBrief(_Contract):
    id: str
    short_id: str
    message: str
    author: str
    author_email: str | None
    created_at: datetime
    kind: str


class GitRemoteCredentialRef(_Contract):
    id: UUID
    label: str
    kind: str


class GitRemoteInfo(_Contract):
    display_url: str
    kind: str
    host: str | None
    provider: str
    provider_info: GitProviderInfo
    web_url: str | None
    branch: str  # ветка на сервере
    local_branch: str
    credential: GitRemoteCredentialRef | None
    insecure_http: bool


class GitLastError(_Contract):
    code: str
    detail: str
    at: datetime


class GitBlocked(_Contract):
    # off_branch | read_only | remote_schema_newer | store_untrusted | profile_required
    reason: str
    required_studio: str | None


class GitStatusOperation(_Contract):
    id: str
    kind: str
    phase: str
    percent: float | None
    cancellable: bool
    started_at: datetime


class GitPending(_Contract):
    session_id: str
    files_total: int
    files_open: int


class GitLastSync(_Contract):
    id: str
    at: datetime
    outcome: str
    pulled_commits: int
    pushed_commits: int


class GitAutoFetch(_Contract):
    enabled: bool
    interval_s: int
    next_fetch_at: datetime | None


class GitSharedFolder(_Contract):
    provider: str
    root: str
    acknowledged: bool


class GitStatusResponse(_Contract):
    connected: bool
    # no_remote | unfetched | up_to_date | ahead | behind | diverged | syncing | conflicts
    # | auth_failed | offline | error | blocked
    ui_state: str
    remote: GitRemoteInfo | None
    # none | unfetched | remote_empty | in_sync | ahead | behind | diverged
    relation: str
    ahead: int
    behind: int
    behind_files: int
    # ok | unauthenticated | offline | error | host_key_changed | remote_missing | branch_missing
    health: str
    last_error: GitLastError | None
    blocked: GitBlocked | None
    profile_ok: bool
    incoming: list[GitCommitBrief]  # не больше 5
    outgoing: list[GitCommitBrief]  # не больше 5
    operation: GitStatusOperation | None
    pending: GitPending | None
    last_fetch_at: datetime | None
    last_fetch_ok_at: datetime | None
    last_sync_at: datetime | None
    last_sync: GitLastSync | None
    auto_fetch: GitAutoFetch
    shared_folder: GitSharedFolder | None
    bot_authored_commits: int


class ConnectRemoteRequest(_Contract):
    url: str
    credential_id: UUID | None
    branch: str | None = None  # локальная
    remote_branch: str | None = None
    adopt: str | None = None  # null | merge_remote
    insecure_http: bool | None = None


class UpdateGitSettingsRequest(_Contract):
    auto_fetch: bool | None = None
    interval_s: int | None = None
    shared_folder_ack: bool | None = None


class GitLargestFile(_Contract):
    path: str
    bytes: int


class GitOverLimitFile(_Contract):
    path: str
    bytes: int
    limit: int


class GitContentsResponse(_Contract):
    files: int
    bytes: int
    commits: int
    bot_authored_commits: int
    signatures: int
    nda_files: int
    pdf_tracked: bool
    largest: list[GitLargestFile]  # пять самых крупных
    over_limit: list[GitOverLimitFile]  # блобы от 95 МБ в истории
    lfs_pointers: int


# --- конфликты ---------------------------------------------------------------


class ConflictSide(_Contract):
    """Сторона сессии: коммит и его автор."""

    commit: str
    author: str | None
    at: datetime | None
    message: str | None


class ConflictFileSide(_Contract):
    """Сторона одного файла."""

    exists: bool
    size: int | None
    author: str | None
    at: datetime | None


class ConflictFileSides(_Contract):
    ours: ConflictFileSide
    theirs: ConflictFileSide
    base: ConflictFileSide


class ConflictSessionCounts(_Contract):
    conflict: int
    auto: int
    total: int


class HunkChoice(_Contract):
    choice: str  # mine | theirs | both | both_reverse | base | custom
    text: str | None = None  # для custom


class FieldChoice(_Contract):
    choice: str  # mine | theirs | union


class FileChoiceResolution(_Contract):
    kind: Literal["file"]
    choice: str  # mine | theirs | newest


class HunksResolution(_Contract):
    kind: Literal["hunks"]
    hunks: dict[str, HunkChoice]


class FieldsResolution(_Contract):
    kind: Literal["fields"]
    fields: dict[str, FieldChoice]


class TextResolution(_Contract):
    kind: Literal["text"]
    content: str


FileResolution = Annotated[
    FileChoiceResolution | HunksResolution | FieldsResolution | TextResolution,
    Field(discriminator="kind"),
]


FileResolutionBody = FileChoiceResolution | HunksResolution | FieldsResolution | TextResolution


class ConflictFile(_Contract):
    path: str
    owner: str | None
    kind: str  # text | json | binary
    # conflict | binary_newest | merged | take_theirs | delete
    action: str
    # null | content | fields | deleted_by_us | deleted_by_them | add_add | binary
    # | signature_group | case_collision | invalid_result
    conflict_type: str | None
    hunks: int
    open_hunks: int
    fields: int
    open_fields: int
    resolved: bool
    resolution: FileResolution | None  # сохранённый черновик
    allowed: list[str]  # mine | theirs | newest
    default_resolution: str | None
    sides: ConflictFileSides
    copy_path: str | None
    doc_id: str | None


class ConflictSessionResponse(_Contract):
    id: str
    fingerprint: str
    ours: ConflictSide
    theirs: ConflictSide
    base: ConflictSide | None
    counts: ConflictSessionCounts
    unresolved: int
    drafts_saved_at: datetime | None
    warnings: list[OperationWarning]
    files: list[ConflictFile]


class TextCleanSegment(_Contract):
    type: Literal["clean"]
    lines: list[str]


class TextHunkSegment(_Contract):
    type: Literal["hunk"]
    key: str
    ours: list[str]
    base: list[str]
    theirs: list[str]
    ours_start: int
    result_start: int


class TextFileDetail(_Contract):
    kind: Literal["text"]
    eol: str  # lf | crlf
    truncated: bool
    segments: list[Annotated[TextCleanSegment | TextHunkSegment, Field(discriminator="type")]]


class JsonFieldConflict(_Contract):
    pointer: str
    label: str | None
    type: str  # scalar | list | record | presence
    base: JsonValue
    ours: JsonValue
    theirs: JsonValue
    allowed: list[str]  # mine | theirs | union
    status: str  # auto | conflict


class JsonFileDetail(_Contract):
    kind: Literal["json"]
    fields: list[JsonFieldConflict]


class BinaryFileDetail(_Contract):
    kind: Literal["binary"]
    ours: ConflictFileSide
    theirs: ConflictFileSide
    newer: str  # ours | theirs
    copy_path: str | None


class DeleteFileDetail(_Contract):
    kind: Literal["delete"]
    deleted_by: str  # ours | theirs


ConflictFileDetailBody = TextFileDetail | JsonFileDetail | BinaryFileDetail | DeleteFileDetail
ConflictFileDetail = Annotated[ConflictFileDetailBody, Field(discriminator="kind")]


class ConflictDiffResponse(_Contract):
    path: str
    binary: bool
    patch: str
    truncated: bool


class SaveConflictDraftRequest(_Contract):
    resolutions: dict[str, FileResolution]


class ResolveConflictsRequest(_Contract):
    fingerprint: str
    resolutions: dict[str, FileResolution] | None = None  # None: взять черновики
    push: bool


# --- CI ----------------------------------------------------------------------


class CiRequest(_Contract):
    provider: str  # github | gitlab
    docs: Literal["all"] | list[str]
    publish: str  # artifacts | release
    triggers: list[str]  # push | tag | manual
    image: str | None = None


class CiWriteRequest(CiRequest):
    overwrite: bool


class CiFile(_Contract):
    path: str
    content: str
    exists: bool
    same: bool


class CiPreviewResponse(_Contract):
    files: list[CiFile]
    command: str
    notes: list[str]


class CiWriteResponse(_Contract):
    written: list[str]


# --- история -----------------------------------------------------------------


class HistoryCommitResponse(VcsCommitResponse):
    """Коммит истории с признаками синхронизации."""

    model_config = ConfigDict(extra="forbid")

    author_email: str | None
    is_merge: bool
    sync: str | None  # pushed | unpushed | incoming, без репозитория null


class HistoryAuthorFacet(_Contract):
    name: str
    email: str | None
    count: int


class HistoryFacetsResponse(_Contract):
    kinds: dict[str, int]
    authors: list[HistoryAuthorFacet]
