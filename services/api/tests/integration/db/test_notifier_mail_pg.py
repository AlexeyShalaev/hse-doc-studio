"""Письмо уведомления на настоящей Postgres: фоновая отправка не делит сессию с транзакцией события.

Регрессия 0.29.0: `Notifier` запускал письмо задачей, которая наследовала ambient-транзакцию запроса, и пока событие
ещё писало в БД, задача шла в ту же `AsyncSession` (asyncpg: «another operation is in progress»). Письмо падало, в
журнале оставалась строка `failed`. Теперь письмо стартует после коммита события и только в своей сессии.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.mail.journal import MailOrigin, MailSkipReason
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.notifications import PostgresNotificationRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from hse_doc_studio.use_cases.notifications.notifier import Notifier
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

NOW = datetime.now(UTC)
USER = "u_signer"
PAYLOAD = NotificationPayload(project_name="ВКР", actor_name="Автор")
_UNREAD = text("SELECT count(*) FROM notifications WHERE user_id = :u")


class _Mailer:
    """Письмо глазами получателя: что ушло и видна ли в этот момент закоммиченная строка уведомления."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions
        self.sent: list[tuple[str, NotificationKind, int]] = []

    @property
    def enabled(self) -> bool:
        return True

    async def send_notification(
        self,
        to_email: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        locale: str | None,
        to_user_id: str | None = None,
        origin: MailOrigin = MailOrigin.notification,
    ) -> bool:
        # Как диспетчер писем, который читает настройки SMTP из БД перед отправкой.
        async with self._sessions.use() as session:
            await session.execute(text("SELECT pg_sleep(0.05)"))
            visible = int((await session.execute(_UNREAD, {"u": to_user_id})).scalar_one())
        self.sent.append((to_email, kind, visible))
        return True

    async def skip_notification(
        self,
        to_email: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        locale: str | None,
        reason: MailSkipReason,
        to_user_id: str | None = None,
        origin: MailOrigin = MailOrigin.notification,
    ) -> None:
        raise AssertionError(f"получатель открыт и подтверждён, пропуск не ожидался: {reason}")

    async def send_invitation(self, *args: object, **kwargs: object) -> bool:
        raise AssertionError("не используется")


async def _stand(engine: AsyncEngine) -> tuple[SessionProvider, Notifier, _Mailer]:
    sessions = SessionProvider(create_sessionmaker(engine))
    async with sessions.use() as db:
        db.add(
            UserRow(
                id=USER,
                email="signer@example.org",
                email_normalized="signer@example.org",
                name="Подписант",
                status="active",
                email_verified=True,
                created_at=NOW,
            )
        )
    mailer = _Mailer(sessions)
    notifier = Notifier(
        PostgresNotificationRepository(sessions),
        SqlUserRepository(sessions),
        mailer,  # type: ignore[arg-type]
    )
    return sessions, notifier, mailer


async def _rest_of_event(sessions: SessionProvider, *, busy: bool) -> None:
    """Событие после уведомления ещё работает с БД в своей транзакции (переход маршрута, аудит) или сразу
    выходит к коммиту."""
    if busy:
        async with sessions.use() as session:
            await session.execute(text("SELECT pg_sleep(0.2)"))


# busy: гонка за соединение транзакции события; idle: письмо до коммита не видит строк события.
EVENT_SHAPES = pytest.mark.parametrize("busy", [True, False], ids=["busy", "idle"])


@EVENT_SHAPES
async def test__notify_inside_event_transaction__mail_goes_after_commit_in_own_session(
    pg_migrated_engine: AsyncEngine, busy: bool
) -> None:
    sessions, notifier, mailer = await _stand(pg_migrated_engine)

    async with SqlUnitOfWork(sessions).begin():
        await notifier.notify(USER, NotificationKind.signing_request, PAYLOAD)
        await _rest_of_event(sessions, busy=busy)
    await notifier.drain()

    # Письмо ушло, и в момент отправки строка уведомления уже закоммичена и видна из своей сессии.
    assert mailer.sent == [("signer@example.org", NotificationKind.signing_request, 1)]


async def _failed_event(sessions: SessionProvider, notifier: Notifier, *, busy: bool) -> None:
    async with SqlUnitOfWork(sessions).begin():
        await notifier.notify(USER, NotificationKind.signing_completed, PAYLOAD)
        await _rest_of_event(sessions, busy=busy)
        raise RuntimeError("event failed")


@EVENT_SHAPES
async def test__notify_inside_rolled_back_event__no_mail(pg_migrated_engine: AsyncEngine, busy: bool) -> None:
    sessions, notifier, mailer = await _stand(pg_migrated_engine)

    with pytest.raises(RuntimeError, match="event failed"):
        await _failed_event(sessions, notifier, busy=busy)
    await notifier.drain()

    assert mailer.sent == []
    async with sessions.use() as session:
        assert (await session.execute(_UNREAD, {"u": USER})).scalar_one() == 0


async def test__notify_outside_transaction__mail_goes_right_away(pg_migrated_engine: AsyncEngine) -> None:
    sessions, notifier, mailer = await _stand(pg_migrated_engine)

    await notifier.notify(USER, NotificationKind.signing_request, PAYLOAD)
    await notifier.drain()

    assert mailer.sent == [("signer@example.org", NotificationKind.signing_request, 1)]
