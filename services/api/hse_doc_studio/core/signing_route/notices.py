"""Уведомления маршрута подписания: кому, с каким ключом повтора, с письмом или без (docs/design/signing-route.md, 6.6).

Расчёт называет уведомления эффектом `Notify` (запросы, остановка, завершение), сценарии добавляют свои через
`notice_for` (возврат, отмена) и напоминание. Доставку делает порт `ISigningNotifier` (`ports.py`) в той же
транзакции, что и запись маршрута с событиями (раздел 5.8). Запросы до сохранения маршрута помечаются у участников
(`mark_notified`, для набора уведомлений `mark_requests`): иначе следующий расчёт повторил бы их в этом раунде (5.4).

Порядок в сценарии:

```python
notices = notices_in(evaluation.effects) + (notice_for(route, Notice.returned),)  # что есть
async with uow.begin():
    route = mark_requests(route, notices, at=now)
    route = await routes.save(route, events=events)
    await signing_notifier.notify(route, notices, actor_id=actor, comment=comment)
```
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.signing_route.effects import Effect, Notify
from hse_doc_studio.core.signing_route.entities import Notice, RequestOutcome, SigningRoute
from hse_doc_studio.core.signing_route.transitions import mark_notified

# Письмо по виду уведомления: запрос и напоминание подписанту, возврат и завершение только автору (6.6).
_MAILED_TO_ANYONE = frozenset({Notice.request, Notice.reminder})
_MAILED_TO_SENDER = frozenset({Notice.returned, Notice.completed})
# О своём же действии человек не уведомляется: вернувший на доработку и отменивший маршрут.
_SKIP_ACTOR = frozenset({Notice.returned, Notice.cancelled})


@dataclass(frozen=True)
class Recipient:
    """Адресат уведомления маршрута.

    `participant_id` участник, от имени которого он получает уведомление (None: только как отправивший маршрут);
    `sender` он же отправил маршрут, то есть «автор» в таблице 6.6.
    """

    user_id: UUID
    participant_id: UUID | None
    sender: bool = False


def notices_in(effects: Iterable[Effect]) -> tuple[Notify, ...]:
    """Уведомления среди эффектов расчёта."""
    return tuple(effect for effect in effects if isinstance(effect, Notify))


def recipients(route: SigningRoute, notify: Notify, *, actor_id: UUID | None = None) -> tuple[Recipient, ...]:
    """Кому уведомление: участники с аккаунтом и, если `notify.sender`, отправивший маршрут.

    Один человек в двух ролях (автор и участник, два участника) получает одно уведомление. Приглашённый, который
    ещё не принял приглашение, уведомлений не получает: запрос придёт ему при принятии. Вернувший на доработку и
    отменивший маршрут о своём действии не уведомляются.
    """
    found: dict[UUID, UUID | None] = {}
    for participant_id in notify.participant_ids:
        p = route.participant(participant_id)
        if p.user_id is not None:
            found.setdefault(p.user_id, p.id)
    if notify.sender and route.sent_by is not None:
        found.setdefault(route.sent_by, None)
    if notify.notice in _SKIP_ACTOR and actor_id is not None:
        found.pop(actor_id, None)
    return tuple(Recipient(user_id, pid, sender=user_id == route.sent_by) for user_id, pid in found.items())


def request_turn(outcome: RequestOutcome | None) -> str:
    """Ход запроса для ключа повтора: «согласовать» (`approve`, `approve_sign`) или «подписать итоговый PDF»."""
    return "sign" if outcome is RequestOutcome.sign else "approve"


def dedupe_key(route: SigningRoute, notify: Notify, recipient: Recipient) -> str:
    """`signing:<маршрут>:<раунд>:<участник>:<вид>`, у запроса ещё ход: `...:signing_request:approve|sign`.

    Повтор с тем же ключом не создаёт второе уведомление, а поднимает прежнее (напоминание поднимает своё).
    Автор, который не участник, вместо id участника получает `sender`.
    """
    who = recipient.participant_id.hex if recipient.participant_id is not None else "sender"
    key = f"signing:{route.id.hex}:{route.round}:{who}:{notify.notice.value}"
    if notify.notice is Notice.request:
        key = f"{key}:{request_turn(notify.outcome)}"
    return key


def mails(notify: Notify, recipient: Recipient) -> bool:
    """Уходит ли этому адресату письмо (если настроен SMTP): запрос и напоминание всем, возврат и завершение автору."""
    if notify.notice in _MAILED_TO_ANYONE:
        return True
    return notify.notice in _MAILED_TO_SENDER and recipient.sender


def mark_requests(route: SigningRoute, notices: Iterable[Notify], *, at: datetime) -> SigningRoute:
    """Запомнить у участников отправленные запросы (`mark_notified`), чтобы расчёт их не повторял.

    Вызывается до сохранения маршрута в той же транзакции, что и `ISigningNotifier.notify`. Запрос без исхода
    и прочие уведомления не помечаются.
    """
    for notify in notices:
        if notify.notice is not Notice.request or notify.outcome is None:
            continue
        for participant_id in notify.participant_ids:
            route = mark_notified(route, participant_id, notify.outcome, at=at)
    return route
