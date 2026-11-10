"""Входы сборки: что в проекте меняет PDF, а что нет (docs/design/connected-devices.md, часть 3).

Одно определение для всех мест, где решается «сборка устарела»: строка документа в списке, получение облачной
сборки Студией (`skipped_stale`) и всё, что смотрит на поле `fresh`.

Раннер получает папку проекта без служебных папок (`RUNNER_EXCLUDED_DIRS`, их же пропускает манифест сборки), а
перед сборкой сервер выводит подключаемые файлы шаблона (`common/meta.tex` и др.) из `.hse-studio/project.json`.
Поэтому входы сборки это файлы истории проекта вне служебных папок и та часть `project.json`, из которой берутся
данные титула.
Состояние подписей (`signatures.json`, картинки слотов, зафиксированные и подписанные PDF, файлы открепленных
подписей), анкеты, журнал обновлений шаблона и прочие служебные файлы под `.hse-studio/` PDF не меняют: их запись
не делает сборку устаревшей. В `project.json` не входами считаются поля состояния: статус и последняя сборка
документа, время изменения, закрепление, архив, переопределения проверок, настройки истории и блок схемы.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

PROJECT_FILE = ".hse-studio/project.json"

# Папки, которые не уходят раннеру в манифесте сборки, на любой глубине.
RUNNER_EXCLUDED_DIRS = frozenset({".git", ".hse-studio", ".build", "submissions", "node_modules", "__pycache__"})

# Поля project.json, которые сборка не читает: их меняют сами сборки (статус, `last_compile_id`) и интерфейс.
_PROJECT_STATE_KEYS = frozenset({"updated_at", "pinned", "archived", "checks_override", "schema"})
_DOCUMENT_STATE_KEYS = frozenset({"status", "last_compile_id", "checks_override"})
_META_STATE_KEYS = frozenset({"vcs"})


def is_build_input(path: str) -> bool:
    """Путь проекта (POSIX, от корня) влияет на сборку. `project.json` входит, но сравнивается без полей состояния."""
    if path == PROJECT_FILE:
        return True
    return not any(part in RUNNER_EXCLUDED_DIRS for part in path.split("/")[:-1])


def project_build_view(data: Any) -> Any:
    """`project.json` без полей состояния: то, из чего сборка берёт данные."""
    if not isinstance(data, dict):
        return data
    view = {k: v for k, v in data.items() if k not in _PROJECT_STATE_KEYS}
    meta = view.get("meta")
    if isinstance(meta, dict):
        view["meta"] = {k: v for k, v in meta.items() if k not in _META_STATE_KEYS}
    documents = view.get("documents")
    if isinstance(documents, list):
        view["documents"] = [
            {k: v for k, v in doc.items() if k not in _DOCUMENT_STATE_KEYS} if isinstance(doc, dict) else doc
            for doc in documents
        ]
    return view


def _parsed(raw: bytes | None) -> Any:
    if raw is None:
        return None
    try:
        return project_build_view(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, ValueError):
        # Испорченный файл сравнивается как есть: любое изменение байтов считается изменением входа.
        return raw


def same_project_inputs(before: bytes | None, after: bytes | None) -> bool:
    """Два содержимых `project.json` (None: файла нет) дают сборке одни и те же данные."""
    return _parsed(before) == _parsed(after)


def changed_build_inputs(paths: Iterable[str]) -> list[str]:
    """Изменённые пути, которые могут поменять PDF; `project.json` сюда попадает и проверяется отдельно."""
    return [path for path in paths if is_build_input(path)]
