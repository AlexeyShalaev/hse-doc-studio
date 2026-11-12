"""Тексты писем: словари ru и en рядом с модулем и подстановка значений.

Подстановка идёт за один проход: значение, попавшее в текст, повторно не разбирается, поэтому `{x}` в имени
проекта остаётся обычными символами. В HTML значения экранируются, а сам текст словаря экранируется как
литерал: разметки в словарях нет.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any

from hse_doc_studio.core.enums import Lang

_LOCALES = Path(__file__).with_name("locales")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")

Catalog = Mapping[str, Any]

# Формы множественного числа: для каждого языка свои ключи словаря `layout.duration`.
PLURAL_FORMS: dict[Lang, tuple[str, ...]] = {Lang.ru: ("one", "few", "many"), Lang.en: ("one", "other")}


@lru_cache(maxsize=len(Lang))
def catalog(lang: Lang) -> Catalog:
    return json.loads((_LOCALES / f"{lang.value}.json").read_text(encoding="utf-8"))


def placeholders(template: str) -> frozenset[str]:
    return frozenset(_PLACEHOLDER.findall(template))


def _literal(parts: list[str], index: int, values: Mapping[str, str]) -> str:
    """Литерал шаблона без точки в начале, если значение перед ним уже кончается точкой: имя с инициалами
    «Петров П. П.» в конце фразы не дает «П. П..»."""
    part = parts[index]
    if index > 0 and part.startswith(".") and values[parts[index - 1]].endswith("."):
        return part[1:]
    return part


def fill_text(template: str, values: Mapping[str, str]) -> str:
    """Простой текст: значения подставляются как есть, точка после значения с точкой на конце не удваивается."""
    parts = _PLACEHOLDER.split(template)
    return "".join(_literal(parts, i, values) if i % 2 == 0 else values[part] for i, part in enumerate(parts))


def fill_html(template: str, values: Mapping[str, str], *, strong: str) -> str:
    """HTML-фрагмент: литерал и значения экранируются, значения оборачиваются в `<strong style=...>`.

    Точка после значения с точкой на конце не удваивается, как в `fill_text`."""
    parts = _PLACEHOLDER.split(template)
    out: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 0:
            out.append(escape(_literal(parts, index, values)))
        else:
            out.append(f'<strong style="{strong}">{escape(values[part])}</strong>')
    return "".join(out)


def plural_form(lang: Lang, n: int) -> str:
    if lang is Lang.en:
        return "one" if n == 1 else "other"
    if n % 10 == 1 and n % 100 != 11:
        return "one"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "few"
    return "many"


def format_duration(lang: Lang, total_seconds: int) -> str:
    """«48 часов», «2 дня», «15 минут»: наибольшая единица, в которой срок делится без остатка."""
    forms = catalog(lang)["layout"]["duration"]
    seconds = max(total_seconds, 60)
    for unit, size in (("day", 86400), ("hour", 3600)):
        if seconds % size == 0:
            amount, key = seconds // size, unit
            break
    else:
        amount, key = max(seconds // 60, 1), "minute"
    return str(forms[key][plural_form(lang, amount)]).replace("{n}", str(amount))
