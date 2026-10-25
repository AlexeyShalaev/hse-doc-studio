"""Версии шаблонов: порядок, класс перехода, совместимость со Студией.

Номер версии шаблона — `YYYY.MINOR.PATCH`:

* `YYYY` — год набора, под регламент которого выпущена версия (2026 = 2026/27).
  Он же major: регламент на набор фиксируется в начале года, и работа студента
  почти никогда не переходит через год;
* `MINOR` — новое без разрушения (документы, разделы, профили, поля; переименования
  и удаления — только с декларацией миграции);
* `PATCH` — исправления без новой поверхности (цвета, опечатки, ложные проверки).

Двухкомпонентный `2026.1` (так выпущены первые версии) читается как `2026.1.0`:
каталоги и lock существующих проектов не переименовываются.

Класс перехода считается по номерам; пак может объявить его строже
(`release.kind`), но не мягче — это проверяет линтер пака.
"""

from __future__ import annotations

import re

from hse_doc_studio.core.enums import TemplateUpdateClass

VersionKey = tuple[int, int, int]

# Формат манифеста версии (`manifest_format` в version.yaml), который понимает
# эта Студия. Новые необязательные ключи формат не меняют (неизвестные ключи
# игнорируются); подъём нужен, когда меняется смысл существующих.
MANIFEST_FORMAT = 1

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")
# Версия Студии: `0.1.3`, `v0.1.3`, `0.2.0-rc.1`, `0.2.0+build` — суффиксы отбрасываются.
_APP_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?$")

_CLASS_ORDER = {
    TemplateUpdateClass.patch: 0,
    TemplateUpdateClass.minor: 1,
    TemplateUpdateClass.major: 2,
}


def parse_version_key(version_id: str) -> VersionKey | None:
    """`2026.1.2` → (2026, 1, 2); `2026.1` → (2026, 1, 0); иное → None."""
    match = _VERSION_RE.match(str(version_id).strip())
    if match is None:
        return None
    year, minor, patch = match.groups()
    return int(year), int(minor), int(patch or 0)


def is_newer(candidate: str, current: str) -> bool:
    """Выше ли `candidate`, чем `current`. Несравнимые номера — не выше."""
    cand_key = parse_version_key(candidate)
    cur_key = parse_version_key(current)
    if cand_key is None or cur_key is None:
        return False
    return cand_key > cur_key


def classify_update(from_version: str, to_version: str) -> TemplateUpdateClass | None:
    """Класс перехода по номерам; None — если `to` не выше `from` или номер не разобран."""
    from_key = parse_version_key(from_version)
    to_key = parse_version_key(to_version)
    if from_key is None or to_key is None or to_key <= from_key:
        return None
    if to_key[0] != from_key[0]:
        return TemplateUpdateClass.major
    if to_key[1] != from_key[1]:
        return TemplateUpdateClass.minor
    return TemplateUpdateClass.patch


def stricter(first: TemplateUpdateClass | None, second: TemplateUpdateClass | None) -> TemplateUpdateClass | None:
    """Более строгий из двух классов (None — «не задан»)."""
    if first is None:
        return second
    if second is None:
        return first
    return first if _CLASS_ORDER[first] >= _CLASS_ORDER[second] else second


def parse_app_version(version: str | None) -> VersionKey | None:
    if not version:
        return None
    match = _APP_VERSION_RE.match(str(version).strip())
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def studio_satisfies(min_studio: str | None, app_version: str | None) -> bool:
    """Подходит ли версия Студии под `min_studio` пака или проекта.

    Неразобранная версия Студии (dev-сборка) считается подходящей: иначе
    разработчик не открыл бы собственные проекты. Неразобранный `min_studio`
    — тоже: это ошибка пака, её ловит линтер, а не пользователь.
    """
    required = parse_app_version(min_studio)
    current = parse_app_version(app_version)
    if required is None or current is None:
        return True
    return current >= required
