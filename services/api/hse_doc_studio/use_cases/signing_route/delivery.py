"""Доставка уведомлений маршрута подписания (`ISigningNotifier`): «Входящие» и письма.

docs/design/signing-route.md, раздел 6.6.

Каждое уведомление это обычное уведомление «Входящих» (`INotifier`), поэтому оно пишется в транзакции сценария
маршрута, а письмо уходит отдельной задачей и только при настроенном SMTP. Подписи на момент события:

| Вид | `actor_name` | `outcome` | `excerpt` |
|---|---|---|---|
| `signing_request`, `signing_reminder` | отправивший маршрут | ход: `approve`, `approve_sign`, `sign` | точка |
| `signing_returned` | вернувший на доработку | нет | комментарий возврата |
| `signing_paused` | чьё действие остановило (если известно) | причина остановки (`StopReason`) | точка |
| `signing_completed` | нет | нет | точка |
| `signing_cancelled` | отменивший | нет | точка |
| `signing_new_version` | отправивший маршрут | нет | точка |

Во всех: `project_id`, `project_name`, `ref_id` (id маршрута), `profile_id`, `deadline` (срок, ISO 8601) и
`new_version` (12.6): true только у запроса раунда новой версии, в котором изменился документ получателя. Письму
такого запроса нужны ещё сообщение маршрута («Что изменилось» его заменяет) и названия изменившихся документов
(`message`, `changed_names`). Названия точки и документов берутся на языке аккаунта получателя.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.entities import Notice, SigningRoute
from hse_doc_studio.core.signing_route.notices import Recipient, dedupe_key, mails, recipients
from hse_doc_studio.core.signing_route.ports import IRouteLabels, RouteLabels

# Комментарий возврата до 2000 символов (RETURN_COMMENT_MAX); во «Входящих» и письме хватит начала.
_EXCERPT_MAX = 500


class SigningNotifier:
    def __init__(self, notifier: INotifier, users: IUserRepository, labels: IRouteLabels) -> None:
        self._notifier = notifier
        self._users = users
        self._labels = labels

    async def notify(
        self,
        route: SigningRoute,
        notices: Sequence[Notify],
        *,
        actor_id: UUID | None = None,
        comment: str | None = None,
    ) -> None:
        if not notices:
            return
        labels = await self._labels.labels(route.project_id, route.profile_id) or RouteLabels(project_name="")
        for notify in notices:
            actor = await self._name(self._actor(route, notify, actor_id))
            for recipient in recipients(route, notify, actor_id=actor_id):
                await self._send(route, notify, recipient, labels, actor, comment)

    async def _send(  # noqa: PLR0913 — подписи одного уведомления
        self,
        route: SigningRoute,
        notify: Notify,
        recipient: Recipient,
        labels: RouteLabels,
        actor: str | None,
        comment: str | None,
    ) -> None:
        user_id = recipient.user_id.hex
        user = await self._users.get(user_id)
        locale = user.locale if user is not None else None
        returned = notify.notice is Notice.returned
        changed = self._changed_docs(route, notify, recipient)
        payload = NotificationPayload(
            project_id=str(route.project_id),
            project_name=labels.project_name or None,
            actor_name=actor,
            ref_id=str(route.id),
            outcome=self._outcome(route, notify, recipient),
            excerpt=_clip(comment) if returned else labels.profile(locale, route.profile_id),
            profile_id=route.profile_id,
            deadline=route.deadline.isoformat() if route.deadline is not None else None,
            new_version=bool(changed),
            message=_clip(route.message) if changed else None,
            changed_names=", ".join(f"«{labels.doc(locale, doc_id)}»" for doc_id in changed) or None,
        )
        await self._notifier.notify(
            user_id,
            NotificationKind(notify.notice.value),
            payload,
            dedupe_key=dedupe_key(route, notify, recipient),
            mail=mails(notify, recipient),
        )

    @staticmethod
    def _changed_docs(route: SigningRoute, notify: Notify, recipient: Recipient) -> tuple[str, ...]:
        """Документы получателя, которые раунд новой версии изменил; только у запроса (12.6)."""
        if notify.notice is not Notice.request or recipient.participant_id is None:
            return ()
        mine = set(route.participant(recipient.participant_id).doc_ids(route.docs))
        return tuple(doc_id for doc_id in route.round_changed_docs if doc_id in mine)

    @staticmethod
    def _actor(route: SigningRoute, notify: Notify, actor_id: UUID | None) -> UUID | None:
        """Запрос, напоминание и новая версия идут от отправившего маршрут; возврат от вернувшего; прочее от
        `actor_id`."""
        if notify.notice in (Notice.request, Notice.reminder, Notice.new_version):
            return route.sent_by
        if notify.notice is Notice.returned and route.stopped_by is not None:
            stopped = next((p for p in route.participants if p.id == route.stopped_by), None)
            if stopped is not None and stopped.user_id is not None:
                return stopped.user_id
        return actor_id

    @staticmethod
    def _outcome(route: SigningRoute, notify: Notify, recipient: Recipient) -> str | None:
        if notify.notice is Notice.paused:
            return route.stop_reason.value if route.stop_reason is not None else None
        if notify.notice is Notice.request:
            return notify.outcome.value if notify.outcome is not None else None
        if notify.notice is Notice.reminder:
            if notify.outcome is not None:
                return notify.outcome.value
            # Напоминание о последнем запросе этого раунда.
            if recipient.participant_id is not None:
                last = route.participant(recipient.participant_id).notified
                if last is not None and last.round == route.round:
                    return last.outcome.value
        return None

    async def _name(self, user_id: UUID | None) -> str | None:
        if user_id is None:
            return None
        user = await self._users.get(user_id.hex)
        return user.name if user is not None and user.name.strip() else None


def _clip(text: str | None) -> str | None:
    if text is None or not text.strip():
        return None
    cleaned = text.strip()
    return cleaned if len(cleaned) <= _EXCERPT_MAX else cleaned[: _EXCERPT_MAX - 1].rstrip() + "…"
