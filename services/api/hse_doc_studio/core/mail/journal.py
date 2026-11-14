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
    # Повтор из журнала («Отправить ещё раз», «Отправить неушедшие»), раздел 14, V2.
    admin_resend = "admin_resend"


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
        MailTemplate.checkpoint_due: frozenset({"project", "profile", "deadline", "signing"}),
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
    # Повтор из журнала (V3): сообщения человека нет, в письме строка «сообщение есть во «Входящих»».
    note_in_inbox: bool = False

    def __post_init__(self) -> None:
        if self.note_in_inbox and self.note:
            raise ValueError("note_in_inbox replaces the note")
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
            note_in_inbox=self.note_in_inbox,
        )

    def to_json(self) -> dict[str, object]:
        """Запрос целиком для очереди автоповтора (V8): со ссылкой и сообщением, поэтому только шифртекстом."""
        return {
            "template": self.template.value,
            "lang": self.lang.value,
            "to": self.to,
            "server_url": self.server_url,
            "origin": self.origin.value,
            "link_kind": self.link_kind.value,
            "link": self.link,
            "ttl_s": int(self.ttl.total_seconds()) if self.ttl is not None else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "values": {str(k): _json_value(v) for k, v in self.values.items() if v is not None},
            "note": self.note,
            "to_user_id": self.to_user_id,
            "project_id": self.project_id,
            "ref_kind": self.ref_kind.value if self.ref_kind else None,
            "ref_id": self.ref_id,
            "note_in_inbox": self.note_in_inbox,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> MailRequest:
        """Обратно из очереди; ValueError, если вида письма или сценария в этой версии нет."""

        def text(key: str) -> str | None:
            value = data.get(key)
            return value if isinstance(value, str) else None

        ttl_s = data.get("ttl_s")
        expires = text("expires_at")
        raw_values = data.get("values")
        ref_kind = text("ref_kind")
        return cls(
            template=MailTemplate(str(data["template"])),
            lang=Lang(str(data["lang"])),
            to=str(data["to"]),
            server_url=text("server_url"),
            origin=MailOrigin(str(data["origin"])),
            link_kind=MailLinkKind(str(data.get("link_kind", MailLinkKind.none.value))),
            link=text("link"),
            ttl=timedelta(seconds=ttl_s) if isinstance(ttl_s, int) and not isinstance(ttl_s, bool) else None,
            expires_at=datetime.fromisoformat(expires) if expires else None,
            values={str(k): v for k, v in raw_values.items()} if isinstance(raw_values, Mapping) else {},
            note=text("note"),
            to_user_id=text("to_user_id"),
            project_id=text("project_id"),
            ref_kind=MailRefKind(ref_kind) if ref_kind else None,
            ref_id=text("ref_id"),
            note_in_inbox=data.get("note_in_inbox") is True,
        )


def _json_value(value: object) -> object:
    """Значение шаблона для очереди: числа как есть, остальное строкой (так его и подставит письмо)."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    return str(value)


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
    # Повтор из журнала: на месте сообщения строка «сообщение есть во «Входящих»» (V3).
    note_in_inbox: bool = False

    def to_json(self) -> dict[str, object]:
        extra: dict[str, object] = {"note_in_inbox": True} if self.note_in_inbox else {}
        return extra | {
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
            note_in_inbox=data.get("note_in_inbox") is True,
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
        note_in_inbox=request.note_in_inbox,
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
    # Версия 2 (раздел 14): запланированный автоповтор (V7), время последней попытки, если их больше одной,
    # и исходная строка ручного повтора (V2).
    next_attempt_at: datetime | None = None
    last_attempt_at: datetime | None = None
    resent_from_id: int | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        # То же, что CHECK таблицы: ушедшее письмо без Message-ID искать в логах почтового сервера нечем.
        if self.status is MailStatus.sent and not self.message_id:
            raise ValueError("a sent mail needs its Message-ID")

    @property
    def template_known(self) -> bool:
        return known_template(self.template) is not None

    @property
    def retrying(self) -> bool:
        """Письмо не ушло, но Студия ещё повторит отправку сама (V6)."""
        return self.status is MailStatus.failed and self.next_attempt_at is not None

    @property
    def tried_at(self) -> datetime:
        """Время последней попытки: у строки с одной попыткой это `at`."""
        return self.last_attempt_at or self.at


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
    # True: только ждущие автоповтора, False: без них, None: все (V13).
    retrying: bool | None = None
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
                self.retrying is not None,
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
    # Окончательные сбои: повторов больше не будет (V13).
    failed: int = 0
    not_sent: int = 0
    suppressed: int = 0
    # Не ушло, но Студия ещё повторит отправку сама.
    retrying: int = 0
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
        note_in_inbox=params.note_in_inbox and params.note_len == 0,
    )


def rerendered(entry: MailLogEntry) -> bool:
    """Шаблон вида менялся после отправки (L5): отпечаток строки не совпадает с текущим. У удалённого вида False:
    превью нет, сравнивать не с чем."""
    template = known_template(entry.template)
    lang = _lang(entry.lang)
    if template is None or lang is None:
        return False
    return entry.template_digest != template_digest(template, lang)


# Автоповтор временных сбоев (раздел 14, V6): паузы перед 2..5-й попыткой.
RETRY_DELAYS: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=30),
)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
# Сбои без кода SMTP, после которых сервер стоит попросить ещё раз: соединение не установилось или оборвалось.
_TRANSIENT_CLASSES = frozenset({MailFailureClass.connect, MailFailureClass.timeout, MailFailureClass.disconnected})
_SMTP_TEMPORARY = range(400, 500)


def is_transient(failure: MailFailure) -> bool:
    """Временный сбой (V6): ответ SMTP `4xx` любого класса или обрыв, таймаут, отказ в соединении без кода.

    Ответ `5xx` постоянный, как и сбой без кода других классов (`tls`, `smtp_off`, `other`)."""
    if failure.smtp_code is not None:
        return failure.smtp_code in _SMTP_TEMPORARY
    return failure.reason in _TRANSIENT_CLASSES


def next_retry_at(attempts: int, tried_at: datetime) -> datetime | None:
    """Когда повторить после `attempts` попыток (последняя в `tried_at`); None, если попытки кончились."""
    if attempts < 1 or attempts >= MAX_ATTEMPTS:
        return None
    return tried_at + RETRY_DELAYS[attempts - 1]


def link_expired(request: MailRequest, first_at: datetime, now: datetime) -> bool:
    """Ссылка с токеном уже не действует: слать письмо с ней незачем (V9)."""
    if request.link_kind is not MailLinkKind.token:
        return False
    expiry = request.expires_at or (first_at + request.ttl if request.ttl is not None else None)
    return expiry is not None and expiry <= now


# Окно ручного повтора от первой попытки (V4).
RESEND_WINDOW = timedelta(hours=72)
# Сколько писем за раз уходит по «Отправить неушедшие» (V11).
RESEND_BATCH_LIMIT = 200
_RESENDABLE = frozenset({MailStatus.failed, MailStatus.not_sent})


class ResendBlock(StrEnum):
    """Почему письмо нельзя отправить ещё раз (V1, V4, V5; таблица 14.2). Подписи `adminMail:resend.blocked.*`."""

    status = "status"
    token_link = "token_link"  # noqa: S105 — код причины, не токен
    smtp_test = "smtp_test"
    template_gone = "template_gone"
    retrying = "retrying"
    too_old = "too_old"
    already_resent = "already_resent"
    smtp_off = "smtp_off"
    recipient_gone = "recipient_gone"
    recipient_changed = "recipient_changed"
    recipient_blocked = "recipient_blocked"
    project_gone = "project_gone"
    invitation_done = "invitation_done"
    request_done = "request_done"
    transfer_done = "transfer_done"
    route_done = "route_done"
    object_gone = "object_gone"


def resend_block(entry: MailLogEntry, *, now: datetime, smtp_enabled: bool, resent: bool) -> ResendBlock | None:
    """Общие правила ручного повтора по самой строке (14.2), без обращения к объекту письма.

    `resent`: у строки уже есть успешный ручной повтор."""
    rules = (
        (entry.status not in _RESENDABLE, ResendBlock.status),
        (known_template(entry.template) is None or _lang(entry.lang) is None, ResendBlock.template_gone),
        (entry.params.link is MailLinkKind.token, ResendBlock.token_link),
        (entry.template == MailTemplate.smtp_test.value, ResendBlock.smtp_test),
        (entry.retrying, ResendBlock.retrying),
        (entry.at < now - RESEND_WINDOW, ResendBlock.too_old),
        (resent, ResendBlock.already_resent),
        (not smtp_enabled, ResendBlock.smtp_off),
    )
    return next((block for broken, block in rules if broken), None)


_REF_KINDS: Mapping[str, MailRefKind] = MappingProxyType({kind.value: kind for kind in MailRefKind})


def resend_request(entry: MailLogEntry, server_url: str | None) -> MailRequest:
    """Письмо ручного повтора из строки журнала (V3): те же значения белого списка, ссылка на страницу по пути на
    текущем адресе установки, на месте сообщения человека строка «сообщение есть во «Входящих»».

    Только для строк, прошедших `resend_block`: у вида есть шаблон, ссылки с токеном нет."""
    template = known_template(entry.template)
    lang = _lang(entry.lang)
    if template is None or lang is None or entry.params.link is MailLinkKind.token:
        raise ValueError("this mail cannot be rebuilt from the log")
    params = entry.params
    link: str | None = None
    if params.link is MailLinkKind.page and fixed_path(template) is None:
        origin = server_origin(server_url)
        link = f"{origin}{params.link_path}" if origin and params.link_path else None
    link_kind = MailLinkKind.page if link or fixed_path(template) else MailLinkKind.none
    ref_kind = _REF_KINDS.get(entry.ref_kind) if entry.ref_kind else None
    return MailRequest(
        template=template,
        lang=lang,
        to=entry.to_email,
        server_url=server_url,
        origin=MailOrigin.admin_resend,
        link_kind=link_kind,
        link=link,
        ttl=timedelta(seconds=params.ttl_s) if params.ttl_s is not None else None,
        expires_at=params.expires_at,
        # Подстановка, которой у старой строки нет (шаблон обновился), не роняет письмо, как и в карточке.
        values=dict.fromkeys(_required_values(template, lang), MISSING_VALUE) | dict(params.values),
        to_user_id=entry.to_user_id,
        project_id=entry.project_id,
        ref_kind=ref_kind,
        ref_id=entry.ref_id if ref_kind is not None else None,
        note_in_inbox=params.note_len > 0 or params.note_in_inbox,
    )


@dataclass(frozen=True)
class MailRetryJob:
    """Созревший автоповтор из очереди (V9). `request` None, если шифртекст не открылся или запрос не читается
    этой версией: повтор тогда прекращается."""

    entry_id: int
    attempts: int
    first_at: datetime
    request: MailRequest | None


@dataclass(frozen=True, kw_only=True)
class MailAttempt:
    """Исход очередной попытки для той же строки журнала (V7). `next_attempt_at` None: повторов больше не будет."""

    status: MailStatus
    attempts: int
    tried_at: datetime
    duration_ms: int
    reason: str | None = None
    smtp_code: int | None = None
    error_text: str | None = None
    message_id: str | None = None
    next_attempt_at: datetime | None = None
