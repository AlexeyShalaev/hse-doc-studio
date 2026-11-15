"""Пак и шаблон с нуля (docs/design/template-studio.md, раздел 8; срез T15): сущности и проверка id.

- «Новый пак»: id, имена ru и en, сопровождающий, лицензия, адрес исходников и первый шаблон.
- «Новый шаблон» в существующем паке: id и имена.
- Заготовка: «Минимальный» (один документ «Отчёт» по ГОСТ 7.32, два поля анкеты, слот автора, одна точка сдачи) или
  «Копия» выбранной версии существующего шаблона из этого пространства или из каталога этой Студии. Копия получает
  новые id, `releases.yaml` пуст, версия `beta` с номером `<год>.1`, атрибуция источника в комментарии манифеста.

Id пака и шаблона это имя папки и ключ в манифесте: строчная латиница и цифры, пак через `-`, шаблон через `-` или
`_` (схема `common.schema.json#/$defs/id` строже не бывает, а строчные буквы не дают двух папок, которые на macOS и
Windows одна).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.template_versions import parse_version_key

ID_MAX = 64
PACK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TEMPLATE_ID_RE = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
DEFAULT_LICENSE = "Apache-2.0"
TEXT_MAX = 500
Localized = Mapping[str, str]


class ScaffoldKind(StrEnum):
    minimal = "minimal"
    copy = "copy"


class SourceOrigin(StrEnum):
    # Пак этого рабочего пространства (папки паков).
    workspace = "workspace"
    # Пак каталога этой Студии: вшитый в образ или подключённый (10.3).
    catalog = "catalog"


@dataclass(frozen=True)
class ScaffoldSource:
    """Версия шаблона, которую копирует заготовка «Копия»."""

    origin: SourceOrigin
    pack: str
    template: str
    version: str


@dataclass(frozen=True)
class Scaffold:
    kind: ScaffoldKind = ScaffoldKind.minimal
    source: ScaffoldSource | None = None


@dataclass(frozen=True)
class Maintainer:
    name: str
    email: str = ""
    url: str = ""


@dataclass(frozen=True)
class NewTemplate:
    id: str
    name: Localized
    short_name: Localized | None = None
    description: Localized | None = None


@dataclass(frozen=True)
class NewPack:
    id: str
    name: Localized
    template: NewTemplate
    description: Localized | None = None
    maintainer: Maintainer | None = None
    license: str = DEFAULT_LICENSE
    source: str | None = None


@dataclass(frozen=True)
class SourceMeta:
    """Что известно об источнике копии: для атрибуции и полей шаблона, которые не зависят от версии."""

    pack: str
    template: str
    version: str
    pack_name: Localized = field(default_factory=dict)
    license: str = ""
    maintainer: str = ""
    # Поля `template.yaml` источника, которые копия берёт себе: иконка, оттенок, подсказка группы.
    template_fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CopySource:
    origin: SourceOrigin
    version_dir: Path
    meta: SourceMeta
    # Примеры данных предпросмотра шаблона-источника (`templates/<шаблон>/examples`), если есть.
    examples_dir: Path | None = None


@dataclass(frozen=True)
class SourceVersion:
    version: str
    status: str | None
    # Выпущена: внесена в реестр выпусков (у каталога Студии все версии выпущены).
    released: bool
    default: bool = False


@dataclass(frozen=True)
class SourceTemplate:
    template: str
    name: Localized
    versions: tuple[SourceVersion, ...]
    default_version: str | None = None


@dataclass(frozen=True)
class SourcePack:
    origin: SourceOrigin
    pack: str
    name: Localized
    license: str
    templates: tuple[SourceTemplate, ...]


@dataclass(frozen=True)
class ScaffoldOptions:
    """Что нужно окну «Новый пак» и «Новый шаблон»: источники копии, занятые id, значения по умолчанию."""

    sources: tuple[SourcePack, ...]
    # Занятые id паков (свёрнутый регистр): папки пространства и паки каталога Студии.
    taken_packs: tuple[str, ...]
    maintainer: Maintainer | None
    license: str
    version: str


@dataclass(frozen=True)
class ScaffoldResult:
    ref: VersionRef
    # Созданные манифесты от папки паков: пак (если создан), шаблон, версия.
    manifests: tuple[str, ...]
    # Исходник первого документа версии: его открывает интерфейс; None, если документа нет.
    main_file: str | None
    files: int
    source: ScaffoldSource | None = None
    pack_created: bool = False


def default_version(today: date) -> str:
    """Номер первой версии: `<год>.1` (7.1: major это год набора)."""
    return f"{today.year}.1"


def check_pack_id(raw: str) -> str:
    return _check_id(raw, PACK_ID_RE, "pack")


def check_template_id(raw: str) -> str:
    return _check_id(raw, TEMPLATE_ID_RE, "template")


def check_version_number(raw: str) -> str:
    value = raw.strip()
    if parse_version_key(value) is None or "/" in value or value.startswith("."):
        raise PackStudioError(PackStudioErrorCode.version_number_invalid, version=value, reason="format")
    return value


def _check_id(raw: str, pattern: re.Pattern[str], field_name: str) -> str:
    value = raw.strip()
    if not value or len(value) > ID_MAX or not pattern.fullmatch(value):
        raise PackStudioError(PackStudioErrorCode.id_invalid, field=field_name, value=value[:ID_MAX])
    return value


def clean_localized(raw: Localized | None, *, required: bool, field_name: str) -> dict[str, str] | None:
    """Пара ru и en без пробелов по краям; пустой перевод берёт текст другого языка, обязательная пара не пуста."""
    values = {lang: (raw or {}).get(lang, "").strip()[:TEXT_MAX] for lang in ("ru", "en")}
    if not any(values.values()):
        if required:
            raise PackStudioError(PackStudioErrorCode.name_required, field=field_name)
        return None
    ru = values["ru"] or values["en"]
    return {"ru": ru, "en": values["en"] or ru}
