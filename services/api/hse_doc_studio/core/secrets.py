"""Привязка шифртекста к записи и реестр шифруемых колонок.

Каждая таблица с секретом (токены git, OIDC, SMTP, ключи ИИ и подписи) регистрирует свои колонки здесь:
по реестру `secrets reencrypt` находит всё, что надо перевести на новый ключ.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


def column_aad(table: str, column: str, row_id: object) -> str:
    """Что привязывает шифртекст к ячейке: перенос в другую запись, колонку или таблицу не расшифруется."""
    return f"{table}/{column}/{row_id}"


@dataclass(frozen=True)
class EncryptedColumn:
    table: str
    column: str
    pk: str = "id"
    # Привязка записей, сделанных до column_aad (например, перенесённых из локального режима).
    legacy_aad: Callable[[str], str] | None = None

    @property
    def label(self) -> str:
        return f"{self.table}.{self.column}"

    def aad(self, row_id: object) -> str:
        return column_aad(self.table, self.column, row_id)


class EncryptedColumnRegistry:
    def __init__(self) -> None:
        self._columns: dict[str, EncryptedColumn] = {}

    def register(self, column: EncryptedColumn) -> None:
        existing = self._columns.get(column.label)
        if existing is not None and existing != column:
            msg = f"колонка {column.label} уже зарегистрирована с другими параметрами"
            raise ValueError(msg)
        self._columns[column.label] = column

    def all(self) -> list[EncryptedColumn]:
        return sorted(self._columns.values(), key=lambda column: column.label)


encrypted_columns = EncryptedColumnRegistry()
