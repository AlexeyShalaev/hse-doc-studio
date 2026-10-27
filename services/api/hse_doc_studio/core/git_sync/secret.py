"""Секрет в памяти процесса: токен или закрытый ключ.

Обычная строка с секретом легко утекает: в repr, в f-строку, в лог, в тело ошибки, в pickle.
`Secret` не позволяет ничего из этого случайно: текст виден только через `reveal()`, а копирование
и сериализация запрещены, поэтому секрет не попадёт ни в задачу диспетчера (кодек задач бросит
TypeError на неизвестном типе), ни на диск мимо шифра.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn


class Secret:
    """Обёртка над секретной строкой: маска в repr и str, сравнение за постоянное время, не копируется."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(***)"

    __str__ = __repr__

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Secret):
            return NotImplemented
        return hmac.compare_digest(self._value.encode(), other._value.encode())

    def __hash__(self) -> NoReturn:
        raise TypeError("Secret is unhashable")

    def __reduce__(self) -> NoReturn:
        raise TypeError("Secret cannot be pickled or copied")

    def __getstate__(self) -> NoReturn:
        raise TypeError("Secret cannot be pickled or copied")


class KeySource(StrEnum):
    """Откуда берётся ключ шифрования секретов."""

    file = "file"
    env = "env"


@dataclass(frozen=True)
class CipherStatus:
    source: KeySource
    # Ключом можно пользоваться: он прочитан либо файла ещё нет и он создастся при первой записи.
    # False: файл ключей повреждён или ключ из окружения задан неверно.
    available: bool
    # Права 0600 на файл ключей и 0700 на каталог действуют (на смонтированных томах Windows и
    # сетевых дисках chmod ничего не меняет).
    permissions_enforced: bool
