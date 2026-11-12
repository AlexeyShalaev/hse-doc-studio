"""Журнал писем (docs/design/mail-log.md): что ушло, кому, с каким итогом, без тела письма и ссылок.

Строка журнала хранит вид, язык, тему как ушла, получателя и безопасные параметры (`MailParams`): значения шаблона
из белого списка `SAFE_VALUES`, вид ссылки без самой ссылки, срок её действия и длину сообщения человека. По ним
карточка перерисовывает письмо тем же шаблоном; токен из ссылки в журнал не попадает, потому что его нет на входе.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from types import MappingProxyType
from urllib.parse import urlsplit

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail.catalog import catalog, placeholders
from hse_doc_studio.core.mail.compose import (
    MailTemplate,
    Redaction,
    RenderedMail,
    clean_note,
    compose,
    fixed_path,
    one_line,
    server_origin,
)
from hse_doc_studio.core.mail.samples import sample_mail

# Границы колонок `mail_log` (5.1).
TEMPLATE_MAX = 64
SUBJECT_MAX = 200
ERROR_TEXT_MAX = 300
ORIGIN_MAX = 48
DIGEST_LEN = 16
MESSAGE_ID_MAX = 255
# `task`, `request_id`, `ref_id`, `to_user_id`: varchar(64).
SHORT_FIELD_MAX = 64
# Чем заменяются логин и пароль SMTP в тексте сбоя (L16).
SECRET_MASK = "[скрыто]"  # noqa: S105 — замена секрета, не секрет


class MailStatus(StrEnum):
    """Итог попытки (L2): ушло, не ушло из-за сбоя, не отправлялось без SMTP, не положено получателю."""

    sent = "sent"
    failed = "failed"
    not_sent = "not_sent"
    suppressed = "suppressed"


class MailSkipReason(StrEnum):
    """Почему письмо не отправлялось: `smtp_off` у `not_sent`, остальные у `suppressed`."""

    smtp_off = "smtp_off"
    email_unverified = "email_unverified"
    account_blocked = "account_blocked"


class MailFailureClass(StrEnum):
    """Класс сбоя SMTP у `failed` (L16); `smtp_off`: настройки сняли между проверкой и отправкой."""

    auth = "auth"
    connect = "connect"
    timeout = "timeout"
    tls = "tls"
    recipient_refused = "recipient_refused"
    sender_refused = "sender_refused"
    data_refused = "data_refused"
    disconnected = "disconnected"
    smtp_off = "smtp_off"
    other = "other"


# Какие причины допустимы при каком итоге; у `sent` причины нет.
REASONS_BY_STATUS: Mapping[MailStatus, frozenset[str]] = MappingProxyType(
    {
        MailStatus.sent: frozenset(),
        MailStatus.failed: frozenset(MailFailureClass),
        MailStatus.not_sent: frozenset({MailSkipReason.smtp_off}),
        MailStatus.suppressed: frozenset({MailSkipReason.email_unverified, MailSkipReason.account_blocked}),
    }
)


class MailCause(StrEnum):
    """Кто вызвал письмо (L8): вошедший человек, запрос без входа или фоновая задача."""

    user = "user"
    anonymous = "anonymous"
    system = "system"


class MailLinkKind(StrEnum):
    """Что стояло в письме на месте ссылки: ссылка с токеном, адрес страницы без токена или ничего."""

    token = "token"  # noqa: S105 — вид ссылки, не токен
    page = "page"
    none = "none"


class MailOrigin(StrEnum):
    """Сценарий, из которого ушло письмо (L8); подписи в словаре админки `adminMail:origin.*`."""

    register = "register"
    resend_verification = "resend_verification"
    forgot_password = "forgot_password"  # noqa: S105 — сценарий, не пароль
    admin_invite = "admin_invite"
    admin_invite_resend = "admin_invite_resend"
    email_change = "email_change"
    admin_reset_link = "admin_reset_link"
    passkey_added = "passkey_added"
    admin_passkeys_reset = "admin_passkeys_reset"
    notification = "notification"
    project_invite = "project_invite"
    project_invite_resend = "project_invite_resend"
    signing_reinvite = "signing_reinvite"
    signing_auto_reminder = "signing_auto_reminder"
    smtp_test = "smtp_test"


class MailRefKind(StrEnum):
    """Объект, к которому относится письмо (L9)."""

    signing_route = "signing_route"
    project_invitation = "project_invitation"
    registration_invite = "registration_invite"
    access_request = "access_request"
    transfer = "transfer"
    passkey = "passkey"


# Белый список значений шаблона по видам (L3): только эти подстановки попадают в журнал. `email` и `server`
# сюда не входят: адрес получателя хранится в своей колонке, адрес установки в `MailParams.server`. Тест сверяет
# список с подстановками словарей писем, так что новое значение в тексте письма без решения здесь не пройдёт CI.
_PROJECT = frozenset({"actor", "project", "role"})
_SIGNING = frozenset({"actor", "project", "profile", "deadline"})
SAFE_VALUES: Mapping[MailTemplate, frozenset[str]] = MappingProxyType(
    {
        MailTemplate.verify_email: frozenset(),
        MailTemplate.reset_password: frozenset(),
        MailTemplate.invite: frozenset({"inviter"}),
        MailTemplate.email_change: frozenset(),
        MailTemplate.reset_notice: frozenset(),
        MailTemplate.passkey_added: frozenset({"name"}),
        MailTemplate.passkey_reset: frozenset({"count"}),
        MailTemplate.project_invitation: _PROJECT,
        MailTemplate.project_invitation_link: _PROJECT,
        MailTemplate.access_request: frozenset({"actor", "project"}),
        MailTemplate.transfer_request: frozenset({"actor", "project"}),
        MailTemplate.signing_request: _SIGNING,
        MailTemplate.signing_request_sign: _SIGNING,
        MailTemplate.signing_request_new_version: _SIGNING | {"changed"},
        MailTemplate.signing_reminder: _SIGNING,
        MailTemplate.signing_skipped: frozenset({"actor", "project", "profile"}),
        MailTemplate.signing_returned: frozenset({"actor", "project"}),
        MailTemplate.signing_completed: frozenset({"project", "profile"}),
        MailTemplate.smtp_test: frozenset(),
    }
)
SAFE_VALUE_KEYS: frozenset[str] = frozenset(key for keys in SAFE_VALUES.values() for key in keys)


_LINK_KINDS: Mapping[str, MailLinkKind] = MappingProxyType({kind.value: kind for kind in MailLinkKind})
_TEMPLATES: Mapping[str, MailTemplate] = MappingProxyType({template.value: template for template in MailTemplate})


@dataclass(frozen=True, kw_only=True)
class MailRequest:
    """Письмо, которое отправитель отдаёт диспетчеру: всё, из чего собирается письмо, и его место в журнале.

    `link_kind` решает отправитель, а не догадка по виду. У `token` ссылка обязательна и в журнал не попадает;
    у `page` в журнал идёт только путь ссылки (без адреса сервера, запроса и якоря), у видов с постоянной страницей
    (`fixed_path`) путь известен и без ссылки; у `none` ссылки нет.
    """

    template: MailTemplate
    lang: Lang
    to: str
    server_url: str | None
    origin: MailOrigin
    link_kind: MailLinkKind = MailLinkKind.none
    link: str | None = None
    ttl: timedelta | None = None
    expires_at: datetime | None = None
    values: Mapping[str, object] = field(default_factory=dict)
    note: str | None = None
    to_user_id: str | None = None
    project_id: str | None = None
    ref_kind: MailRefKind | None = None
    ref_id: str | None = None

    def __post_init__(self) -> None:
        if self.link_kind is MailLinkKind.token and not self.link:
            raise ValueError("a token link mail needs the link")
        if self.link_kind is MailLinkKind.none and (self.link or fixed_path(self.template)):
            raise ValueError(f"{self.template.value} carries a link, link_kind must not be none")
        if self.link_kind is MailLinkKind.token and fixed_path(self.template):
            raise ValueError(f"{self.template.value} links to a fixed page, not a token")
        if (self.ref_kind is None) != (self.ref_id is None):
            raise ValueError("ref_kind and ref_id go together")

    def render(self) -> RenderedMail:
        """Письмо как уйдёт: с настоящей ссылкой и сообщением человека."""
        return compose(
            self.template,
            self.lang,
            to=self.to,
            server_url=self.server_url,
            link=self.link,
            ttl=self.ttl,
            expires_at=self.expires_at,
            values=self.values,
            note=self.note,
        )


@dataclass(frozen=True, kw_only=True)
class MailParams:
    """Безопасные параметры письма (`mail_log.params`, 5.2): ни ссылки с токеном, ни сообщения человека."""

    values: Mapping[str, str] = field(default_factory=dict)
    link: MailLinkKind = MailLinkKind.none
    link_path: str | None = None
    ttl_s: int | None = None
    expires_at: datetime | None = None
    note_len: int = 0
    # Публичный адрес установки на момент отправки (`server_origin`); null, если он не задан.
    server: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "values": dict(self.values),
            "link": self.link.value,
            "link_path": self.link_path,
            "ttl_s": self.ttl_s,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "note_len": self.note_len,
            "server": self.server,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> MailParams:
        """Чтение строки журнала: незнакомые ключи и значения вне белого списка отбрасываются."""
        raw_values = data.get("values")
        values = (
            {str(k): str(v) for k, v in raw_values.items() if k in SAFE_VALUE_KEYS and isinstance(v, str)}
            if isinstance(raw_values, Mapping)
            else {}
        )
        link = data.get("link")
        link_kind = _LINK_KINDS.get(link, MailLinkKind.none) if isinstance(link, str) else MailLinkKind.none
        path = data.get("link_path")
        ttl_s = data.get("ttl_s")
        expires = data.get("expires_at")
        note_len = data.get("note_len")
        server = data.get("server")
        return cls(
            values=values,
            link=link_kind,
            link_path=path if link_kind is MailLinkKind.page and isinstance(path, str) else None,
            ttl_s=ttl_s if isinstance(ttl_s, int) and not isinstance(ttl_s, bool) else None,
            expires_at=datetime.fromisoformat(expires) if isinstance(expires, str) else None,
            note_len=note_len if isinstance(note_len, int) and not isinstance(note_len, bool) else 0,
            server=server if isinstance(server, str) else None,
        )


def _page_path(request: MailRequest) -> str | None:
    if request.link_kind is not MailLinkKind.page:
        return None
    if request.link:
        return urlsplit(request.link.strip()).path or "/"
    return fixed_path(request.template)


def safe_params(request: MailRequest) -> MailParams:
    """Параметры для журнала: значения белого списка этого вида (`one_line`, как в письме), путь страницы,
    срок ссылки и длина сообщения. Ссылка с токеном и текст сообщения сюда не попадают."""
    allowed = SAFE_VALUES.get(request.template, frozenset())
    values = {key: one_line(value) for key, value in request.values.items() if key in allowed and value is not None}
    return MailParams(
        values=values,
        link=request.link_kind,
        link_path=_page_path(request),
        ttl_s=int(request.ttl.total_seconds()) if request.ttl is not None else None,
        expires_at=request.expires_at,
        note_len=len(clean_note(request.note)) if request.note else 0,
        server=server_origin(request.server_url),
    )


@lru_cache(maxsize=len(MailTemplate) * len(Lang))
def template_digest(template: MailTemplate, lang: Lang) -> str:
    """Отпечаток шаблона вида на языке (L5): первые 16 hex SHA-256 от темы, текста и HTML образца.

    Меняется при любой правке словаря, `render.py`, `compose.py` и образцов `samples.py`: карточка тогда честно
    помечает письмо перерисованным. Кэш на процесс: шаблоны в работающем процессе не меняются.
    """
    mail = sample_mail(template, lang)
    digest = hashlib.sha256("\x00".join((mail.subject, mail.text, mail.html)).encode("utf-8"))
    return digest.hexdigest()[:DIGEST_LEN]


def known_template(value: str) -> MailTemplate | None:
    """Вид письма по значению из журнала; None, если такого вида в этой версии больше нет."""
    return _TEMPLATES.get(value)


@dataclass(frozen=True, kw_only=True)
class MailFailure:
    """Сбой отправки (L16): класс, код ответа SMTP и очищенный текст до `ERROR_TEXT_MAX` символов."""

    reason: MailFailureClass
    smtp_code: int | None = None
    text: str | None = None

    def describe(self) -> str:
        """Одна строка для человека и логов: `auth 535: текст`; так отвечает и тестовое письмо."""
        head = f"{self.reason.value} {self.smtp_code}" if self.smtp_code is not None else self.reason.value
        return f"{head}: {self.text}" if self.text else head


class MailSendError(Exception):
    """Сбой `IMailSender.send`, уже разобранный отправителем: только он знает логин и пароль, которые надо скрыть.

    Отправитель SMTP разбирает исключения `aiosmtplib` (`infra/identity/smtp_errors.classify`); без настроенного
    SMTP причина `smtp_off`. Любое другое исключение из `send` диспетчер записывает как `other`.
    """

    def __init__(self, failure: MailFailure) -> None:
        super().__init__(failure.describe())
        self.failure = failure


def clean_error_text(text: object, *, secrets: Iterable[str | None] = ()) -> str | None:
    """Текст сбоя для журнала (L16): секреты заменены на `SECRET_MASK` без учёта регистра, переводы строк и
    управляющие символы убраны, не длиннее `ERROR_TEXT_MAX`. None, если текста нет."""
    raw = str(text) if text is not None else ""
    hidden = sorted({secret for secret in secrets if secret}, key=len, reverse=True)
    if hidden:
        raw = re.compile("|".join(re.escape(secret) for secret in hidden), re.IGNORECASE).sub(SECRET_MASK, raw)
    cleaned = one_line(raw, ERROR_TEXT_MAX)
    return cleaned or None


@dataclass(frozen=True, kw_only=True)
class MailLogEntry:
    """Строка журнала (`mail_log`, 5.1). `id` выдаёт хранилище; у ещё не записанной строки он None.

    `template` и `lang` строки, а не перечисления: строка переживает удаление вида из `MailTemplate`.
    """

    at: datetime
    duration_ms: int
    template: str
    lang: str
    to_email: str
    subject: str
    status: MailStatus
    cause: MailCause
    origin: str
    params: MailParams
    template_digest: str
    to_user_id: str | None = None
    reason: str | None = None
    smtp_code: int | None = None
    error_text: str | None = None
    message_id: str | None = None
    attempts: int = 1
    actor_user_id: str | None = None
    task: str | None = None
    request_id: str | None = None
    project_id: str | None = None
    ref_kind: str | None = None
    ref_id: str | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        # То же, что CHECK таблицы: ушедшее письмо без Message-ID искать в логах почтового сервера нечем.
        if self.status is MailStatus.sent and not self.message_id:
            raise ValueError("a sent mail needs its Message-ID")

    @property
    def template_known(self) -> bool:
        return known_template(self.template) is not None


@dataclass(frozen=True)
class MailLogQuery:
    """Фильтры журнала (6.1), все по И; строки новые первыми, страница идёт ключом `before_id`."""

    templates: tuple[str, ...] = ()
    statuses: tuple[MailStatus, ...] = ()
    reason: str | None = None
    recipient_id: str | None = None
    recipient: str | None = None
    project_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    q: str | None = None
    before_id: int | None = None
    limit: int = 50

    @property
    def filtered(self) -> bool:
        return any(
            (
                self.templates,
                self.statuses,
                self.reason,
                self.recipient_id,
                self.recipient,
                self.project_id,
                self.since,
                self.until,
                self.q,
            )
        )


@dataclass(frozen=True)
class MailLogPage:
    items: list[MailLogEntry]
    next_before_id: int | None
    # Оценка числа строк без фильтров (по статистике таблицы); с фильтрами не считается.
    total_estimate: int | None = None


@dataclass(frozen=True)
class MailLogCounts:
    """Итоги за окно сводки (L14) и последний сбой в этом окне."""

    sent: int = 0
    failed: int = 0
    not_sent: int = 0
    suppressed: int = 0
    last_failure_at: datetime | None = None
    last_failure_reason: str | None = None


# Значение, которого у строки нет, а текст вида его требует: например, в новой версии шаблона появилась подстановка.
MISSING_VALUE = "…"
# Подстановки, которые письмо заполняет само: адрес получателя и установки, «Пользователь Студии», срок ссылки.
_SELF_FILLED = frozenset({"email", "server", "actor", "project", "duration", "date"})


@lru_cache(maxsize=len(MailTemplate) * len(Lang))
def _required_values(template: MailTemplate, lang: Lang) -> frozenset[str]:
    """Подстановки текстов вида, без которых письмо не собрать. Строки сведений (`details`) сюда не входят: без
    значения строка просто пропускается, как в ушедшем письме."""
    texts = catalog(lang)["mails"][template.value]
    found: set[str] = set()
    for key, value in texts.items():
        if key == "details":
            continue
        for text in value if isinstance(value, list) else [value]:
            if isinstance(text, str):
                found |= placeholders(text)
    return frozenset(found - _SELF_FILLED)


def _lang(value: str) -> Lang | None:
    return next((lang for lang in Lang if lang.value == value), None)


def rerender(entry: MailLogEntry) -> RenderedMail | None:
    """Письмо строки журнала глазами получателя, перерисованное текущим шаблоном (L3, L5).

    Собирается тем же `compose`, что шлёт, из безопасных параметров строки: на месте ссылки с токеном
    `layout.link_hidden`, у ссылки на страницу её путь текстом, на месте сообщения человека `layout.note_hidden`.
    Токена и сообщения на входе нет, поэтому в превью их быть не может. None, если вида или языка в этой версии нет.
    """
    template = known_template(entry.template)
    lang = _lang(entry.lang)
    if template is None or lang is None:
        return None
    params = entry.params
    values = dict.fromkeys(_required_values(template, lang), MISSING_VALUE) | dict(params.values)
    return compose(
        template,
        lang,
        to=entry.to_email,
        server_url=params.server,
        ttl=timedelta(seconds=params.ttl_s) if params.ttl_s is not None else None,
        expires_at=params.expires_at,
        values=values,
        redaction=Redaction(
            token_link=params.link is MailLinkKind.token,
            page_path=params.link_path if params.link is MailLinkKind.page else None,
            note=params.note_len > 0,
        ),
    )


def rerendered(entry: MailLogEntry) -> bool:
    """Шаблон вида менялся после отправки (L5): отпечаток строки не совпадает с текущим. У удалённого вида False:
    превью нет, сравнивать не с чем."""
    template = known_template(entry.template)
    lang = _lang(entry.lang)
    if template is None or lang is None:
        return False
    return entry.template_digest != template_digest(template, lang)
