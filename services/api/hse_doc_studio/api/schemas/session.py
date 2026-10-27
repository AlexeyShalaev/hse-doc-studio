"""Контракт серверного режима: bootstrap, сессия, регистрация, аккаунт, проекты, черновики админки.

Эталонные JSON лежат в contracts/server; их проверяют pytest (tests/unit/contract/test_server_contract.py)
и vitest (entities/session). Модели строгие (extra=forbid): лишнее поле означает расхождение
сторон. Форму меняют так: сначала эталоны, затем обе стороны и оба набора тестов в одном коммите.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

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
    email: str
    password: str


class LoginResponse(StrictModel):
    user: SessionUser
    csrf_token: str


class RegisterRequest(StrictModel):
    email: str
    name: str
    password: str
    invitation_token: str | None


class VerifyEmailRequest(StrictModel):
    token: str


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
    email: str


class ForgotRequest(StrictModel):
    email: str


class ForgotResponse(StrictModel):
    status: Literal["check_email"]
    link: str | None


class ResetRequest(StrictModel):
    token: str
    password: str


class ServerSetupStatus(StrictModel):
    state: SetupState
    token_required: bool
    steps_done: list[Literal["admin", "settings"]]


class ServerSetupAdminRequest(StrictModel):
    setup_token: str | None
    name: str
    email: str
    password: str


class ServerSetupSettingsRequest(StrictModel):
    registration_mode: RegistrationMode
    require_approval: bool
    password_enabled: bool


class UpdateAccountRequest(StrictModel):
    name: str | None = None
    locale: Literal["ru", "en"] | None = None


class ChangePasswordRequest(StrictModel):
    current_password: str
    new_password: str
    sign_out_other_sessions: bool


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
