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
from hse_doc_studio.api.schemas.signature import PackDateEntry, PackPlaceEntry, PlaceAnchorResponse
from hse_doc_studio.core.enums import DateMarkAlign, DateMarkFormat

WorkspaceKindName = Literal["git", "folder"]
WorkspaceStateName = Literal["cloning", "ready", "failed"]
ReadOnlyReason = Literal["version_released", "releases_read_only"]
YamlOpName = Literal["set", "insert", "delete", "move"]
GrantSubjectName = Literal["user", "group"]
DiagnosticSeverityName = Literal["error", "warning"]
DiagnosticCheckName = Literal["lint", "schema", "outcome"]
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
    # Новая ветка от свежей базовой, а не от текущей вершины (после слияния PR): дерево чистое (`workspace_dirty`),
    # имя свободно (`branch_exists`). По умолчанию ветка создаётся на текущей вершине, как раньше.
    from_base: bool = False


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


class CreatePackServiceAccessRequest(StrictModel):
    url: str = Field(min_length=1, max_length=2048)
    token: str = Field(min_length=1, max_length=4096)
    label: str | None = Field(default=None, max_length=120)


ServiceAccessProblemName = Literal["token_rejected", "cannot_push", "provider_unsupported"]


class PackServiceAccessCheckResponse(StrictModel):
    """`POST /api/admin/pack-studio/service-access/{id}/check`: проверка доступа у хостинга."""

    access: PackServiceAccessResponse
    ok: bool
    login: str | None
    # Области классического токена GitHub; null: хостинг их не назвал (точный токен).
    scopes: list[str] | None
    can_push: bool | None
    problems: list[ServiceAccessProblemName]


# ── срез T22: официальные паки ──────────────────────────────────────────────


class PackOfficialRepo(StrictModel):
    url: str
    web_url: str
    packs_path: str
    base_branch: str
    license: str
    license_url: str
    contributing_url: str


class PackOfficialResponse(StrictModel):
    """`GET /pack-studio/official`: официальный репозиторий паков установки (null: кнопки нет) и уже созданное
    пространство человека."""

    repo: PackOfficialRepo | None
    workspace_id: str | None


class OpenPackOfficialRequest(StrictModel):
    """Вклад в официальные паки только своим аккаунтом: личный доступ git человека к хосту репозитория."""

    credential_id: UUID


class PackStudioOfficialAdminResponse(StrictModel):
    """`GET /api/admin/pack-studio/official`: официальный репозиторий из окружения установки (null: кнопки нет)."""

    repo: PackOfficialRepo | None


# ── Предпросмотр (раздел 6, срез T7) ─────────────────────────────────────────

PreviewStatusName = Literal["queued", "running", "succeeded", "failed", "cancelled"]
PreviewExampleSource = Literal["file", "auto"]


class PackPreviewVariant(StrictModel):
    """Вариант документа для выбора при сборке (срез O9, `variant` запроса)."""

    id: str
    label: dict[str, str]
    # Языки проекта, в которых вариант доступен; пусто: во всех (IEEE и ISO-редакции только для en).
    langs: list[str]
    # Из варианта выходит PDF предпросмотра: есть движок, либо исходник офисный (PowerPoint, конвертация) или PDF.
    # У RevealJS (HTML) PDF нет, сборка кончится `pdf_missing`.
    pdf: bool


class PackPreviewDocument(StrictModel):
    id: str
    name: dict[str, str]
    # Виды работы и составы, в которых документ есть: в остальных комбинациях его нет в проекте.
    kinds: list[str]
    staffing: list[str]
    # Языки редакций документа: его `supported_langs`, иначе все языки версии (срез O9).
    langs: list[str] = Field(default_factory=list)
    # Варианты документа в порядке манифеста (пусто: вариантов нет) и вариант по умолчанию, первый (срез O9).
    variants: list[PackPreviewVariant] = Field(default_factory=list)
    default_variant: str | None = None


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
    # Прогнать правила проверок версии на собранном документе (срез T14): находки в `checks` сборки.
    checks: bool = False
    # Вариант документа (срез O9): у запроса ровно с одним документом; нет: вводная `variant.<документ>` сценария,
    # иначе первый вариант. Вариант, которого нет или который не доступен при языке комбинации, это `preview_invalid`.
    variant: str | None = Field(default=None, max_length=255)
    # Сценарий пака (срез O9): вводные и набор данных берёт из него (набор запроса главнее), `combination` ложится
    # поверх. Нет файла: `scenario_not_found`, файл не по формату: `scenario_invalid`.
    scenario: str | None = Field(default=None, max_length=64)
    # Автор команды, чьи личные документы собирать: слаг автора синтетического проекта (`authors` сборки) или номер
    # с единицы («2»: второй автор). Нет: первый автор. Общему документу и одиночной работе выбор безразличен;
    # автора с таким слагом или номером нет в комбинации: `preview_invalid` с полем `author`.
    author: str | None = Field(default=None, min_length=1, max_length=64)


class PackPreviewErrorBody(StrictModel):
    # `render_failed`, `interrupted`, `pdf_missing` и коды сборки проекта (`build_failed`, `font_missing`,
    # `image_missing`, `docker_unavailable`, `no_runners`, `quota_exceeded`, ...).
    code: str
    detail: str | None


class PackPreviewCheck(StrictModel):
    """Находка проверки на сборке предпросмотра: правило, важность, текст и место в синтетическом проекте."""

    rule_id: str
    severity: str
    message: str
    file: str | None
    line: int | None


class PackPreviewAuthor(StrictModel):
    """Автор команды синтетического проекта сборки: слаг (папка автора, якорь `author__<слаг>`) и имя из набора."""

    slug: str
    name: str


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
    # Сборка с проверками правил версии (срез T14); `checks` находки удачной сборки, null: проверок не было.
    with_checks: bool = False
    checks: list[PackPreviewCheck] | None = None
    # Что вышло из запроса (срез O9): выбранный вариант документа (null: вариантов нет), итоговое имя файла в
    # пакете, сценарий и его вводные как в файле (до наложения `combination`).
    variant: str | None = None
    file_name: str | None = None
    scenario: str | None = None
    scenario_inputs: dict[str, str] = Field(default_factory=dict)
    # Чей личный документ команды собран: слаг автора (null: общий документ или одиночная работа) и авторы команды
    # синтетического проекта по порядку: любого из них можно назвать в `author` следующего запроса.
    author: str | None = None
    authors: list[PackPreviewAuthor] = Field(default_factory=list)


class PackPreviewStartResponse(StrictModel):
    builds: list[PackPreviewBuildResponse]


# ── Срез T10: мастер «Новая версия» ─────────────────────────────────────────

UpdateClassName = Literal["patch", "minor", "major"]


class PackLocalizedList(StrictModel):
    """Пункты по языкам: списки ru и en параллельны (`pack_lint`)."""

    ru: list[StrictStr] = Field(default_factory=list, max_length=50)
    en: list[StrictStr] = Field(default_factory=list, max_length=50)


class PackVersionNumbers(StrictModel):
    """Номер по классу: свободный, после последней известной версии (на диске и в базовой ветке)."""

    patch: str | None
    minor: str | None
    major: str | None


class PackVersionChoice(StrictModel):
    version: str
    status: str | None
    released: bool
    registered: bool
    modified: bool


class PackVersionOptionsResponse(StrictModel):
    pack: str
    template: str
    versions: list[PackVersionChoice]
    default_base: str | None
    default_version: str | None
    numbers: PackVersionNumbers


class CreatePackVersionRequest(StrictModel):
    # База копии: по умолчанию последняя выпущенная.
    base: StrictStr | None = Field(default=None, max_length=64)
    # Номер явно или по классу (по умолчанию patch).
    version: StrictStr | None = Field(default=None, max_length=64)
    update_class: UpdateClassName | None = None


class PackVersionRef(StrictModel):
    pack: str
    template: str
    version: str
    path: str


class PackVersionCreatedResponse(StrictModel):
    version: PackVersionRef
    base: str
    update_class: UpdateClassName | None
    warnings: list[str]


class PackVersionReason(StrictModel):
    code: str
    path: str
    change: str
    minimum: UpdateClassName
    suggested: UpdateClassName
    hard: bool
    exception: bool
    message: dict[str, str]


class PackVersionStateResponse(StrictModel):
    version: PackVersionRef
    status: str | None
    released: bool
    modified: bool
    registered: bool
    release_outdated: bool
    is_default: bool
    base: str | None
    minimum: UpdateClassName | None
    suggested: UpdateClassName | None
    by_number: UpdateClassName | None
    declared: UpdateClassName | None
    note: str | None
    number_ok: bool
    headline: dict[str, str]
    reasons: list[PackVersionReason]
    numbers: PackVersionNumbers
    changes: PackLocalizedList
    breaking_changes: PackLocalizedList
    draft_changes: PackLocalizedList
    draft_breaking: PackLocalizedList
    move_to: str | None
    error: str | None


class PackVersionNotesRequest(StrictModel):
    """Поле не передано или null: не менять. Пустая `note` убирает объяснение класса."""

    changes: PackLocalizedList | None = None
    breaking_changes: PackLocalizedList | None = None
    note: StrictStr | None = Field(default=None, max_length=2000)


class PackRenumberRequest(StrictModel):
    version: StrictStr = Field(min_length=1, max_length=64)


class PackMoveEditsRequest(StrictModel):
    # Без номера: следующий свободный того же класса, что у номера выпущенной версии.
    version: StrictStr | None = Field(default=None, max_length=64)


class PackVersionMovedResponse(StrictModel):
    version: PackVersionRef
    previous: str
    unreleased: bool
    restored: bool


class PackReleaseRequest(StrictModel):
    # Класс выпуска (`release.kind`): по умолчанию по номеру; мягче минимума нельзя.
    kind: UpdateClassName | None = None
    set_default: bool = False


class PackReleaseResponse(StrictModel):
    version: PackVersionRef
    digest: str
    kind: UpdateClassName | None
    previous: str | None
    replaced: bool
    default_set: bool
    edited: list[str]
    warnings: list[str]


# ── Места подписей на PDF предпросмотра (5.6, срез T9) ───────────────────────

PlaceOpName = Literal[
    "set_place", "remove_place", "make_default", "bind_anchor", "unbind_anchor", "add_date", "set_date", "remove_date"
]
FrameKindName = Literal["place", "default"]
_MM_LIMIT = 1000.0


class PackPlaceBox(StrictModel):
    """Рамка подписи на странице, мм от левого верхнего угла."""

    page: int = Field(ge=1, le=10000)
    x_mm: float = Field(ge=-_MM_LIMIT, le=_MM_LIMIT)
    y_mm: float = Field(ge=-_MM_LIMIT, le=_MM_LIMIT)
    width_mm: float = Field(gt=0, le=_MM_LIMIT)


class PackMarkBox(StrictModel):
    """Рамка метки даты, формат и выравнивание."""

    page: int = Field(ge=1, le=10000)
    x_mm: float = Field(ge=-_MM_LIMIT, le=_MM_LIMIT)
    y_mm: float = Field(ge=-_MM_LIMIT, le=_MM_LIMIT)
    width_mm: float = Field(gt=0, le=_MM_LIMIT)
    height_mm: float = Field(gt=0, le=_MM_LIMIT)
    format: DateMarkFormat
    align: DateMarkAlign = DateMarkAlign.centered


class PackIndexedDate(StrictModel):
    """Метка даты пака с индексом в списке `default_dates` документа (битые метки пропущены, индексы не сдвинуты)."""

    index: int
    entry: PackDateEntry


class PackFrameDate(StrictModel):
    index: int
    entry: PackDateEntry
    # Рамка в этой сборке; null: метки нет (строки даты нет в сборке, у якоря нет запасной метки).
    box: PackMarkBox | None
    anchor: PlaceAnchorResponse | None


class PackSlotFrame(StrictModel):
    """Место слота на документе сборки: своя запись документа (`place`) или общее место слота (`default`)."""

    kind: FrameKindName
    entry: PackPlaceEntry
    # Рамка по якорям сборки; null: места нет (строки шаблона нет в этой сборке).
    box: PackPlaceBox | None
    anchor: PlaceAnchorResponse | None
    dates: list[PackFrameDate]


class PackSignatureSlot(StrictModel):
    id: str
    label: dict[str, str]
    applies_to: list[str]
    per_author: bool
    required: bool
    # Общее место слота, как его читает лоадер; `default_set` ложно, если ключа в YAML нет (место лоадера).
    default_place: PackPlaceEntry
    default_set: bool
    places: dict[str, PackPlaceEntry]
    dates: dict[str, list[PackIndexedDate]]
    # Рамки документа сборки; null без сборки или если слот к документу не относится.
    document: PackSlotFrame | None


class PackSignaturesBuild(StrictModel):
    id: str
    document: str
    # У сборки есть якоря: места на якорях стоят по строкам, иначе по запасным местам.
    anchors_known: bool
    sign_anchors: list[str]
    date_anchors: list[str]


class PackSignaturesResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    # Манифест версии и его ETag: правка мест идёт с `If-Match` по нему.
    path: str
    etag: str
    read_only: ReadOnlyReason | None
    documents: list[str]
    build: PackSignaturesBuild | None
    slots: list[PackSignatureSlot]


class PackPlaceOp(StrictModel):
    """Правка мест: `doc` пуст у общего места слота (`set_place`, `bind_anchor`, `unbind_anchor`)."""

    op: PlaceOpName
    slot: str = Field(min_length=1, max_length=64)
    doc: str | None = Field(default=None, max_length=128)
    box: PackPlaceBox | None = None
    index: int | None = Field(default=None, ge=0, le=64)
    mark: PackMarkBox | None = None
    anchor: str | None = Field(default=None, max_length=96)

    @model_validator(mode="after")
    def _fields(self) -> PackPlaceOp:
        needs_doc = {"remove_place", "make_default", "add_date", "set_date", "remove_date"}
        if self.op in needs_doc and self.doc is None:
            raise ValueError(f"{self.op} needs doc")
        if self.op == "set_place" and self.box is None:
            raise ValueError("set_place needs box")
        if self.op in {"set_date", "remove_date"} and self.index is None:
            raise ValueError(f"{self.op} needs index")
        if self.op == "set_date" and self.mark is None:
            raise ValueError("set_date needs mark")
        if self.op == "add_date" and self.mark is None and self.anchor is None:
            raise ValueError("add_date needs mark or anchor")
        return self


class PackSignaturesPatchRequest(StrictModel):
    # Сборка, по якорям которой автор видит рамки: место на якоре двигается относительно её линии.
    build_id: UUID | None = None
    ops: list[PackPlaceOp] = Field(min_length=1, max_length=50)


# ── Срезы T11 и T12: формы версии (модель, точечные правки манифестов, операции) ──

ModelActionName = Literal["rename_field", "add_document", "remove_document", "add_translation"]


class PackModelFile(StrictModel):
    """Манифест версии или документа: путь от папки паков, ETag и данные `safe_load` (даты строкой ISO)."""

    path: str
    etag: str
    data: Any


class PackDocFile(StrictModel):
    """Файл папки документа: путь от `files/` версии, путь без языкового кода и код ("" у файла для всех языков)."""

    path: str
    bare: str
    lang: str
    size: int


class PackModelDocument(StrictModel):
    id: str
    # `files/<id>/doc.yaml`; None у записи v1 прямо в ростере (её данные в `data`) и у папки без манифеста.
    manifest: PackModelFile | None
    data: Any
    files: list[PackDocFile]
    # Где манифест версии называет документ (слоты подписей, места, профили сдачи).
    references: list[str]


class PackFieldUsage(StrictModel):
    """Поле печатается в документе: через макросы `\\hse...` динамических инклудов или прямо из исходника."""

    field: str
    document: str
    macros: list[str]
    direct: bool
    # Поле действует на весь документ (строка инклуда вне макросов, например шрифт).
    whole: bool


class PackVersionModelResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    read_only: ReadOnlyReason | None
    manifest: PackModelFile
    documents: list[PackModelDocument]
    usage: list[PackFieldUsage]
    # Файлы проверок версии без `.yaml` (`gost_ref` документа).
    checks: list[str]
    # Находки лоадера и схемы по манифестам версии сейчас.
    problems: list[str]
    # Файлы, которые записала или удалила эта правка (от папки паков); у чтения пусто.
    changed: list[str]


class PackModelPatchRequest(StrictModel):
    # Манифест от каталога версии: `version.yaml` или `files/<id>/doc.yaml`; `If-Match` по его ETag.
    file: str = Field(min_length=1, max_length=300)
    ops: list[PackYamlOp] = Field(min_length=1, max_length=50)


class PackModelActionRequest(StrictModel):
    """Операция на несколько файлов; `If-Match` по ETag `version.yaml`."""

    action: ModelActionName
    field: str | None = Field(default=None, max_length=64)
    to: str | None = Field(default=None, max_length=64)
    document: str | None = Field(default=None, max_length=64)
    name: dict[str, str] | None = None
    # add_document: папка заготовки от папки паков.
    source: str | None = Field(default=None, max_length=512)
    lang: str | None = Field(default=None, max_length=8)
    # add_translation: пути без языкового кода от `files/` (пусто: все файлы с редакцией языка по умолчанию).
    files: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _fields(self) -> PackModelActionRequest:
        needed = {
            "rename_field": ("field", "to"),
            "add_document": ("document",),
            "remove_document": ("document",),
            "add_translation": ("document", "lang"),
        }[self.action]
        missing = [name for name in needed if not getattr(self, name)]
        if missing:
            raise ValueError(f"{self.action} needs {', '.join(missing)}")
        return self


class PackDocLibraryItem(StrictModel):
    """Документ-заготовка: последняя версия шаблона пространства."""

    path: str
    pack: str
    template: str
    version: str
    id: str
    name: dict[str, str]


class PackDocLibraryResponse(StrictModel):
    documents: list[PackDocLibraryItem]


# ── Срез T15: пак и шаблон с нуля (docs/design/template-studio.md, раздел 8) ──

ScaffoldKindName = Literal["minimal", "copy"]
SourceOriginName = Literal["workspace", "catalog"]


class PackLocalizedText(StrictModel):
    ru: StrictStr = Field(default="", max_length=500)
    en: StrictStr = Field(default="", max_length=500)


class PackScaffoldSource(StrictModel):
    # `workspace`: пак этого пространства (имя папки); `catalog`: пак каталога этой Студии (id).
    origin: SourceOriginName
    pack: StrictStr = Field(min_length=1, max_length=255)
    template: StrictStr = Field(min_length=1, max_length=255)
    version: StrictStr = Field(min_length=1, max_length=64)


class PackScaffoldRequest(StrictModel):
    kind: ScaffoldKindName = "minimal"
    # Обязателен у `copy`.
    source: PackScaffoldSource | None = None

    @model_validator(mode="after")
    def _source_for_copy(self) -> PackScaffoldRequest:
        if self.kind == "copy" and self.source is None:
            raise ValueError("source is required for a copy")
        return self


class PackMaintainer(StrictModel):
    name: StrictStr = Field(max_length=500)
    email: StrictStr = Field(default="", max_length=500)
    url: StrictStr = Field(default="", max_length=500)


class CreatePackTemplateRequest(StrictModel):
    id: StrictStr = Field(min_length=1, max_length=64)
    name: PackLocalizedText
    short_name: PackLocalizedText | None = None
    description: PackLocalizedText | None = None
    scaffold: PackScaffoldRequest = Field(default_factory=PackScaffoldRequest)
    # Номер первой версии; по умолчанию `<год>.1`.
    version: StrictStr | None = Field(default=None, max_length=64)


class PackNewTemplate(StrictModel):
    id: StrictStr = Field(min_length=1, max_length=64)
    name: PackLocalizedText
    short_name: PackLocalizedText | None = None
    description: PackLocalizedText | None = None


class CreatePackRequest(StrictModel):
    id: StrictStr = Field(min_length=1, max_length=64)
    name: PackLocalizedText
    description: PackLocalizedText | None = None
    maintainer: PackMaintainer | None = None
    license: StrictStr | None = Field(default=None, max_length=500)
    source: StrictStr | None = Field(default=None, max_length=500)
    template: PackNewTemplate
    scaffold: PackScaffoldRequest = Field(default_factory=PackScaffoldRequest)
    version: StrictStr | None = Field(default=None, max_length=64)


class PackScaffoldVersion(StrictModel):
    version: str
    status: str | None
    released: bool
    default: bool


class PackScaffoldTemplate(StrictModel):
    template: str
    name: dict[str, str]
    default_version: str | None
    versions: list[PackScaffoldVersion]


class PackScaffoldPack(StrictModel):
    origin: SourceOriginName
    pack: str
    name: dict[str, str]
    license: str
    templates: list[PackScaffoldTemplate]


class PackScaffoldOptionsResponse(StrictModel):
    sources: list[PackScaffoldPack]
    # Занятые id паков в нижнем регистре: папки пространства и паки каталога Студии.
    taken_packs: list[str]
    maintainer: PackMaintainer | None
    license: str
    version: str


class PackScaffoldCreatedResponse(StrictModel):
    version: PackVersionRef
    pack_created: bool
    # Манифесты пака (если создан), шаблона и версии от папки паков.
    manifests: list[str]
    # Что открыть: исходник первого документа или манифест версии.
    main_file: str | None
    files: int
    source: PackScaffoldSource | None
