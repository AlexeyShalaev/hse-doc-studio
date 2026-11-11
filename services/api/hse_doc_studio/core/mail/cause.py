"""Кто вызвал письмо (docs/design/mail-log.md, L8): берётся из контекста процесса, через слои не передаётся.

- `user`: вошедший человек (`current_actor`); фоновые отправки, начатые запросом, наследуют его актора;
- `system`: прогон периодической задачи `BackgroundTaskRunner` (`current_background_task`), даже если внутри
  прогона стоит актор: тик задачи лидера не действие человека;
- `anonymous`: всё остальное, то есть запрос без входа (регистрация, «Забыли пароль») или гость по ссылке.

`request_id` из `RequestIdMiddleware`: у фоновых отправок запроса он тот же, у задач лидера None.
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.background import current_background_task
from hse_doc_studio.core.mail.journal import MailCause
from hse_doc_studio.core.request_id import current_request_id


@dataclass(frozen=True)
class MailCaller:
    cause: MailCause
    actor_user_id: str | None = None
    task: str | None = None
    request_id: str | None = None


def current_caller() -> MailCaller:
    """Кто вызвал письмо в текущем контексте (запрос, его фоновая задача или прогон задачи лидера)."""
    request_id = current_request_id()
    task = current_background_task()
    if task is not None:
        return MailCaller(MailCause.system, task=task, request_id=request_id)
    actor = current_actor()
    if actor is not None and actor.kind is ActorKind.user and actor.id:
        return MailCaller(MailCause.user, actor_user_id=actor.id, request_id=request_id)
    return MailCaller(MailCause.anonymous, request_id=request_id)
