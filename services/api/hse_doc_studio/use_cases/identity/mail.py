"""Доставка ссылок из писем: почтой, если настроен SMTP, иначе ссылка возвращается вызывающему.

Письмо собирает `core.mail`: тема, текст и HTML на языке получателя."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta

from hse_doc_studio.core.identity.entities import MailKind, MailOutboxEntry
from hse_doc_studio.core.identity.protocols import IMailOutboxRepository, IMailSender
from hse_doc_studio.core.mail import MailTemplate, RenderedMail, compose, resolve_lang

_log = logging.getLogger(__name__)


def auth_link(public_url: str | None, path: str, token: str) -> str:
    """Ссылка на страницу клиента: `<public_url>/<path>/<token>`."""
    base = (public_url or "").rstrip("/")
    return f"{base}{path}/{token}"


class LinkDelivery:
    """Письмо уходит по SMTP; без SMTP или при сбое в outbox остаётся запись о неушедшем письме, но без ссылки.

    Ссылка с одноразовым токеном нигде не хранится (в БД токены лежат хешами) и возвращается только вызывающему:
    анонимным маршрутам её показывать нельзя. С `background=True` отправка идёт отдельной задачей: запрос не ждёт
    SMTP (до его таймаута), а время ответа не выдаёт, существует ли адрес. Сбой такой отправки вызывающему
    ссылку уже не вернёт: нужно запросить письмо заново.
    """

    def __init__(
        self,
        sender: IMailSender,
        outbox: IMailOutboxRepository,
        ttl: timedelta = timedelta(days=7),
        *,
        background: bool = False,
        public_url: str | None = None,
    ) -> None:
        self._sender = sender
        self._outbox = outbox
        self._ttl = ttl
        self._background = background
        self._public_url = public_url
        # Ссылки на задачи: цикл событий держит задачи слабо, и незавершённая отправка могла бы пропасть.
        self._pending: set[asyncio.Task[None]] = set()

    async def drain(self) -> None:
        """Дожидается отправок, начатых в фоне (остановка и тесты)."""
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

    @property
    def smtp_enabled(self) -> bool:
        return self._sender.enabled

    async def deliver(
        self,
        kind: MailKind,
        to_email: str,
        link: str,
        now: datetime,
        *,
        locale: str | None = None,
        ttl: timedelta | None = None,
        params: Mapping[str, object] | None = None,
    ) -> str | None:
        """Ссылка для показа человеку (copyable) либо None, если письмо ушло.

        Язык письма: язык получателя, если он известен, иначе язык интерфейса запроса. `ttl` попадает в письмо
        как срок действия ссылки.
        """
        if self._sender.enabled:
            mail = self._render(kind, to_email, locale, link=link, ttl=ttl, params=params)
            if self._background:
                task = asyncio.create_task(self._send_in_background(kind, to_email, now, mail))
                self._pending.add(task)
                task.add_done_callback(self._pending.discard)
                return None
            try:
                await self._sender.send(to_email, mail.subject, mail.text, html=mail.html)
            except Exception:
                # Сбой почты не должен ломать регистрацию: человек получит ссылку другим путём.
                _log.warning("mail delivery failed, outbox entry kept", extra={"kind": kind.value})
            else:
                return None
        await self._keep_in_outbox(kind, to_email, now)
        return link

    def _render(
        self,
        kind: MailKind,
        to_email: str,
        locale: str | None,
        *,
        link: str | None = None,
        ttl: timedelta | None = None,
        params: Mapping[str, object] | None = None,
    ) -> RenderedMail:
        return compose(
            MailTemplate(kind.value),
            resolve_lang(locale),
            to=to_email,
            server_url=self._public_url,
            link=link,
            ttl=ttl,
            values=params,
        )

    async def _send_in_background(self, kind: MailKind, to_email: str, now: datetime, mail: RenderedMail) -> None:
        try:
            await self._sender.send(to_email, mail.subject, mail.text, html=mail.html)
        except Exception:
            _log.warning("mail delivery failed, outbox entry kept", extra={"kind": kind.value})
            try:
                await self._keep_in_outbox(kind, to_email, now)
            except Exception:
                _log.exception("mail outbox write failed", extra={"kind": kind.value})

    async def _keep_in_outbox(self, kind: MailKind, to_email: str, now: datetime) -> None:
        # Ссылку не сохраняем: открытый токен в БД и бэкапах позволял бы захватить аккаунт.
        await self._outbox.add(
            MailOutboxEntry(
                id=uuid.uuid4().hex,
                kind=kind,
                to_email=to_email,
                link="",
                created_at=now,
                expires_at=now + self._ttl,
            )
        )

    async def notify(
        self,
        kind: MailKind,
        to_email: str,
        *,
        locale: str | None = None,
        params: Mapping[str, object] | None = None,
    ) -> bool:
        """Уведомление без ссылки; уходит только по SMTP, сбой не мешает действию, о котором уведомляют.

        Без SMTP молча пропускается: событие остаётся в журнале аудита.
        """
        if not self._sender.enabled:
            return False
        mail = self._render(kind, to_email, locale, params=params)
        try:
            await self._sender.send(to_email, mail.subject, mail.text, html=mail.html)
        except Exception:
            _log.warning("mail notice failed", extra={"kind": kind.value})
            return False
        return True
