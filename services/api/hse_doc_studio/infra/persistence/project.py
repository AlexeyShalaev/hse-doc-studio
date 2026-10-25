from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio import __version__
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import ProjectReadOnlyError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.project_schema import can_write, schema_to_write
from hse_doc_studio.core.value_objects import ProjectSchema
from hse_doc_studio.infra.persistence.project_migrations import migrate_project_state, needs_migration
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_project,
    deserialize_project_schema,
    serialize_project,
)
from hse_doc_studio.infra.persistence.unknown_fields import PROJECT_SHAPE, preserve_unknown

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"
_PROJECT_FILE = "project.json"


def read_json_or_none(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def stored_project_schema(folder: Path) -> ProjectSchema | None:
    """Схема `project.json` на диске; None — файла нет или он нечитаем."""
    data = read_json_or_none(folder / _HSE_STUDIO / _PROJECT_FILE)
    if not isinstance(data, dict):
        return None
    return deserialize_project_schema(data.get("schema"))


def assert_project_writable(folder: Path, schema: ProjectSchema | None = None) -> None:
    """Запрет записи в данные проекта, которые разрешено писать только более новой Студии.

    Последний рубеж после HTTP-гарда (api.guards): даже если запрос дошёл до
    репозитория, `.hse-studio` в формате, который эта Студия писать не умеет,
    не перезаписывается — иначе мы бы молча испортили данные.
    """
    current = schema if schema is not None else stored_project_schema(folder)
    if can_write(current):
        return
    written_by = current.written_by if current is not None and current.written_by else "?"
    raise ProjectReadOnlyError(
        localized_error(
            f"Проект записан более новой версией Студии ({written_by}): здесь он открыт только для чтения.",
            f"The project was saved by a newer Studio ({written_by}): it is read-only here.",
        )
    )


class JsonProjectRepository:
    """Reads/writes Project to <folder>/.hse-studio/project.json.

    Чтение доводит данные до текущей схемы (infra.persistence.project_migrations);
    запись сохраняет неизвестные этой Студии поля (unknown_fields) и не трогает
    файл, который разрешено писать только более новой Студии.
    """

    def __init__(self, app_version: str = __version__) -> None:
        self._app_version = app_version

    def get(self, folder: Path) -> Project | None:
        path = folder / _HSE_STUDIO / _PROJECT_FILE
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if needs_migration(data):
                data = migrate_project_state(folder, data, app_version=self._app_version)
            return deserialize_project(data, folder=folder)
        except Exception as exc:
            logger.warning("project.json read error", folder=str(folder), exc=str(exc))
            return None

    def save(self, project: Project) -> None:
        studio_dir = project.folder / _HSE_STUDIO
        studio_dir.mkdir(parents=True, exist_ok=True)
        path = studio_dir / _PROJECT_FILE
        old = read_json_or_none(path) if path.exists() else None
        stored = deserialize_project_schema(old.get("schema")) if isinstance(old, dict) else None
        assert_project_writable(project.folder, stored)
        data = serialize_project(replace(project, schema=schema_to_write(stored, self._app_version)))
        data = preserve_unknown(data, old, PROJECT_SHAPE)
        # Атомарная запись: temp + os.replace. project.json — единственный
        # источник правды проекта; жёсткое убийство процесса посреди
        # write_text оставляло файл из мусора (наблюдалось вживую) и проект
        # переставал открываться.
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
        logger.debug("project saved", folder=str(project.folder))
