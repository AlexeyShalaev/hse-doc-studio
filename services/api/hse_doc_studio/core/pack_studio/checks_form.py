"""Проверки и правила версии шаблона формой в Студии шаблонов (docs/design/template-studio.md, 5.7, срез T14).

Автор пака правит файлы `checks/*.yaml` версии (шапка `label`, `ref`, `source` и правила списком) и
`checks_version` в `version.yaml` (выключенные категории и правила, переопределение важности). Студия пишет это
точечными правками YAML (D11): меняется только фрагмент записи, комментарии и незнакомые форме ключи остаются.

Модель правил та же, что у лоадера (`_parse_check_rule`), с индексами записей в списке YAML: битое правило видно с
причиной, индексы остальных не сдвигаются. Параметры правила (`params`) форма правит как словарь: для известных
структурных проверок полями, для прочих движков текстом YAML.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from hse_doc_studio.core.pack_studio.submission import Indexed

# Набор правок за один запрос.
MAX_CHECKS_OPS = 50
# Важность правила в паке и в `severity_override` (`skipped` только переопределением).
RULE_SEVERITIES: tuple[str, ...] = ("info", "warn", "err")
OVERRIDE_SEVERITIES: tuple[str, ...] = ("info", "warn", "err", "skipped")
# Структурные проверки движка `structural` (`params.check`), у которых в форме свои поля.
STRUCTURAL_CHECKS: tuple[str, ...] = (
    "page_geometry",
    "line_spacing",
    "font_size",
    "paragraph_indent",
    "page_count",
    "figure_numbering",
    "float_orphans",
)


class ChecksEditError(ValueError):
    """Правку нельзя применить: правила нет, значение не читается лоадером, шапка без названия."""


class ChecksOpKind(StrEnum):
    # Шапка файла: `label`, `ref` ru и en, `source` (текст ru и en, `url`).
    set_header = "set_header"
    # Правило в конец списка, по индексу, убрать, переставить на `to`.
    add_rule = "add_rule"
    set_rule = "set_rule"
    remove_rule = "remove_rule"
    move_rule = "move_rule"


@dataclass(frozen=True)
class ChecksHeader:
    label: Mapping[str, str]
    ref: Mapping[str, str]
    # Текст источника по языкам (без `url`).
    source: Mapping[str, str]
    url: str | None = None


@dataclass(frozen=True)
class RuleEntry:
    """Правило проверки: `applies_to` None значит «все документы» (`*`)."""

    id: str
    title: Mapping[str, str]
    description: Mapping[str, str]
    category: str | None
    applies_to: tuple[str, ...] | None
    default_severity: str
    engine: str
    params: Mapping[str, Any]


@dataclass(frozen=True)
class ChecksOp:
    op: ChecksOpKind
    header: ChecksHeader | None = None
    index: int | None = None
    to: int | None = None
    rule: RuleEntry | None = None


@dataclass(frozen=True)
class ChecksFileView:
    """Файл правил: шапка, префикс id правил (имя файла), правила по индексам и первая проблема разбора."""

    header: ChecksHeader
    prefix: str
    rules: tuple[Indexed[RuleEntry], ...]
    error: str | None = None


@dataclass(frozen=True)
class ChecksConfig:
    """`checks_version` версии: выключенные категории и правила, переопределение важности."""

    disabled_categories: tuple[str, ...] = ()
    disabled: tuple[str, ...] = ()
    severity_override: Mapping[str, str] | None = None
