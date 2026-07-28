from __future__ import annotations

import json
import os
from pathlib import Path

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_project,
    serialize_project,
)

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"


class JsonProjectRepository:
    """Reads/writes Project to <folder>/.hse-studio/project.json."""

    def get(self, folder: Path) -> Project | None:
        path = folder / _HSE_STUDIO / "project.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return deserialize_project(data, folder=folder)
        except Exception as exc:
            logger.warning("project.json read error", folder=str(folder), exc=str(exc))
            return None

    def save(self, project: Project) -> None:
        studio_dir = project.folder / _HSE_STUDIO
        studio_dir.mkdir(parents=True, exist_ok=True)
        path = studio_dir / "project.json"
        data = serialize_project(project)
        # Атомарная запись: temp + os.replace. project.json — единственный
        # источник правды проекта; жёсткое убийство процесса посреди
        # write_text оставляло файл из мусора (наблюдалось вживую) и проект
        # переставал открываться.
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
        logger.debug("project saved", folder=str(project.folder))
