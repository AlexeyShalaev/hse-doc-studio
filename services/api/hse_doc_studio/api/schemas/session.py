"""Контракт серверного режима: bootstrap, сессия, регистрация, аккаунт, проекты, черновики админки.

Эталонные JSON лежат в contracts/server; их проверяют pytest (tests/unit/contract/test_server_contract.py)
и vitest (entities/session). Модели строгие (extra=forbid): лишнее поле означает расхождение
сторон. Форму меняют так: сначала эталоны, затем обе стороны и оба набора тестов в одном коммите.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.identity.normalize import is_valid_email

# Пределы полей, которые клиент присылает без входа: ключ попыток входа и журнал не должны раздуваться от ввода.
EMAIL_MAX = 254
PASSWORD_MAX = 1024
NAME_MAX = 200
TOKEN_MAX = 512

StudioModeName = Literal["local", "server"]
SetupState = Literal["needs_admin", "ready"]
RegistrationMode = Literal["open", "domains", "invite", "closed"]
OrgRoleName = Literal["owner", "admin", "member"]
AccountStatus = Literal["active", "pending_verification", "pending_approval", "disabled"]
TokenScope = Literal["api", "git:read", "git:write"]
ProjectRoleName = Literal["reader", "reviewer", "editor", "owner"]


class Capabilities(StrictModel):
    fs_browse: bool
    connect_folder: bool
    open_in_editor: bool
    move_project: bool
    docker_ui: bool
    self_update: bool
    local_services_ui: bool
    # Считается на запрос: админ установки, прошедший ограничение по хосту/IP.
    admin: bool
    personal_signing_keys: bool
    # Сервер: вошедший человек может подключать свои раннеры (личные разрешены в установке).
    personal_runners: bool = False
    # Локально: Студия может собирать облачные проекты хозяина как его личный раннер.
    remote_runner: bool = False


class OidcProviderOption(StrictModel):
    id: str
    label: str


class AuthOptions(StrictModel):
    registration_mode: RegistrationMode
    password_enabled: bool
    oidc_providers: list[OidcProviderOption]
    smtp_enabled: bool
    password_min_length: int


class OrgRole(StrictModel):
    slug: str
    name: str
    role: OrgRoleName


class SessionUser(StrictModel):
    id: str
    name: str
    email: str
    avatar_initials: str
    is_instance_admin: bool
    email_verified: bool
    locale: Literal["ru", "en"] | None
    org_roles: list[OrgRole]


class BootstrapResponse(StrictModel):
    mode: StudioModeName
    version: str
    setup_state: SetupState
    auth: AuthOptions
    user: SessionUser | None
    capabilities: Capabilities
    # Токен CSRF текущей сессии; без сессии null. Шлётся в заголовке X-CSRF-Token.
    csrf_token: str | None


class AuthErrorBody(StrictModel):
    detail: str
    code: str


class LoginRequest(StrictModel):
    email: str = Field(max_length=EMAIL_MAX)
    password: str = Field(max_length=PASSWORD_MAX)


class LoginResponse(StrictModel):
    user: SessionUser
    csrf_token: str


class RegisterRequest(StrictModel):
    email: str = Field(max_length=EMAIL_MAX)
    name: str = Field(max_length=NAME_MAX)
    password: str = Field(max_length=PASSWORD_MAX)
    invitation_token: str | None = Field(max_length=TOKEN_MAX)


class VerifyEmailRequest(StrictModel):
    token: str = Field(max_length=TOKEN_MAX)


# Ответ всегда нейтральный. link заполнен только без SMTP (ссылку копирует сам человек).
class RegisterResponse(StrictModel):
    status: Literal["check_email", "pending_approval"]
    link: str | None


# Что известно о приглашении по ссылке: форма регистрации подставляет почту и блокирует её.
class InvitationInfo(StrictModel):
    email: str
    invited_by: str
    org_name: str | None


# Повторная отправка письма подтверждения. Ответ нейтральный: ForgotResponse.
class ResendVerificationRequest(StrictModel):
    email: str = Field(max_length=EMAIL_MAX)


class ForgotRequest(StrictModel):
    email: str = Field(max_length=EMAIL_MAX)


class ForgotResponse(StrictModel):
    status: Literal["check_email"]
    link: str | None


class ResetRequest(StrictModel):
    token: str = Field(max_length=TOKEN_MAX)
    password: str = Field(max_length=PASSWORD_MAX)


class ServerSetupStatus(StrictModel):
    state: SetupState
    token_required: bool
    steps_done: list[Literal["admin", "settings"]]


class ServerSetupAdminRequest(StrictModel):
    setup_token: str | None
    name: str
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email_is_valid(cls, value: str) -> str:
        if not is_valid_email(value):
            msg = "email is not valid"
            raise ValueError(msg)
        return value


class ServerSetupSettingsRequest(StrictModel):
    registration_mode: RegistrationMode
    # Домены почты для режима domains (для него нужен хотя бы один); в остальных режимах пустой список.
    registration_domains: list[str]
    require_approval: bool
    password_enabled: bool

    @model_validator(mode="after")
    def _domains_mode_needs_domains(self) -> ServerSetupSettingsRequest:
        if self.registration_mode == "domains" and not any(d.strip().lstrip("@") for d in self.registration_domains):
            msg = "registration_domains must not be empty in domains mode"
            raise ValueError(msg)
        return self


SetupSettingKey = Literal["registration_mode", "registration_domains", "require_approval", "password_enabled"]


class ServerSetupSettings(StrictModel):
    """Действующие настройки входа для шага мастера: значения и ключи, заданные окружением (только чтение)."""

    registration_mode: RegistrationMode
    registration_domains: list[str]
    require_approval: bool
    password_enabled: bool
    locked_by_env: list[SetupSettingKey]


SetupCheckId = Literal["database", "storage", "runner"]
SetupCheckStatus = Literal["ok", "fail", "not_configured"]


class ServerSetupCheck(StrictModel):
    id: SetupCheckId
    status: SetupCheckStatus
    # Короткая причина для fail (класс ошибки); подробности только в журнале сервера.
    reason: str | None


class ServerSetupEnvironment(StrictModel):
    checks: list[ServerSetupCheck]


class UpdateAccountRequest(StrictModel):
    """Частичное обновление: отсутствующее поле и `null` значат «не менять».

    Пустая строка в `commit_name` или `commit_email` сбрасывает своё значение к подписи по умолчанию.
    """

    name: str | None = Field(default=None, max_length=NAME_MAX)
    locale: Literal["ru", "en"] | None = None
    commit_name: str | None = Field(default=None, max_length=NAME_MAX)
    commit_email: str | None = Field(default=None, max_length=EMAIL_MAX)
    commit_use_account_email: bool | None = None


class AccountProfile(StrictModel):
    """Профиль аккаунта и подпись, которой ставятся коммиты человека."""

    id: str
    name: str
    email: str
    locale: Literal["ru", "en"] | None
    commit_name: str | None
    commit_email: str | None
    commit_use_account_email: bool
    effective_commit_name: str
    effective_commit_email: str
    # Адрес в коммитах сгенерирован (настоящий e-mail наружу не уходит).
    commit_email_is_noreply: bool


class ChangePasswordRequest(StrictModel):
    current_password: str = Field(max_length=PASSWORD_MAX)
    new_password: str = Field(max_length=PASSWORD_MAX)
    sign_out_other_sessions: bool


# Смена e-mail: ссылка уходит на новый адрес. Ответ нейтральный (занятый адрес отвечает так же);
# link заполнен только без SMTP.
class ChangeEmailRequest(StrictModel):
    email: str = Field(max_length=EMAIL_MAX)
    password: str = Field(max_length=PASSWORD_MAX)

    @field_validator("email")
    @classmethod
    def _email_is_valid(cls, value: str) -> str:
        if not is_valid_email(value):
            msg = "email is not valid"
            raise ValueError(msg)
        return value


class ChangeEmailResponse(StrictModel):
    status: Literal["check_email"]
    link: str | None


class AccountSession(StrictModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    ip: str | None
    user_agent: str
    current: bool


class AccountIdentity(StrictModel):
    """Внешний вход, привязанный к аккаунту."""

    provider: str
    # Название для экрана; None, если провайдер удалён или выключен (отвязать всё равно можно).
    label: str | None
    email: str | None
    email_verified: bool


class ApiToken(StrictModel):
    id: str
    name: str
    # Первые символы для опознания; сам токен показывается один раз при создании.
    prefix: str
    scopes: list[TokenScope]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


class CreateApiTokenRequest(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[TokenScope] = Field(min_length=1, max_length=3)
    expires_in_days: int | None = Field(ge=1, le=365)


class CreateApiTokenResponse(StrictModel):
    token: str
    item: ApiToken


class ProjectOwner(StrictModel):
    kind: Literal["user", "org"]
    id: str
    name: str
    slug: str | None


class ProjectSummary(StrictModel):
    id: str
    name: str
    kind: Literal["research", "project"]
    staffing: Literal["solo", "team"]
    lang: Literal["ru", "en"]
    owner: ProjectOwner
    my_role: ProjectRoleName
    updated_at: datetime
    pinned: bool
    archived: bool
    shared_enabled: bool


class ProjectImportWarning(StrictModel):
    code: Literal["remote_needs_access", "records_skipped", "store_hardened", "junk_skipped", "chats_unreadable"]
    # Число затронутых файлов или настроек; пусто, когда считать нечего.
    detail: str


class ProjectImportResult(StrictModel):
    project_id: str
    name: str
    # Id из архива был занят, проекту выдан новый.
    id_regenerated: bool
    files: int
    bytes: int
    chats: int
    warnings: list[ProjectImportWarning]


# Папку проекта в серверном режиме выбирает сервер: поля folder нет, владелец задаётся slug организации.
class CreateServerProjectRequest(StrictModel):
    name: str
    pack_id: str
    template_id: str
    version: str
    engine: Literal["xelatex", "pdflatex", "lualatex"]
    kind: Literal["research", "project"]
    staffing: Literal["solo", "team"]
    lang: Literal["ru", "en"]
    owner_org_slug: str | None
    shared_enabled: bool


class AdminUser(StrictModel):
    id: str
    name: str
    email: str
    status: AccountStatus
    is_instance_admin: bool
    created_at: datetime
    last_login_at: datetime | None
    project_count: int


class AdminUserPage(StrictModel):
    items: list[AdminUser]
    total: int
    limit: int
    offset: int


class UpdateAdminUserRequest(StrictModel):
    is_instance_admin: bool


class AdminResetLinkRequest(StrictModel):
    # Выдача ссылки сброса это захват аккаунта: без явного подтверждения не выполняется.
    confirm: bool


class AdminResetLink(StrictModel):
    link: str
    expires_at: datetime
    user_notified: bool


class AdminSessionsRevoked(StrictModel):
    revoked: int


class AdminRetentionSettings(StrictModel):
    """Сроки хранения в днях; задаются окружением, в интерфейсе только для чтения. `audit_days=0`: журнал вечно."""

    audit_days: int
    deleted_projects_days: int
    unused_blobs_days: int


AdminInvitationStatus = Literal["pending", "used", "expired"]


class AdminInvitation(StrictModel):
    id: str
    email: str | None
    status: AdminInvitationStatus
    expires_at: datetime
    used_at: datetime | None


class AdminInvitationPage(StrictModel):
    items: list[AdminInvitation]
    total: int
    limit: int
    offset: int


class AdminAuditEvent(StrictModel):
    id: int
    at: datetime
    action: str
    actor_id: str | None
    target: str | None
    details: dict[str, Any]


class AdminAuditPage(StrictModel):
    """Страница журнала по ключу: `next_cursor` непрозрачный, пустой на последней странице."""

    items: list[AdminAuditEvent]
    next_cursor: str | None


class CreateAdminInvitationRequest(StrictModel):
    email: str | None
    ttl_days: int | None


class AdminInvitationCreated(StrictModel):
    invitation: AdminInvitation
    # Непустая, когда письмо не ушло по почте: ссылку пересылает сам админ.
    link: str | None


ProjectMemberKind = Literal["user", "group"]
ProjectMemberRole = Literal["reader", "reviewer", "editor"]


class ProjectMember(StrictModel):
    kind: ProjectMemberKind
    principal_id: str
    name: str
    role: ProjectMemberRole
    persona: str | None
    can_share: bool
    show_sources: bool
    can_edit_all: bool


class SetProjectMemberRequest(StrictModel):
    role: ProjectMemberRole
    persona: str | None = Field(max_length=64)
    can_share: bool
    show_sources: bool
    can_edit_all: bool


class AdminOrg(StrictModel):
    slug: str
    name: str
    member_count: int
    project_count: int
    # Роль смотрящего в организации; null у админа установки, который в ней не состоит.
    my_role: OrgRoleName | None


# Организации и группы: /orgs и /groups (серверный режим).
class Org(StrictModel):
    slug: str
    name: str
    my_role: OrgRoleName
    member_count: int
    group_count: int
    project_count: int
    created_at: datetime


class CreateOrgRequest(StrictModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    # Только админ установки: назначить владельцем другого человека. Без него владелец создатель.
    owner_email: str | None = Field(max_length=EMAIL_MAX)


class UpdateOrgRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)


class OrgMember(StrictModel):
    user_id: str
    name: str
    email: str
    role: OrgRoleName
    joined_at: datetime


class AddOrgMemberRequest(StrictModel):
    email: str = Field(min_length=1, max_length=EMAIL_MAX)
    role: OrgRoleName


class ChangeOrgMemberRoleRequest(StrictModel):
    role: OrgRoleName


class Group(StrictModel):
    id: str
    name: str
    member_count: int
    created_at: datetime


class CreateGroupRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)


class UpdateGroupRequest(StrictModel):
    name: str = Field(min_length=1, max_length=256)


class GroupMember(StrictModel):
    user_id: str
    name: str
    email: str
    added_at: datetime


class AddGroupMemberRequest(StrictModel):
    user_id: str = Field(min_length=1, max_length=64)


class AdminOrgMember(OrgMember):
    """Участник организации в админке: та же форма, что у участника в /orgs."""


class AddAdminOrgMemberRequest(StrictModel):
    email: str
    role: OrgRoleName


class UpdateAdminOrgMemberRequest(StrictModel):
    role: OrgRoleName


class CreateAdminOrgRequest(StrictModel):
    name: str
    slug: str


class AdminGroup(StrictModel):
    id: str
    name: str
    member_ids: list[str]


class CreateAdminGroupRequest(StrictModel):
    name: str
    member_ids: list[str]


class UpdateAdminGroupRequest(StrictModel):
    # null значит «не менять».
    name: str | None
    member_ids: list[str] | None


class MyOrg(StrictModel):
    """Организация глазами участника: «Настройки → Организации» (GET /api/v1/account/orgs)."""

    slug: str
    name: str
    my_role: OrgRoleName
    member_count: int
    # Названия групп организации, в которых состоит человек.
    groups: list[str]
    # Человек единственный владелец: выйти нельзя, пока не назначен другой (409 last_owner).
    sole_owner: bool


class ProjectAccessEntry(StrictModel):
    """Строка панели «Доступ» проекта (GET /api/v1/projects/{id}/members)."""

    subject_kind: Literal["user", "group", "org"]
    subject_id: str
    name: str
    # Почта человека или организация группы; у организации null.
    detail: str | None
    role: ProjectRoleName
    # Строку нельзя менять здесь: владелец проекта и доступ через организацию-владельца.
    locked: bool


class ProjectAccessCandidate(StrictModel):
    """Кого можно добавить (GET /api/v1/projects/{id}/members/candidates?q=)."""

    subject_kind: Literal["user", "group"]
    subject_id: str
    name: str
    detail: str | None


class AdminSettings(StrictModel):
    registration_mode: RegistrationMode
    require_approval: bool
    password_enabled: bool
    allowed_domains: list[str]
    smtp_enabled: bool
    public_url: str


SettingSourceName = Literal["env", "admin", "default"]
SmtpSecurityName = Literal["starttls", "tls", "none"]


class SettingState(StrictModel):
    """Откуда значение; `locked` значит «задано окружением, из интерфейса не меняется»."""

    source: SettingSourceName
    locked: bool


class AdminRegistrationSettings(StrictModel):
    registration_mode: RegistrationMode
    registration_domains: list[str]
    require_approval: bool
    fields: dict[str, SettingState]


class UpdateAdminRegistrationRequest(StrictModel):
    """Меняется только заданное (не null)."""

    registration_mode: RegistrationMode | None = None
    registration_domains: list[str] | None = Field(default=None, max_length=200)
    require_approval: bool | None = None


class AdminAuthSettings(StrictModel):
    password_enabled: bool
    # Сколько провайдеров единого входа включено: отключить пароль можно, только если есть куда войти иначе.
    oidc_enabled_count: int
    fields: dict[str, SettingState]


class UpdateAdminAuthRequest(StrictModel):
    password_enabled: bool | None = None


class AdminSmtpSettings(StrictModel):
    """Пароль не возвращается никогда: только признак `password_set`."""

    enabled: bool
    host: str | None
    port: int
    security: SmtpSecurityName
    username: str | None
    password_set: bool
    from_address: str
    from_name: str
    fields: dict[str, SettingState]


class UpdateAdminSmtpRequest(StrictModel):
    """Меняется только заданное (не null). `host: ""` выключает почту, пустые `username` и `password` стирают их."""

    host: str | None = Field(default=None, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65535)
    security: SmtpSecurityName | None = None
    username: str | None = Field(default=None, max_length=256)
    password: str | None = Field(default=None, max_length=1024)
    from_address: str | None = Field(default=None, max_length=254)
    from_name: str | None = Field(default=None, max_length=200)


class AdminSmtpTestRequest(StrictModel):
    """Без `to` письмо уходит на адрес самого админа."""

    to: str | None = Field(default=None, max_length=EMAIL_MAX)


class AdminSmtpTestResult(StrictModel):
    ok: bool
    error: str | None


class AdminOidcProvider(StrictModel):
    """Секрет клиента не возвращается никогда: только признак `client_secret_set`."""

    id: str
    label: str
    issuer: str
    client_id: str
    client_secret_set: bool
    scopes: str
    enabled: bool
    auto_provision: bool
    created_at: datetime


class CreateAdminOidcProviderRequest(StrictModel):
    label: str = Field(max_length=128)
    issuer: str = Field(max_length=2048)
    client_id: str = Field(max_length=256)
    client_secret: str = Field(max_length=1024)
    scopes: str = Field(default="openid email profile", max_length=256)
    enabled: bool = True
    auto_provision: bool = False


class UpdateAdminOidcProviderRequest(StrictModel):
    """Меняется только заданное (не null); секрет заменяется только новым значением."""

    label: str | None = Field(default=None, max_length=128)
    issuer: str | None = Field(default=None, max_length=2048)
    client_id: str | None = Field(default=None, max_length=256)
    client_secret: str | None = Field(default=None, max_length=1024)
    scopes: str | None = Field(default=None, max_length=256)
    enabled: bool | None = None
    auto_provision: bool | None = None


CompileWaitReason = Literal["queued", "no_runner", "quota_wait", "runner_lost", "superseded", "personal_runner"]


class CompileWait(StrictModel):
    """Почему сборка ещё не идёт (поле `wait` деталей сборки и события `wait` потока).

    queued и quota_wait: сборка ждёт очереди (место и оценка ожидания); no_runner: свободных раннеров нет;
    runner_lost: раннер потерян, идёт повтор (попытка из максимума); superseded: сборку заменила более новая;
    personal_runner: сборка ждёт личный раннер владельца проекта (`wait_hint_seconds` окно ожидания).
    """

    reason: CompileWaitReason
    queue_position: int | None = Field(ge=1)
    wait_hint_seconds: int | None = Field(ge=0)
    attempt: int | None = Field(ge=1)
    max_attempts: int | None = Field(ge=1)


class OfficeEditorBusy(StrictModel):
    """Ответ редактора документов, когда исчерпан лимит сессий ONLYOFFICE (state=editor_busy)."""

    state: Literal["editor_busy"]
    retry_after_s: int = Field(ge=1)
    limit: int = Field(ge=1)
