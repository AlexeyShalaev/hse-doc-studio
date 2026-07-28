"""Версии продукта и адрес фида релизов. Чистые функции — без сети и файлов.

Версии ставит release-please (`vX.Y.Z`), поэтому разбор сознательно снисходителен:
лишняя `v`, суффикс предрелиза, мусор в компоненте — всё сводится к числовому ядру.
Сломанный тег в фиде не должен ни падать, ни выдавать «доступно обновление» на
пустом месте.
"""

from __future__ import annotations

import re

# Значения, выключающие проверку обновлений (офлайн / закрытый контур).
_DISABLED_FEED_VALUES = frozenset({"", "off", "none", "disabled", "-", "0", "false"})

# Ядро semver в конце строки: тег может быть "v0.2.0", "0.2.0", "1.4.0-rc.1".
_TAG_RE = re.compile(r"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\s*$")


def extract_version(tag: str) -> str:
    """Тег релиза → semver-ядро: "v0.2.0" → "0.2.0". Не распознали — вернём как есть."""
    match = _TAG_RE.search(tag or "")
    if match is not None:
        return match.group(1)
    return (tag or "").lstrip("vV")


def parse_version(value: str) -> tuple[int, ...]:
    """Версия → кортеж чисел для сравнения. Суффикс предрелиза отбрасывается."""
    core = (value or "").strip().lstrip("vV").split("-")[0].split("+")[0]
    parts: list[int] = []
    for part in core.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    """Строго новее ли `candidate`, чем `current`."""
    if not candidate or not current:
        return False
    return parse_version(candidate) > parse_version(current)


def feed_disabled(url: str) -> bool:
    """Пустой URL или явный флаг выключения → проверка обновлений отключена."""
    return (url or "").strip().lower() in _DISABLED_FEED_VALUES


def official_feed_url(github_repo: str) -> str:
    """Фид по умолчанию — релизы репозитория продукта (владелец/репо из настроек)."""
    return f"https://api.github.com/repos/{github_repo}/releases"
