"""Доставка ссылок из писем: почтой, если настроен SMTP, иначе ссылка возвращается вызывающему.

Письмо уходит через `MailDispatcher` (docs/design/mail-log.md, L1): он собирает его (`core.mail`, тема, текст и
HTML на языке получателя), отправляет и пишет строку журнала писем на каждую попытку, включая пропуск без SMTP.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import timedelta

import structlog

from hse_doc_studio.core.identity.entities import MailKind
from hse_doc_studio.core.mail import MailTemplate, resolve_lang
from hse_doc_studio.core.mail.compose import fixed_path
from hse_doc_studio.core.mail.journal import MailLinkKind, MailOrigin, MailRefKind, MailRequest, MailSkipReason
from hse_doc_studio.use_cases.mail.dispatch import MailDispatcher

logger = structlog.get_logger(__name__)


def auth_link(public_url: str | None, path: str, token: str) -> str:
    """Ссылка на страницу клиента: `<public_url>/<path>/<token>`."""
    base = (public_url or "").rstrip("/")
    return f"{base}{path}/{token}"


class LinkDelivery:
    """Письма входа и аккаунта (пути P1..P7 журнала писем): ссылки с токеном и уведомления без ссылки.

    Ссылка с одноразовым токеном нигде не хранится (в БД токены лежат хешами, в журнал писем идёт только признак
    «была ссылка») и возвращается только вызывающему, если письмо не ушло: показывать ли её, решает вызывающий
    (анонимным маршрутам нельзя). С `background=True` отправка идёт отдельной задачей: запрос не ждёт SMTP (до его
    таймаута), а время ответа не выдаёт, существует ли адрес. Сбой такой отправки вызывающему ссылку уже не
    вернёт: он виден в журнале писем, а человеку нужно запросить письмо заново.
    """

    def __init__(
        self,
        mail: MailDispatcher,
        *,
        background: bool = False,
        public_url: str | None = None,
    ) -> None:
        self._mail = mail
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
        return self._mail.enabled

    async def deliver(
        self,
        kind: MailKind,
        to_email: str,
        link: str,
        *,
        origin: MailOrigin,
        locale: str | None = None,
        ttl: timedelta | None = None,
        params: Mapping[str, object] | None = None,
        to_user_id: str | None = None,
        ref_kind: MailRefKind | None = None,
        ref_id: str | None = None,
    ) -> str | None:
        """Ссылка для показа человеку (copyable) либо None, если письмо ушло или ушло в фоновую отправку.

        Язык письма: язык получателя, если он известен, иначе язык интерфейса запроса. `ttl` попадает в письмо
        как срок действия ссылки. Без SMTP письмо не отправляется, в журнале строка `not_sent`.
        """
        request = self._request(
            kind, to_email, locale, origin,
            link=link, ttl=ttl, params=params, to_user_id=to_user_id, ref_kind=ref_kind, ref_id=ref_id,
        )  # fmt: skip
        if not self._mail.enabled:
            await self._mail.skip(request, MailSkipReason.smtp_off)
            return link
        if self._background:
            # Задача копирует контекст: журнал запишет того же вызвавшего и тот же `request_id`, что у запроса.
            task = asyncio.create_task(self._send_in_background(request))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
            return None
        # Сбой почты не ломает регистрацию: человек получит ссылку другим путём, сбой записан в журнал.
        outcome = await self._mail.send(request)
        return None if outcome.sent else link

    async def notify(
        self,
        kind: MailKind,
        to_email: str,
        *,
        origin: MailOrigin,
        locale: str | None = None,
        params: Mapping[str, object] | None = None,
        to_user_id: str | None = None,
        ref_kind: MailRefKind | None = None,
        ref_id: str | None = None,
    ) -> bool:
        """Уведомление без ссылки с токеном; ушло ли оно. Сбой не мешает действию, о котором уведомляют.

        Без SMTP письмо не отправляется (строка `not_sent` в журнале), событие остаётся в журнале аудита.
        """
        request = self._request(
            kind, to_email, locale, origin, params=params, to_user_id=to_user_id, ref_kind=ref_kind, ref_id=ref_id
        )
        return (await self._mail.send(request)).sent

    def _request(
        self,
        kind: MailKind,
        to_email: str,
        locale: str | None,
        origin: MailOrigin,
        *,
        link: str | None = None,
        ttl: timedelta | None = None,
        params: Mapping[str, object] | None = None,
        to_user_id: str | None = None,
        ref_kind: MailRefKind | None = None,
        ref_id: str | None = None,
    ) -> MailRequest:
        template = MailTemplate(kind.value)
        if link is not None:
            link_kind = MailLinkKind.token
        else:
            # Уведомления о passkey ведут на постоянную страницу настроек аккаунта, остальные без ссылки.
            link_kind = MailLinkKind.page if fixed_path(template) else MailLinkKind.none
        return MailRequest(
            template=template,
            lang=resolve_lang(locale),
            to=to_email,
            server_url=self._public_url,
            origin=origin,
            link_kind=link_kind,
            link=link,
            ttl=ttl,
            values=dict(params or {}),
            to_user_id=to_user_id,
            ref_kind=ref_kind,
            ref_id=ref_id,
        )

    async def _send_in_background(self, request: MailRequest) -> None:
        try:
            await self._mail.send(request)
        except Exception:
            # Диспетчер не бросает из-за почты и журнала; остаётся ошибка в коде письма.
            logger.exception("link_mail_failed", template=request.template.value, origin=request.origin.value)
