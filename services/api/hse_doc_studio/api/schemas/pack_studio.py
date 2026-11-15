"""Схемы `/api/v1/pack-studio/*` и `/api/admin/pack-studio*` (docs/design/template-studio.md, раздел 12).

Эталоны лежат в `contracts/pack-studio/fixtures`, тест `tests/unit/contract/test_pack_studio_contract.py` сверяет их
с этими моделями. Форму меняют так: сначала эталоны, затем модели и клиент в одном коммите.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from hse_doc_studio.api.schemas.common import StrictModel

WorkspaceKindName = Literal["git", "folder"]
WorkspaceStateName = Literal["cloning", "ready", "failed"]
ReadOnlyReason = Literal["version_released", "releases_read_only"]
YamlOpName = Literal["set", "insert", "delete", "move"]
GrantSubjectName = Literal["user", "group"]
DiagnosticSeverityName = Literal["error", "warning"]
DiagnosticCheckName = Literal["lint", "schema"]
LintScopeName = Literal["version", "file", "none"]


class PackStudioErrorBody(BaseModel):
    """`{detail, code}` и поля по коду: `etag` и `content` у `stale_file`, `path` у `version_released`, `op` и
    `reason` у `yaml_patch_conflict`, `limit` у `file_too_large` и `workspace_limit`."""

    model_config = ConfigDict(extra="allow")

    detail: str
    code: str


class PackStudioSectionResponse(StrictModel):
    enabled: bool
    # Включение задано окружением или профилем standalone: переключатель только для чтения.
    locked: bool
    # Раздел открыт этому человеку: включён и есть право «Автор шаблонов».
    allowed: bool
    has_right: bool
    standalone: bool


class UpdatePackStudioSectionRequest(StrictModel):
    enabled: bool


class PackWorkspaceErrorBody(StrictModel):
    # Код из contracts/pack-studio/error_codes.json или contracts/git-sync/error_codes.json.
    code: str
    detail: str


class PackWorkspaceResponse(StrictModel):
    id: str
    kind: WorkspaceKindName
    label: str
    state: WorkspaceStateName
    # Идёт фоновая операция: клон или выборка базовой ветки.
    busy: bool
    packs_path: str
    url: str | None
    credential_id: str | None
    # Срез T6: пространство ходит служебным доступом репозитория (4.2), а не личным.
    service_access: bool
    insecure_http: bool
    # Папка для показа (путь хоста); только у `folder`.
    folder: str | None
    base_branch: str | None
    base_sha: str | None
    fetched_at: datetime | None
    # Срез T6: рабочая ветка, запрос на слияние, последняя сводка проверок (`CiStateName`), форк и отправленная вершина.
    work_branch: str | None
    pr_url: str | None
    pr_number: int | None
    ci_status: str | None
    fork_url: str | None
    pushed_sha: str | None
    error: PackWorkspaceErrorBody | None
    created_at: datetime
    updated_at: datetime
    # Срез T22: пространство над официальным репозиторием паков установки и когда человек принял его лицензию.
    official: bool = False
    license_accepted_at: datetime | None = None


class CreatePackWorkspaceRequest(StrictModel):
    kind: WorkspaceKindName
    label: str | None = Field(default=None, max_length=120)
    url: str | None = Field(default=None, max_length=2048)
    credential_id: UUID | None = None
    # Служебный доступ репозитория вместо личного (только сервер, его задаёт админ установки).
    service_access: bool = False
    insecure_http: bool = False
    base_branch: str | None = Field(default=None, max_length=255)
    folder: str | None = Field(default=None, max_length=4096)
    packs_path: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _source(self) -> CreatePackWorkspaceRequest:
        if self.kind == "git" and not (self.url or "").strip():
            raise ValueError("url is required for a git workspace")
        if self.kind == "folder" and not (self.folder or "").strip():
            raise ValueError("folder is required for a folder workspace")
        if self.service_access and (self.kind != "git" or self.credential_id is not None):
            raise ValueError("service_access is for a git workspace without credential_id")
        return self


class PackTreeVersion(StrictModel):
    version: str
    path: str
    status: str | None
    released: bool
    # Каталог выпущенной версии отличается от дайджеста в реестре: его правили мимо Студии.
    modified: bool


class PackTreeTemplate(StrictModel):
    id: str
    path: str
    name: dict[str, str] | None
    default_version: str | None
    versions: list[PackTreeVersion]


class PackTreePack(StrictModel):
    id: str
    path: str
    name: dict[str, str] | None
    templates: list[PackTreeTemplate]


class PackTreeFile(StrictModel):
    path: str
    is_dir: bool
    size: int
    read_only: ReadOnlyReason | None


class PackTreeResponse(StrictModel):
    workspace_id: str
    # Вершина базовой ветки, по реестрам которой отмечены выпущенные версии; у папки null.
    base_sha: str | None
    packs: list[PackTreePack]
    files: list[PackTreeFile]
    truncated: bool


class PackFileVersionResponse(StrictModel):
    path: str
    etag: str
    size: int


class PackYamlOp(StrictModel):
    """Точечная правка YAML: путь это ключи словарей (строки) и индексы списков (целые)."""

    op: YamlOpName
    path: list[StrictStr | StrictInt] = Field(max_length=64)
    value: Any = None
    # insert: место нового элемента; move: откуда.
    index: int | None = Field(default=None, ge=0)
    # move: куда (индекс в итоговом списке).
    to: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _fields(self) -> PackYamlOp:
        if self.op in {"insert", "move"} and self.index is None:
            raise ValueError(f"{self.op} needs index")
        if self.op == "move" and self.to is None:
            raise ValueError("move needs to")
        if self.op == "delete" and not self.path:
            raise ValueError("delete needs a path")
        return self


class PackYamlPatchRequest(StrictModel):
    ops: list[PackYamlOp] = Field(min_length=1, max_length=200)


class PackYamlPatchResponse(StrictModel):
    path: str
    etag: str
    size: int
    # Текст файла после правок: вкладка «Исходник» обновляется без второго запроса.
    content: str


class PackLintRequest(StrictModel):
    # Открытый файл или каталог версии, от папки паков пространства.
    path: str = Field(min_length=1, max_length=1024)


class PackDiagnosticResponse(StrictModel):
    severity: DiagnosticSeverityName
    check: DiagnosticCheckName
    message: str
    # Файл находки от папки паков; null: версия целиком (файл не определён).
    path: str | None
    # Строка с единицы, если её удалось найти.
    line: int | None
    # Путь в данных манифеста у находок схемы: `/meta_fields/year`.
    pointer: str | None


class PackLintResponse(StrictModel):
    scope: LintScopeName
    target: str | None
    released: bool
    errors: int
    warnings: int
    findings: list[PackDiagnosticResponse]


class PackMetaFieldHintResponse(StrictModel):
    key: str
    type: str | None
    label: dict[str, str] | None
    group: str | None


class PackMacroHintResponse(StrictModel):
    name: str
    keys: list[str]
    source: str


class PackEditorHintsResponse(StrictModel):
    # Каталог версии открытого файла; null: файл вне версии, подсказок нет.
    version: str | None
    meta_fields: list[PackMetaFieldHintResponse]
    macros: list[PackMacroHintResponse]


class PackStudioGrantResponse(StrictModel):
    id: str
    subject: GrantSubjectName
    subject_id: str
    # Человек: имя и почта; группа: название и её организация.
    name: str | None
    email: str | None
    org_slug: str | None
    org_name: str | None
    granted_by: str | None
    created_at: datetime


class PackStudioAdminResponse(StrictModel):
    enabled: bool
    locked: bool
    grants: list[PackStudioGrantResponse]


class UpdatePackStudioAdminRequest(StrictModel):
    enabled: bool


class CreatePackStudioGrantRequest(StrictModel):
    user_id: str | None = Field(default=None, min_length=1, max_length=64)
    group_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _one(self) -> CreatePackStudioGrantRequest:
        if (self.user_id is None) == (self.group_id is None):
            raise ValueError("exactly one of user_id and group_id")
        return self


# ── срез T6: git рабочего пространства ──────────────────────────────────────

ChangeStatusName = Literal["added", "modified", "deleted"]
GitProviderName = Literal["github", "gitlab", "gitea", "bitbucket", "hse_studio", "other"]
CiStateName = Literal["none", "pending", "awaiting_approval", "success", "failure", "unknown"]
CheckStateName = Literal[
    "queued", "running", "success", "failure", "neutral", "skipped", "cancelled", "awaiting_approval"
]
PullRequestStateName = Literal["open", "merged", "closed"]


class PackFileChange(StrictModel):
    # Путь от папки паков пространства.
    path: str
    status: ChangeStatusName


class PackGitResponse(StrictModel):
    """`GET /workspaces/{id}/git`: ветка, правки и PR. `branch` null: дерево на вершине базы без ветки."""

    workspace: PackWorkspaceResponse
    provider: GitProviderName
    head_sha: str
    branch: str | None
    base_branch: str | None
    # Правки на диске после последнего коммита; `dirty` это непустой список.
    uncommitted: list[PackFileChange]
    dirty: bool
    # Всё, чем пространство отличается от базы (коммиты и правки).
    changed: list[PackFileChange]
    ahead: int
    behind: int
    # Ветка отправлена, PR нет: ссылка «Открыть PR в браузере» (compare); иначе null.
    compare_url: str | None


class PackBranchRequest(StrictModel):
    """Создать или перейти на рабочую ветку; без имени Студия называет её сама (`pack-studio/<человек>/...`)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)


class PackCommitRequest(StrictModel):
    message: str | None = Field(default=None, max_length=2000)


class PackCommitResponse(StrictModel):
    git: PackGitResponse
    # Коммитить было нечего: null и `committed` false.
    sha: str | None
    committed: bool


class PackForkChoice(StrictModel):
    """Нет права push: свой форк по адресу или создать форк токеном (только GitHub)."""

    url: str | None = Field(default=None, max_length=2048)
    create: bool = False

    @model_validator(mode="after")
    def _one(self) -> PackForkChoice:
        if (self.url is None) == (not self.create):
            raise ValueError("exactly one of url and create")
        return self


class PackProposeRequest(StrictModel):
    # Заголовок PR или MR; без него сообщение по conventional commits из изменённых версий.
    title: str | None = Field(default=None, max_length=200)
    # Текст перед сводкой, которую Студия собирает сама (версии, класс, заметки, проверки).
    description: str | None = Field(default=None, max_length=20000)
    # Сообщение коммита несохранённых правок.
    message: str | None = Field(default=None, max_length=2000)
    fork: PackForkChoice | None = None
    # Срез T22: официальные паки, согласие с лицензией репозитория и публичностью вклада (нужно один раз).
    accept_license: bool = False


class PackPullRequest(StrictModel):
    number: int
    url: str
    # false: PR из этой ветки уже был открыт, найден существующий.
    created: bool


class PackCheckFinding(StrictModel):
    severity: Literal["error", "warning"]
    check: str
    path: str
    message: str


class PackVersionClass(StrictModel):
    path: str
    base: str
    minimum: str
    suggested: str
    by_number: str | None
    headline: dict[str, str]


class PackCheckSummary(StrictModel):
    errors: int
    warnings: int
    findings: list[PackCheckFinding]
    classes: list[PackVersionClass]


class PackProposeResponse(StrictModel):
    git: PackGitResponse
    pushed_sha: str
    # Куда ушла ветка: сам репозиторий или форк (адрес без секретов).
    pushed_to: str
    pull_request: PackPullRequest | None
    compare_url: str | None
    # Ветка отправлена, а PR открыть не дали: `{code: pr_permission_missing, detail}`; иначе null.
    pr_error: PackWorkspaceErrorBody | None
    checks: PackCheckSummary


class PackCiCheck(StrictModel):
    name: str
    state: CheckStateName
    url: str | None
    summary: str | None


class PackCiResponse(StrictModel):
    """`GET /workspaces/{id}/git/checks`: статус проверок хостинга по отправленной вершине."""

    state: CiStateName
    sha: str | None
    checks: list[PackCiCheck]
    # false: хостинг не отдаёт статус этому токену (GitLab без read_api, точный токен GitHub без прав) или провайдеру.
    available: bool
    reason: str | None
    web_url: str | None
    # Срез T22: открыт, слит или закрыт PR (null: PR нет или хостинг не сказал).
    pr_state: PullRequestStateName | None = None


class PackStartOverRequest(StrictModel):
    # Отбросить несохранённые правки; без него при правках `workspace_dirty`.
    discard: bool = False


class PackDiffResponse(StrictModel):
    diff: str
    truncated: bool


class PackServiceAccessResponse(StrictModel):
    id: str
    url: str
    label: str
    token_family: str | None
    created_by: str | None
    created_by_name: str | None
    created_at: datetime
    # Срез T22: доступ бота, push только в форк аккаунта токена (`fork_url`, null до первой проверки или отправки).
    fork_mode: bool = False
    fork_url: str | None = None


class CreatePackServiceAccessRequest(StrictModel):
    url: str = Field(min_length=1, max_length=2048)
    token: str = Field(min_length=1, max_length=4096)
    label: str | None = Field(default=None, max_length=120)
    fork_mode: bool = False


ServiceAccessProblemName = Literal[
    "token_rejected", "fine_grained_token", "scope_missing", "fork_unavailable", "bot_can_push", "provider_unsupported"
]


class PackServiceAccessCheckResponse(StrictModel):
    """`POST /api/admin/pack-studio/service-access/{id}/check`: проверка доступа у хостинга (срез T22)."""

    access: PackServiceAccessResponse
    ok: bool
    login: str | None
    # Области классического токена GitHub; null: хостинг их не назвал (точный токен).
    scopes: list[str] | None
    can_push: bool | None
    problems: list[ServiceAccessProblemName]


# ── срез T22: официальные паки ──────────────────────────────────────────────

OfficialAccessName = Literal["bot", "token"]
BotUnavailableName = Literal["local", "not_configured", "disabled", "no_right"]


class PackOfficialRepo(StrictModel):
    url: str
    web_url: str
    packs_path: str
    base_branch: str
    license: str
    license_url: str
    contributing_url: str


class PackOfficialBot(StrictModel):
    available: bool
    reason: BotUnavailableName | None
    daily_limit: int | None
    used: int | None


class PackOfficialResponse(StrictModel):
    """`GET /pack-studio/official`: официальный репозиторий паков установки (null: кнопки нет), доступ бота и уже
    созданное пространство человека."""

    repo: PackOfficialRepo | None
    bot: PackOfficialBot
    workspace_id: str | None


class OpenPackOfficialRequest(StrictModel):
    access: OfficialAccessName
    credential_id: UUID | None = None

    @model_validator(mode="after")
    def _token_needs_credential(self) -> OpenPackOfficialRequest:
        if (self.access == "token") != (self.credential_id is not None):
            raise ValueError("credential_id goes with access=token only")
        return self


class PackStudioOfficialAdminResponse(StrictModel):
    """`GET/PUT /api/admin/pack-studio/official`: вклад через бота (срез T22)."""

    repo: PackOfficialRepo | None
    bot_enabled: bool
    daily_limit: int
    default_daily_limit: int
    service_access: PackServiceAccessResponse | None


class UpdatePackStudioOfficialRequest(StrictModel):
    bot_enabled: bool
    daily_limit: int = Field(ge=1, le=1000)


# ── Предпросмотр (раздел 6, срез T7) ─────────────────────────────────────────

PreviewStatusName = Literal["queued", "running", "succeeded", "failed", "cancelled"]
PreviewExampleSource = Literal["file", "auto"]


class PackPreviewDocument(StrictModel):
    id: str
    name: dict[str, str]
    # Виды работы и составы, в которых документ есть: в остальных комбинациях его нет в проекте.
    kinds: list[str]
    staffing: list[str]


class PackPreviewSwitch(StrictModel):
    """Переключатель комбинации: `lang`, `kind`, `staffing`, `supervisor`, `co_supervisor`, `academic_supervisor`,
    `nda` и `meta.<поле>` (до пяти полей select и bool); у полей анкеты есть `label` из пака."""

    id: str
    values: list[str]
    default: str
    label: dict[str, str] | None


class PackPreviewExample(StrictModel):
    """Набор данных: файл `templates/<шаблон>/examples/<id>.yaml` или автонабор `auto:normal|long|empty`."""

    id: str
    source: PreviewExampleSource
    label: dict[str, str] | None
    # Файл не разобран: набор виден, но собрать по нему нельзя.
    error: str | None
    # Значения переключателей, которые предлагает сам набор (`lang`, `kind`, `staffing` в файле).
    defaults: dict[str, str]


class PackPreviewOptionsResponse(StrictModel):
    workspace_id: str
    # Папки версии в пространстве (как в дереве) и id из манифестов.
    pack: str
    template: str
    version: str
    pack_id: str
    template_id: str
    version_id: str
    documents: list[PackPreviewDocument]
    switches: list[PackPreviewSwitch]
    examples: list[PackPreviewExample]
    default_example: str
    # Полная комбинация по умолчанию для набора `default_example`.
    combination: dict[str, str]


class StartPackPreviewRequest(StrictModel):
    documents: list[str] = Field(min_length=1, max_length=8)
    # Нет: первый разобранный файл примера, иначе `auto:normal`.
    example: str | None = Field(default=None, max_length=255)
    # Недостающие переключатели берутся из набора, затем по умолчанию.
    combination: dict[str, str] = Field(default_factory=dict, max_length=32)


class PackPreviewErrorBody(StrictModel):
    # `render_failed`, `interrupted`, `pdf_missing` и коды сборки проекта (`build_failed`, `font_missing`,
    # `image_missing`, `docker_unavailable`, `no_runners`, `quota_exceeded`, ...).
    code: str
    detail: str | None


class PackPreviewBuildResponse(StrictModel):
    id: str
    workspace_id: str
    pack: str
    template: str
    version: str
    document: str
    example: str
    combination: dict[str, str]
    # Ключ кэша: одинаковый ключ значит тот же PDF.
    key: str
    status: PreviewStatusName
    # Ответ взят из кэша, сборки не было.
    cached: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    pages: int | None
    error: PackPreviewErrorBody | None
    # Исходник документа в синтетическом проекте (`report/report.tex`, у личного документа команды с папкой автора).
    source_file: str | None
    # Есть якоря мест подписей (`GET .../anchors`).
    has_anchors: bool


class PackPreviewStartResponse(StrictModel):
    builds: list[PackPreviewBuildResponse]
