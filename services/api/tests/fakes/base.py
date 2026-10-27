"""База InMemory-реализаций портов: данные разложены по владельцу из current_actor()."""

from __future__ import annotations

from collections import defaultdict
from typing import Generic, TypeVar

from hse_doc_studio.core.access.context import current_actor

T = TypeVar("T")


class ActorRequired(RuntimeError):  # noqa: N818 — имя из плана этапа 2, как у будущего порта
    """Запись или чтение без актора: в серверном режиме это пропущенный гард."""


def owner_key() -> str:
    actor = current_actor()
    if actor is None:
        raise ActorRequired("нет current_actor()")
    return actor.key or actor.kind.value


class OwnedStore(Generic[T]):
    """Словарь id -> значение отдельно для каждого владельца."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, T]] = defaultdict(dict)

    def put(self, item_id: str, value: T) -> None:
        self._data[owner_key()][item_id] = value

    def get(self, item_id: str) -> T | None:
        return self._data[owner_key()].get(item_id)

    def delete(self, item_id: str) -> bool:
        return self._data[owner_key()].pop(item_id, None) is not None

    def items(self) -> dict[str, T]:
        return dict(self._data[owner_key()])
