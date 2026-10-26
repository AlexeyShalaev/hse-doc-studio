"""Выбор человека по конфликту: словарь `путь → решение`, как в теле запроса resolve.

Слова совпадают с контрактом (contracts/git-sync): `mine` всегда «моя» сторона слияния,
`theirs` — пришедшая из удалённого репозитория.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class HunkChoice(StrEnum):
    """Что взять в конфликтном участке текста."""

    mine = "mine"
    theirs = "theirs"
    both = "both"  # сначала моё, потом чужое
    both_reverse = "both_reverse"  # сначала чужое, потом моё
    base = "base"  # как было до обеих правок
    custom = "custom"  # текст, набранный вручную


class FieldChoice(StrEnum):
    """Что взять в конфликтном поле структурированного файла."""

    mine = "mine"
    theirs = "theirs"
    union = "union"  # только для списков: мои элементы, затем чужие, которых у меня нет


class FileChoice(StrEnum):
    """Решение по файлу целиком."""

    mine = "mine"
    theirs = "theirs"
    newest = "newest"  # только для бинарных файлов: новее побеждает, проигравший рядом копией


@dataclass(frozen=True)
class HunkDecision:
    choice: HunkChoice
    # Нужен только для custom.
    text: str | None = None


@dataclass(frozen=True)
class FieldDecision:
    choice: FieldChoice


@dataclass(frozen=True)
class FileChoiceResolution:
    choice: FileChoice


@dataclass(frozen=True)
class HunksResolution:
    # Ключ участка (TextHunk.key), а не номер: решения переживают пересчёт плана.
    hunks: Mapping[str, HunkDecision]


@dataclass(frozen=True)
class FieldsResolution:
    # JSON-указатель поля.
    fields: Mapping[str, FieldDecision]


@dataclass(frozen=True)
class TextResolution:
    """Весь текст файла целиком, набранный вручную."""

    content: str


FileResolution = FileChoiceResolution | HunksResolution | FieldsResolution | TextResolution
