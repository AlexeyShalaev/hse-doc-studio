"""Макросы zensical: числа пака hse-cs-se для полосы-доказательства лендинга.

Единственный источник правды — сам пак: version.yaml (документы, профили сдачи)
и checks/*.yaml (правила). Числа на лендинге не пишутся руками — их выдаёт
pack_stats_strip на сборке сайта, поэтому изменение пака автоматически
перегенерирует полосу (CI собирает сайт при изменении packs/**).

Справочник сознательно рассказывает о сущностях (пак, шаблон, документ,
проверка, профиль сдачи), а не о начинке конкретного пака — поэтому таблицы
каталогов здесь больше не генерируются; полоса цифр на главной — реклама.

Правила модуля:
- каждый макрос принимает lang ("ru" | "en") — один модуль обслуживает обе
  языковые сборки;
- вывод — HTML без пустых строк внутри блока: пустая строка разрезала бы
  HTML-остров на отдельные markdown-блоки.
"""

from __future__ import annotations

from functools import cache
from html import escape
from pathlib import Path
from typing import Any

import yaml

PACK_ROOT = Path(__file__).resolve().parent.parent / "packs" / "hse-cs-se" / "templates"
PACK_VERSION = "2026.1"
TEMPLATES = ("vkr", "coursework", "pp")

_L10N = {
    "ru": {
        "docs": "документа",
        "rules": "правила нормоконтроля",
        "engines": "движков проверок",
        "profiles": "профилей сдачи",
        "accounts": "аккаунтов и облаков",
    },
    "en": {
        "docs": "documents",
        "rules": "normcontrol rules",
        "engines": "check engines",
        "profiles": "submission profiles",
        "accounts": "accounts or clouds",
    },
}


@cache
def _load_version(template: str) -> dict[str, Any]:
    path = PACK_ROOT / template / "versions" / PACK_VERSION / "version.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@cache
def _load_checks(template: str) -> list[dict[str, Any]]:
    """Все файлы правил шаблона: [{label, ref, rules: […]}]."""
    out: list[dict[str, Any]] = []
    checks_dir = PACK_ROOT / template / "versions" / PACK_VERSION / "checks"
    for path in sorted(checks_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        out.append({"label": data.get("label"), "ref": data.get("ref"), "rules": data.get("rules") or []})
    return out


def _unique_rules() -> dict[str, dict[str, Any]]:
    """Уникальные правила по id (одно правило может жить в нескольких шаблонах)."""
    merged: dict[str, dict[str, Any]] = {}
    for template in TEMPLATES:
        for group in _load_checks(template):
            for rule in group["rules"]:
                merged.setdefault(rule["id"], {"rule": rule})
    return merged


def define_env(env: Any) -> None:
    env.macro(pack_stats_strip)


def pack_stats_strip(lang: str = "ru") -> str:
    """Полоса доказательства на лендинге: числа считаются из пака."""
    docs_total = sum(len(_load_version(t).get("documents") or []) for t in TEMPLATES)
    rules = _unique_rules()
    engines = {entry["rule"].get("engine") for entry in rules.values()}
    profiles_total = sum(len(_load_version(t)["pack_submission"]["profiles"]) for t in TEMPLATES)
    labels = _L10N[lang]
    cells = [
        (docs_total, labels["docs"]),
        (len(rules), labels["rules"]),
        (len(engines), labels["engines"]),
        (profiles_total, labels["profiles"]),
        (0, labels["accounts"]),
    ]
    items = "".join(f"<div><b>{n}</b><span>{escape(label)}</span></div>" for n, label in cells)
    return f'<div class="hds-stats hds-wide">{items}</div>'
