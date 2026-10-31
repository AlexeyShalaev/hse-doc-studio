"""Сущности identity: пользователь, сессия, персональный токен, разовые токены, приглашения.

Секреты (сессии, токены) в сущностях хранятся только хешем sha256; сам секрет существует в
момент выдачи и отдаётся один раз.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.listing import PICKER_LIMIT, SortKey, Window


class UserStatus(StrEnum):
    active = "active"
    pending_verification = "pending_verification"
    pending_approval = "pending_approval"
    disabled = "disabled"


class RegistrationMode(StrEnum):
    """Кто может зарегистрироваться; значения совпадают с `RegistrationMode` контракта."""

    open = "open"
    domains = "domains"
    invite = "invite"
    closed = "closed"


class TokenScope(StrEnum):
    api = "api"
    git_read = "git:read"
    git_write = "git:write"


class AuthTokenKind(StrEnum):
    """Разовые токены из писем и ссылок."""

    verify_email = "verify_email"
    reset_password = "reset_password"  # noqa: S105 — вид токена, не пароль
    setup = "setup"
    change_email = "change_email"


@dataclass(frozen=True)
class User:
    id: str
    email: str
    # Ключ уникальности: `normalize_email(email)`.
    email_normalized: str
    name: str
    status: UserStatus
    created_at: datetime
    email_verified: bool = False
    is_instance_admin: bool = False
    locale: str | None = None
    last_login_at: datetime | None = None
    # Подпись коммитов: пусто значит «как в аккаунте» (имя) и noreply-адрес, если не включён флаг.
    commit_name: str | None = None
    commit_email: str | None = None
    commit_use_account_email: bool = False

    @property
    def can_sign_in(self) -> bool:
        return self.status is UserStatus.active


@dataclass(frozen=True)
class UserListing:
    """Строка списка пользователей админки: человек и число его проектов (без содержимого)."""

    user: User
    project_count: int


USER_SORTS = ("name", "email", "created_at", "last_login_at", "status")


@dataclass(frozen=True)
class UserQuery:
    """Фильтры списка людей админки; всё сочетается по И. `org_slug`: человек состоит в этой организации."""

    q: str | None = None
    statuses: tuple[UserStatus, ...] = ()
    is_admin: bool | None = None
    org_slug: str | None = None
    sort: SortKey = field(default_factory=lambda: SortKey("created_at", descending=True))
    window: Window = field(default_factory=Window)


@dataclass(frozen=True)
class UserFacets:
    """Счётчики на чипах списка людей под теми же условиями.

    Каждый счётчик не учитывает свой фильтр: статусы считаются при выбранной роли, роли при выбранных статусах.
    `members`: не админы установки.
    """

    status: Mapping[UserStatus, int]
    admins: int
    members: int


def facets_of(rows: Iterable[tuple[UserStatus, bool, int]], query: UserQuery) -> UserFacets:
    """Счётчики из групп «статус, админ ли, сколько» под общими условиями; фильтры статуса и роли из `query`."""
    by_status = dict.fromkeys(UserStatus, 0)
    roles = {True: 0, False: 0}
    for status, admin, n in rows:
        if query.is_admin is None or admin is query.is_admin:
            by_status[status] += n
        if not query.statuses or status in query.statuses:
            roles[admin] += n
    return UserFacets(status=by_status, admins=roles[True], members=roles[False])


@dataclass(frozen=True)
class UserPickQuery:
    """Пикер людей: только админ установки, он видит всех. Исключения: уже состоящие в организации или группе."""

    q: str | None = None
    limit: int = PICKER_LIMIT
    status: UserStatus | None = None
    not_in_org_slug: str | None = None
    not_in_group_id: str | None = None


@dataclass(frozen=True)
class UserIdentity:
    """Внешняя учётная запись (OIDC): пара (provider, subject) уникальна."""

    user_id: str
    provider: str
    subject: str
    email: str | None = None
    email_verified: bool = False


@dataclass(frozen=True)
class Session:
    id_hash: str
    user_id: str
    # Токен CSRF привязан к строке сессии и в ответах отдаётся вместе с ней.
    csrf_token: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip: str | None = None
    user_agent: str = ""


@dataclass(frozen=True)
class ApiToken:
    id: str
    user_id: str
    name: str
    token_hash: str
    # Первые символы для опознания в списке.
    prefix: str
    scopes: frozenset[TokenScope]
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None


@dataclass(frozen=True)
class AuthToken:
    token_hash: str
    kind: AuthTokenKind
    user_id: str | None
    expires_at: datetime
    used_at: datetime | None = None
    # Данные, ради которых выдан токен: для смены адреса это новый адрес.
    payload: str | None = None


@dataclass(frozen=True)
class RegistrationInvite:
    token_hash: str
    # Пусто: приглашение на любой адрес.
    email: str | None
    created_by: str
    expires_at: datetime
    used_at: datetime | None = None
    # Публичный идентификатор для списка и отзыва; хеш токена наружу не отдаётся. Пусто: хранилище берёт начало хеша.
    id: str = ""
    # Членство, которое получит принявший приглашение; организации появятся в срезе орг.
    org_id: str | None = None
    org_role: str | None = None


class InviteState(StrEnum):
    """Состояние приглашения: от `used_at`, `expires_at` и текущего времени."""

    pending = "pending"
    used = "used"
    expired = "expired"


def invite_state(invite: RegistrationInvite, now: datetime) -> InviteState:
    if invite.used_at is not None:
        return InviteState.used
    return InviteState.expired if invite.expires_at <= now else InviteState.pending


INVITE_SORTS = ("expires_at", "email")


@dataclass(frozen=True)
class InviteQuery:
    """Список приглашений админки. Состояние считается в запросе относительно `now`."""

    now: datetime
    q: str | None = None
    states: tuple[InviteState, ...] = ()
    org_slug: str | None = None
    created_by: str | None = None
    sort: SortKey = field(default_factory=lambda: SortKey("expires_at", descending=True))
    window: Window = field(default_factory=Window)


@dataclass(frozen=True)
class LoginAttempt:
    """Счётчик неудачных входов по ключу (e-mail и IP или один IP); задержка растёт, постоянной блокировки нет."""

    key: str
    failures: int
    updated_at: datetime
    next_allowed_at: datetime | None = None


class MailKind(StrEnum):
    verify_email = "verify_email"
    reset_password = "reset_password"  # noqa: S105 — вид письма, не пароль
    invite = "invite"
    email_change = "email_change"
    # Уведомление без ссылки: админ выдал ссылку для сброса пароля.
    reset_notice = "reset_notice"


@dataclass(frozen=True)
class MailOutboxEntry:
    """Запись о неушедшем письме (SMTP не настроен или сбой). Ссылка с токеном не хранится: поле пусто."""

    id: str
    kind: MailKind
    to_email: str
    link: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class OidcProvider:
    id: str
    label: str
    issuer: str
    client_id: str
    # Шифртекст `ISecretCipher` с привязкой `column_aad("oidc_providers", "client_secret_enc", id)`.
    client_secret_enc: str
    created_at: datetime
    scopes: str = "openid email profile"
    enabled: bool = True
    # Создавать пользователя при первом входе без регистрационной политики (решает админ).
    auto_provision: bool = False


OIDC_SORTS = ("label", "created_at")


@dataclass(frozen=True)
class OidcProviderQuery:
    """Провайдеры входа в админке: поиск по названию и издателю, фильтр включённых."""

    q: str | None = None
    enabled: bool | None = None
    sort: SortKey = field(default_factory=lambda: SortKey("created_at"))
    window: Window = field(default_factory=Window)


@dataclass(frozen=True)
class AuditEntry:
    id: int
    at: datetime
    action: str
    actor_id: str | None = None
    target: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditQuery:
    """Фильтры чтения журнала; события новые первыми, страница идёт ключом `before_id` (id последнего виденного).

    Все фильтры сочетаются по И. Внутри «что случилось» действие подходит, если оно из любой категории
    `categories` (префикс до точки) или равно любому из `actions`. `q` ищет подстроку в действии и цели,
    а также события людей, у которых она есть в имени или почте.
    """

    actor_id: str | None = None
    action_prefix: str | None = None
    categories: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    target: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    q: str | None = None
    before_id: int | None = None
    limit: int = 50

    @property
    def filtered(self) -> bool:
        return any(
            (
                self.actor_id,
                self.action_prefix,
                self.categories,
                self.actions,
                self.target,
                self.since,
                self.until,
                self.q,
            )
        )


# Сколько людей, подходящих под поиск журнала, учитывается как «кто»: поиск не превращается в перебор установки.
AUDIT_PEOPLE_LIMIT = 200


@dataclass(frozen=True)
class AuditActor:
    """Кто действовал. У удалённого человека вместо имени псевдоним из журнала, почты нет."""

    id: str
    name: str
    email: str | None


@dataclass(frozen=True)
class AuditView:
    """Событие с подписями, которые сервер вычисляет сам: имя действовавшего и подпись цели."""

    entry: AuditEntry
    actor: AuditActor | None
    target_label: str | None


@dataclass(frozen=True)
class AuditPage:
    items: list[AuditView]
    next_before_id: int | None
    # Оценка числа событий без фильтров (по статистике таблицы); с фильтрами не считается.
    total_estimate: int | None = None


@dataclass(frozen=True)
class ActorCredentials:
    """Что запрос предъявил для входа: значение cookie сессии, токен из заголовка Authorization: Bearer
    и секрет гостевой сессии по ссылке (cookie `hse_guest`)."""

    session_secret: str | None = None
    bearer_token: str | None = None
    guest_secret: str | None = None


@dataclass(frozen=True)
class AuthSettings:
    """Настройки входа установки; хранятся в instance_settings."""

    registration_mode: RegistrationMode = RegistrationMode.invite
    registration_domains: tuple[str, ...] = field(default_factory=tuple)
    require_approval: bool = False
    password_enabled: bool = True
