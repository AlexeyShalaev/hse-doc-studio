"""Миграции данных проекта вперёд: схема N → N+1 (см. core.project_schema).

Шаг — чистая функция над словарями json-файлов `.hse-studio` (`project.json`,
`signatures.json`, `forms/<id>.json`, …): миграция часто трогает несколько файлов
сразу, поэтому номер схемы один на весь набор. Применяется при чтении проекта,
до десериализации; результат сразу записывается на диск, а исходные файлы
кладутся в `.hse-studio/backup/schema-<N>/` (каталог вне истории версий).

Шаги идемпотентны по номеру: снимок из истории со старой схемой после restore
просто мигрирует снова при следующем открытии. Обратных миграций нет: вместо них
`read_compat` / `write_compat` и снимки до миграции.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.project_schema import (
    PROJECT_SCHEMA_READ_COMPAT,
    PROJECT_SCHEMA_VERSION,
    PROJECT_SCHEMA_WRITE_COMPAT,
)
from hse_doc_studio.infra.persistence.serializers import deserialize_project_schema

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"
PROJECT_FILE = "project.json"
BACKUP_DIR = "backup"


class ProjectStateBundle:
    """json-файлы `.hse-studio` одного проекта, загружаемые по требованию.

    Шаг миграции читает и меняет файлы через `get`/`set`; записываются только
    изменённые (`dirty`). Пути — относительно `.hse-studio` (`signatures.json`).
    """

    def __init__(self, studio_dir: Path, project: dict[str, Any]) -> None:
        self._dir = studio_dir
        self._data: dict[str, Any] = {PROJECT_FILE: project}
        self.dirty: set[str] = {PROJECT_FILE}

    @property
    def project(self) -> dict[str, Any]:
        project: dict[str, Any] = self._data[PROJECT_FILE]
        return project

    def get(self, rel_path: str) -> Any:
        if rel_path not in self._data:
            path = self._dir / rel_path
            self._data[rel_path] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return self._data[rel_path]

    def set(self, rel_path: str, data: Any) -> None:
        self._data[rel_path] = data
        self.dirty.add(rel_path)

    def list_dir(self, rel_dir: str) -> list[str]:
        """Относительные пути json-файлов в подкаталоге (`forms`)."""
        directory = self._dir / rel_dir
        if not directory.is_dir():
            return []
        return sorted(f"{rel_dir}/{p.name}" for p in directory.glob("*.json"))

    def items(self) -> list[tuple[str, Any]]:
        return [(rel, self._data[rel]) for rel in sorted(self.dirty)]


MigrationStep = Callable[[ProjectStateBundle], None]

# Ключ — схема, ИЗ которой шаг переводит данные (в схему ключ + 1). Пусто, пока
# схема одна. Новый шаг сопровождается подъёмом PROJECT_SCHEMA_VERSION.
MIGRATIONS: dict[int, MigrationStep] = {}


def needs_migration(project_data: dict[str, Any], target_version: int = PROJECT_SCHEMA_VERSION) -> bool:
    return deserialize_project_schema(project_data.get("schema")).version < target_version


def migrate_project_state(
    folder: Path,
    project_data: dict[str, Any],
    *,
    steps: Mapping[int, MigrationStep] | None = None,
    target_version: int = PROJECT_SCHEMA_VERSION,
    read_compat: int = PROJECT_SCHEMA_READ_COMPAT,
    write_compat: int = PROJECT_SCHEMA_WRITE_COMPAT,
    app_version: str = "",
) -> dict[str, Any]:
    """Довести данные проекта до `target_version` и записать результат.

    Возвращает мигрированный `project.json`. Если записать не удалось (папка
    только для чтения), данные всё равно мигрированы в памяти — проект откроется,
    а запись повторится при следующем чтении.
    """
    registry = MIGRATIONS if steps is None else steps
    stored = deserialize_project_schema(project_data.get("schema"))
    if stored.version >= target_version:
        return project_data

    studio_dir = folder / _HSE_STUDIO
    bundle = ProjectStateBundle(studio_dir, json.loads(json.dumps(project_data)))
    for version in range(stored.version, target_version):
        step = registry.get(version)
        if step is not None:
            step(bundle)
    bundle.project["schema"] = {
        "version": target_version,
        "read_compat": max(read_compat, stored.read_compat),
        "write_compat": max(write_compat, stored.write_compat),
        "written_by": app_version,
    }
    try:
        _backup(studio_dir, bundle, stored.version)
        _write(studio_dir, bundle)
    except OSError as exc:
        logger.warning("project migration not persisted", folder=str(folder), exc=str(exc))
    else:
        logger.info("project data migrated", folder=str(folder), from_schema=stored.version, to_schema=target_version)
    return bundle.project


def _backup(studio_dir: Path, bundle: ProjectStateBundle, from_version: int) -> None:
    backup_dir = studio_dir / BACKUP_DIR / f"schema-{from_version}"
    for rel in sorted(bundle.dirty):
        source = studio_dir / rel
        if source.exists():
            target = backup_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _write(studio_dir: Path, bundle: ProjectStateBundle) -> None:
    for rel, data in bundle.items():
        path = studio_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
