"""Списки на сервере: поиск, сортировка, окно страницы и выбор из пикера. Чистые значения без HTTP и SQL.

Каждый ресурс сам перечисляет поля, по которым разрешено сортировать; хранилище добавляет к любой сортировке
вторичный ключ id, чтобы порядок строк между страницами не плавал.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
PICKER_LIMIT = 20
SEARCH_MAX = 200


@dataclass(frozen=True)
class SortKey:
    """Одно поле сортировки: `name` по возрастанию, `-name` по убыванию."""

    field: str
    descending: bool = False

    @classmethod
    def parse(cls, raw: str) -> SortKey:
        return cls(raw[1:], True) if raw.startswith("-") else cls(raw)

    def __str__(self) -> str:
        return f"-{self.field}" if self.descending else self.field


@dataclass(frozen=True)
class Window:
    """Окно страницы: сколько строк и с какой по счёту."""

    limit: int = DEFAULT_LIMIT
    offset: int = 0


@dataclass(frozen=True)
class Found[T]:
    """Страница строк и общее число строк под тем же фильтром."""

    items: list[T]
    total: int


@dataclass(frozen=True)
class PickerItem:
    """Строка пикера без HTTP: вид сущности, id, подпись и вторая строка подписи."""

    kind: str
    id: str
    name: str
    detail: str | None = None


@dataclass(frozen=True)
class Picked[T]:
    """Ответ пикера: первые подходящие и признак, что есть ещё (тогда поиск надо уточнить)."""

    items: list[T]
    has_more: bool

    @classmethod
    def of(cls, rows: list[T], limit: int) -> Picked[T]:
        """Хранилище читает на одну строку больше `limit`: лишняя только говорит, что дальше есть ещё."""
        return cls(rows[:limit], len(rows) > limit)


def clamp_limit(limit: int, maximum: int = MAX_LIMIT) -> int:
    """Размер окна в пределах 1..`maximum`: вызов use case в обход HTTP не прочтёт таблицу целиком."""
    return max(1, min(limit, maximum))


def search_text(q: str | None) -> str | None:
    """Строка поиска без пробелов по краям; пустая значит «без поиска»."""
    if q is None:
        return None
    stripped = q.strip()
    return stripped or None


def like_escaped(q: str) -> str:
    """Подстрока для LIKE/ILIKE: `%`, `_` и `\\` ищутся как обычные символы (ESCAPE '\\')."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
