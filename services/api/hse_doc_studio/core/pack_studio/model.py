"""Модель версии шаблона для форм Студии шаблонов (docs/design/template-studio.md, 5.0 и 5.2–5.3, срезы T11 и T12).

Форма правит структуру пака мышкой, а пишет то же, что автор написал бы руками: точечные правки YAML (D11) в
`version.yaml` и `doc.yaml` документов, с сохранением комментариев и порядка. Модель (`VersionModel`) это разобранные
манифесты как есть (данные `yaml.safe_load` в виде JSON) с ETag каждого файла, файлы документов по языкам (грамматика
суффиксов `<stem>.<код>.<ext>`) и «где печатается» каждое поле по исходникам версии (`core/meta_usage.py`).

Правка формы проходит тот же путь, что ручная: запись под замком пространства с `If-Match`, защита выпущенной
версии, затем «Проблемы» (`pack_lint`), живой класс версии (T10) и предпросмотр. Сверх того форма не даёт записать
то, что лоадер или схема пака отвергнут: правка, после которой у файла появилась новая находка схемы или лоадера,
не пишется (`model_invalid`). Старые находки не мешают: пак, сломанный руками, форма всё равно правит.

Операции на несколько файлов (`ModelAction`) считает адаптер порта: переименование поля во всех шаблонах версии,
новый документ (пустой или копия заготовки), удаление документа с его папкой, перевод файлов документа.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# Правок формы за один запрос: столько автор не делает и за час.
MAX_MODEL_OPS = 50
# Как в схеме пака (`contracts/pack/common.schema.json`): id документа (`id`, двойной `-` занят инстансами команды),
# ключ поля (`metaKey`, печатается как `project.meta.<ключ>`), код языка (`langCode`).
DOC_ID = re.compile(r"^[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)*$")
FIELD_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LANG_CODE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$")
MAX_ID_CHARS = 64


def valid_doc_id(value: str) -> bool:
    return len(value) <= MAX_ID_CHARS and bool(DOC_ID.match(value))


def valid_field_key(value: str) -> bool:
    return len(value) <= MAX_ID_CHARS and bool(FIELD_KEY.match(value))


class ModelEditError(ValueError):
    """Правку формы нельзя записать: причина по-английски (уходит полем `reason` ответа `model_invalid`)."""


@dataclass(frozen=True)
class ModelFile:
    """Манифест версии или документа: путь от папки паков, ETag содержимого и данные как их читает `safe_load`."""

    path: str
    etag: str
    data: Any


@dataclass(frozen=True)
class DocFile:
    """Файл папки документа: путь от `files/` версии, путь без языкового суффикса и код языка ("" у файла без кода)."""

    path: str
    bare: str
    lang: str
    size: int


@dataclass(frozen=True)
class DocumentModel:
    """Документ ростера: манифест `files/<id>/doc.yaml` (None у записи v1 прямо в ростере) и файлы его папки."""

    id: str
    manifest: ModelFile | None
    # Запись документа: данные `doc.yaml` или (v1) словарь ростера.
    data: Any
    files: tuple[DocFile, ...]
    # Где манифест версии упоминает документ (слоты, места, профили сдачи): пути YAML строкой.
    references: tuple[str, ...]


@dataclass(frozen=True)
class FieldUsage:
    """Поле печатается в документе: макросами `\\hse...` динамических инклудов или прямо из исходника (Jinja)."""

    field: str
    document: str
    macros: tuple[str, ...]
    # Исходник документа ссылается на поле сам (Jinja при создании проекта).
    direct: bool
    # Строка инклуда вне макросов: поле действует на весь документ (шрифты).
    whole: bool


@dataclass(frozen=True)
class VersionModel:
    manifest: ModelFile
    documents: tuple[DocumentModel, ...]
    usage: tuple[FieldUsage, ...]
    # Файлы проверок версии (`checks/<имя>.yaml`) по имени без расширения: для `gost_ref` документа.
    checks: tuple[str, ...]
    # Находки лоадера и схемы по манифестам версии сейчас (форма подсвечивает их у сущности).
    problems: tuple[str, ...]


@dataclass(frozen=True)
class LibraryDocument:
    """Заготовка документа из пака рабочего пространства: последняя версия каждого шаблона."""

    path: str
    pack: str
    template: str
    version: str
    id: str
    name: dict[str, str]


class ModelActionKind(StrEnum):
    # Новый ключ поля в `meta_fields` и во всех шаблонах версии (`project.meta.<ключ>`, `author.meta.<ключ>`).
    rename_field = "rename_field"
    # Документ в ростер: пустой (`doc.yaml` и главный `.tex`) или копия папки заготовки (`source`).
    add_document = "add_document"
    # Документ из ростера вместе с папкой `files/<id>/`.
    remove_document = "remove_document"
    # Перевод файлов документа на язык версии: копия редакции языка по умолчанию в `<stem>.<код>.<ext>`.
    add_translation = "add_translation"


@dataclass(frozen=True)
class ModelAction:
    kind: ModelActionKind
    field: str | None = None
    to: str | None = None
    document: str | None = None
    name: dict[str, str] | None = None
    # add_document: папка документа-заготовки от папки паков (`<пак>/templates/<шаблон>/versions/<в>/files/<id>`).
    source: str | None = None
    lang: str | None = None
    # add_translation: пути без суффикса от `files/` (пусто: все файлы документа с редакцией языка по умолчанию).
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileChange:
    """Запись (`content`) или удаление (None: файл или папка) по пути от папки паков."""

    path: str
    content: bytes | None
