"""Контракт серверного режима: bootstrap, сессия, регистрация, аккаунт, проекты, черновики админки.

Эталонные JSON лежат в contracts/server; их проверяют pytest (tests/unit/contract/test_server_contract.py)
и vitest (entities/session). Модели строгие (extra=forbid): лишнее поле означает расхождение
сторон. Форму меняют так: сначала эталоны, затем обе стороны и оба набора тестов в одном коммите.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    name: str | None = None
    locale: Literal["ru", "en"] | None = None


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
    name: str
    scopes: list[TokenScope]
    expires_in_days: int | None


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


class AdminOrg(StrictModel):
    slug: str
    name: str
    member_count: int
    project_count: int


class AdminRunner(StrictModel):
    id: str
    name: str
    status: Literal["online", "offline", "draining"]
    tags: list[str]
    version: str
    last_seen_at: datetime | None
    running_jobs: int


class AdminSettings(StrictModel):
    registration_mode: RegistrationMode
    require_approval: bool
    password_enabled: bool
    allowed_domains: list[str]
    smtp_enabled: bool
    public_url: str
