"""Ссылки доступа к проекту и гостевые сессии: типы, константы и порты хранилища.

Ссылка (`share_links`) даёт роль без членства: гостю без входа или вошедшему (ссылочное право). Действует
ссылка, пока она не отозвана, не истекла и её не запрещает политика установки и организации
(`core.access.sharing_policy`); политика пересчитывается на каждый запрос, поэтому ужесточение закрывает уже
открытые ссылки без записи в БД.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.listing import Found, Window


class LinkRole(StrEnum):
    reader = "reader"
    reviewer = "reviewer"
    editor = "editor"

    @property
    def role(self) -> Role:
        return Role(self.value)


class LinkState(StrEnum):
    active = "active"
    expired = "expired"
    revoked = "revoked"
    blocked = "blocked"


class LinkBlockReason(StrEnum):
    links_disabled = "links_disabled"
    org_links_off = "org_links_off"
    org_role_cap = "org_role_cap"
    nda = "nda"


class LinkPreviewState(StrEnum):
    ok = "ok"
    password_required = "password_required"  # noqa: S105 — состояние превью, не пароль
    login_required = "login_required"
    org_only = "org_only"
    inactive = "inactive"


class RevokeReason(StrEnum):
    manual = "manual"
    rotated = "rotated"
    policy = "policy"
    project_deleted = "project_deleted"


LINK_TOKEN_PREFIX = "hsl_"  # noqa: S105 — префикс формата токена, не секрет
LINK_ID_PREFIX = "lnk_"
GUEST_SESSION_PREFIX = "gs_"
GUEST_COOKIE = "hse_guest"
MAX_ACTIVE_LINKS_PER_PROJECT = 50
LABEL_MAX = 128
GUEST_NAME_MAX = 64
PASSWORD_MIN = 8
PASSWORD_MAX = 128
EXPIRY_DAYS_MAX = 365
TOKEN_PREFIX_LEN = 8
# Отозванные ссылки видны в списке («Показать отозванные») ещё месяц.
REVOKED_VISIBLE_DAYS = 30
# Пароль ссылки: десять неудач с одного адреса бесплатны, дальше пауза растёт до 15 минут (S4).
PASSWORD_FREE_FAILURES = 10
PASSWORD_MAX_DELAY_S = 15 * 60

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def new_link_token() -> str:
    """`hsl_` и 32 случайных байта (256 бит) в base64url."""
    return LINK_TOKEN_PREFIX + secrets.token_urlsafe(32)


def new_link_id() -> str:
    return LINK_ID_PREFIX + secrets.token_hex(16)


def new_guest_session_id() -> str:
    return GUEST_SESSION_PREFIX + secrets.token_hex(16)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def token_prefix_of(token: str) -> str:
    """Первые восемь знаков после `hsl_`: по ним владелец узнаёт ссылку в списке."""
    return token.removeprefix(LINK_TOKEN_PREFIX)[:TOKEN_PREFIX_LEN]


def looks_like_link_token(value: str) -> bool:
    return value.startswith(LINK_TOKEN_PREFIX) and 16 <= len(value) <= 128 and value.isascii()


def clean_text(value: str, limit: int) -> str | None:
    """Строка без управляющих знаков и лишних пробелов; None, если пусто или длиннее предела."""
    text = " ".join(_CONTROL.sub(" ", unicodedata.normalize("NFC", value)).split())
    if not text or len(text) > limit:
        return None
    return text


def password_delay_s(failures: int) -> int:
    """Пауза после `failures`-й неудачи пароля ссылки: первые десять без паузы, дальше 2^n секунд до 15 минут."""
    over = failures - PASSWORD_FREE_FAILURES
    if over < 0:
        return 0
    return min(2 ** min(over, 20), PASSWORD_MAX_DELAY_S)


@dataclass(frozen=True)
class ShareLink:
    id: str
    project_id: UUID
    label: str
    role: LinkRole
    show_sources: bool
    require_login: bool
    has_password: bool
    token_prefix: str
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    revoke_reason: str | None
    replaced_by: str | None
    last_opened_at: datetime | None

    @property
    def sources_open(self) -> bool:
        """Исходники и история: у Рецензента и Редактора всегда, у Читателя по флагу."""
        return self.show_sources or self.role is not LinkRole.reader

    def is_live(self, now: datetime) -> bool:
        """Не отозвана и не истекла (без учёта политики)."""
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)


@dataclass(frozen=True)
class ShareLinkSecrets:
    """Что хранится рядом со ссылкой и наружу не уходит: хеш пароля, хеш и шифртекст токена."""

    password_hash: str | None
    token_hash: str
    token_enc: str


@dataclass(frozen=True)
class NewShareLinkRecord:
    link: ShareLink
    secrets: ShareLinkSecrets


@dataclass(frozen=True)
class ShareLinkChanges:
    """Правка записи: None значит «не менять»; `password_hash` меняется только при `set_password`."""

    label: str | None = None
    role: LinkRole | None = None
    show_sources: bool | None = None
    require_login: bool | None = None
    set_password: bool = False
    password_hash: str | None = None
    set_expiry: bool = False
    expires_at: datetime | None = None


@dataclass(frozen=True)
class LinkVisitStats:
    visitors: int
    opens: int
    last_at: datetime | None


@dataclass(frozen=True)
class LinkVisit:
    visitor_kind: Literal["guest", "user"]
    visitor_id: str
    name: str | None
    first_at: datetime
    last_at: datetime
    opens: int


@dataclass(frozen=True)
class LinkVisitRecord:
    """Итог отметки визита: `first_today` значит, что сегодня этот гость или человек открывает ссылку впервые."""

    first_today: bool


@dataclass(frozen=True)
class GuestSession:
    id: str
    name: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    csrf_token: str


@dataclass(frozen=True)
class GuestLink:
    """Ссылка, открытая в гостевой сессии, вместе с её проектом и подписью для шапки гостя."""

    link: ShareLink
    project_name: str


@dataclass(frozen=True)
class LinkProject:
    """Проект ссылки: имя, владелец (человек или организация) и признак NDA для политики."""

    id: UUID
    name: str
    owner_user_id: str | None
    owner_org_id: str | None
    owner_name: str
    nda: bool


class IShareLinkRepository(Protocol):
    async def get(self, link_id: str) -> ShareLink | None: ...

    async def get_by_token_hash(self, token_hash: str) -> ShareLink | None: ...


class IShareLinkStore(IShareLinkRepository, Protocol):
    """Запись ссылок: используют сценарии `use_cases/sharing`."""

    async def add(self, record: NewShareLinkRecord) -> None: ...

    async def project(self, project_id: UUID) -> LinkProject | None:
        """Неудалённый проект ссылки; None, если проекта нет."""
        ...

    async def user_names(self, user_ids: Sequence[str]) -> dict[str, str]: ...

    async def secrets_of(self, link_id: str) -> ShareLinkSecrets | None: ...

    async def list_for_project(
        self, project_id: UUID, *, created_by: str | None, revoked_since: datetime | None
    ) -> list[ShareLink]:
        """Действующие и (если `revoked_since`) отозванные не раньше этого момента; новые первыми.
        `created_by` ограничивает список ссылками этого человека."""
        ...

    async def count_active(self, project_id: UUID, now: datetime) -> int: ...

    async def count_revoked(self, project_id: UUID, *, created_by: str | None, since: datetime) -> int: ...

    async def update(self, link_id: str, changes: ShareLinkChanges, now: datetime) -> ShareLink | None: ...

    async def revoke(
        self, link_id: str, *, by: str | None, reason: RevokeReason, now: datetime, replaced_by: str | None = None
    ) -> bool:
        """False, если ссылка уже отозвана или её нет."""
        ...

    async def touch_opened(self, link_id: str, now: datetime) -> None: ...

    async def visit_stats(self, link_ids: Sequence[str]) -> dict[str, LinkVisitStats]: ...

    async def visits(self, link_id: str, window: Window) -> Found[LinkVisit]: ...

    async def record_visit(
        self,
        link_id: str,
        visitor_kind: Literal["guest", "user"],
        visitor_id: str,
        visitor_name: str | None,
        ip: str | None,
        now: datetime,
    ) -> LinkVisitRecord: ...

    async def grant_user(self, link_id: str, user_id: str, project_id: UUID, now: datetime) -> None:
        """Ссылочное право вошедшего (`share_link_grants`); повтор ничего не меняет."""
        ...


class IGuestSessionRepository(Protocol):
    async def get_by_secret_hash(self, secret_hash: str, now: datetime) -> GuestSession | None:
        """Действующая сессия по хешу секрета cookie; истёкшая не находится."""
        ...

    async def create(self, session: GuestSession, secret_hash: str, ip: str | None, user_agent: str) -> None: ...

    async def touch(self, session_id: str, now: datetime, expires_at: datetime) -> None: ...

    async def rename(self, session_id: str, name: str | None) -> None: ...

    async def attach_link(self, session_id: str, link_id: str, project_id: UUID, now: datetime) -> None:
        """Ставит ссылку в сессию; прежняя ссылка того же проекта в этой сессии заменяется."""
        ...

    async def links_of(self, session_id: str) -> list[GuestLink]:
        """Ссылки сессии с проектами (неудалёнными); политику и срок проверяет вызывающий."""
        ...

    async def had_link_for(self, session_id: str, project_id: UUID) -> bool:
        """Была ли у сессии ссылка этого проекта (для понятного 404 `link_inactive`)."""
        ...

    async def detach_project(self, session_id: str, project_id: UUID) -> None: ...

    async def delete(self, session_id: str) -> None: ...

    async def purge_expired(self, now: datetime) -> int: ...


class IBuildPayerResolver(Protocol):
    """Чья квота и чей маршрут раннеров у сборки: пользователь сам; гость по ссылке (S7) ставит сборку от имени
    создателя ссылки, а если тот потерял право делиться или удалён, от имени владельца-человека проекта."""

    async def payer_for(self, actor: Actor, project_id: UUID) -> UUID: ...
