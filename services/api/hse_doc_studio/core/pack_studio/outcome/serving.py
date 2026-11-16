"""Выдача результата по HTTP без ввода-вывода: кэш по ключу, ETag и разбор `If-None-Match` (раздел 4.6 дизайна).

Ключ ответа складывается из всего, от чего он зависит: пространство и версия, состояние и его источник (дайджест
каталога или коммит), `revision` манифестов, день, набор данных, вводные и `include`. Одинаковый ключ значит
одинаковый ответ, поэтому ETag это хэш ключа, а не ответа: по `If-None-Match` ответ не считается вовсе.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

ETAG_LENGTH = 24


def request_key(parts: Mapping[str, Any]) -> str:
    """Канонический вид ключа: порядок ключей и вводных значения не имеет."""
    return json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=sorted)


def etag_of(key: str) -> str:
    """Сильный ETag в кавычках по ключу ответа."""
    return f'"{hashlib.sha256(key.encode("utf-8")).hexdigest()[:ETAG_LENGTH]}"'


def etag_matches(header: str | None, etag: str) -> bool:
    """`If-None-Match`: список ETag или `*`; слабая форма `W/` для сравнения равна сильной (RFC 9110, 13.1.2)."""
    if not header:
        return False
    bare = etag.removeprefix("W/")
    for candidate in header.split(","):
        item = candidate.strip()
        if item == "*" or item.removeprefix("W/") == bare:
            return True
    return False


class LruCache[V]:
    """Кэш с вытеснением давно не читанных записей: не больше `max_entries` записей и `max_cost` суммарной цены
    (размер в байтах, если он известен). Запись дороже предела не кладётся: она всё равно вытеснила бы всё."""

    def __init__(self, max_entries: int, *, max_cost: int | None = None) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._max_cost = max_cost
        self._items: OrderedDict[str, tuple[V, int]] = OrderedDict()
        self._cost = 0

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: object) -> bool:
        return key in self._items

    @property
    def cost(self) -> int:
        return self._cost

    def get(self, key: str) -> V | None:
        found = self._items.get(key)
        if found is None:
            return None
        self._items.move_to_end(key)
        return found[0]

    def put(self, key: str, value: V, cost: int = 0) -> None:
        if self._max_cost is not None and cost > self._max_cost:
            return
        previous = self._items.pop(key, None)
        if previous is not None:
            self._cost -= previous[1]
        self._items[key] = (value, cost)
        self._cost += cost
        while len(self._items) > self._max_entries or (self._max_cost is not None and self._cost > self._max_cost):
            _, (_, dropped) = self._items.popitem(last=False)
            self._cost -= dropped

    def clear(self) -> None:
        self._items.clear()
        self._cost = 0
