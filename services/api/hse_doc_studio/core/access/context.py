"""Актор текущего запроса; наследуется задачами, созданными внутри запроса (как core.i18n)."""

from __future__ import annotations

import contextvars

from hse_doc_studio.core.access.entities import Actor

# По умолчанию None, а не local: пропущенный гард в серверном режиме не должен
# превращаться в полный доступ. None значит «запроса нет» (например, восстановление при старте).
_current_actor: contextvars.ContextVar[Actor | None] = contextvars.ContextVar("current_actor", default=None)


def set_current_actor(actor: Actor | None) -> None:
    _current_actor.set(actor)


def current_actor() -> Actor | None:
    return _current_actor.get()
