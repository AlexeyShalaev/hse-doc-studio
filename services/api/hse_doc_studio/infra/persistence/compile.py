from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_compile_record,
    serialize_compile_record,
)

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"


class JsonCompileRepository:
    """Reads/writes CompileRecord to <folder>/.hse-studio/compiles/<uuid>.json."""

    def _compiles_dir(self, project_folder: Path) -> Path:
        return project_folder / _HSE_STUDIO / "compiles"

    def get(self, compile_id: UUID) -> CompileRecord | None:
        # compile_id alone is not enough to find the file without a folder;
        # we do a best-effort scan based on infra convention (not used in protocol directly).
        # The primary lookup is by folder+doc_id. This method is here for protocol compliance.
        logger.warning(
            "JsonCompileRepository.get called without folder context; returning None",
            compile_id=str(compile_id),
        )
        return None

    def get_for_project(self, project_folder: Path, compile_id: UUID) -> CompileRecord | None:
        path = self._compiles_dir(project_folder) / f"{compile_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return deserialize_compile_record(data, project_folder=project_folder)
        except Exception as exc:
            logger.warning("compile record read error", path=str(path), exc=str(exc))
            return None

    def list_for_document(self, project_folder: Path, doc_id: str) -> list[CompileRecord]:
        compiles_dir = self._compiles_dir(project_folder)
        if not compiles_dir.exists():
            return []
        records: list[CompileRecord] = []
        for json_file in compiles_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if data.get("doc_id") == doc_id:
                    records.append(deserialize_compile_record(data, project_folder=project_folder))
            except Exception as exc:
                logger.warning("compile record read error", path=str(json_file), exc=str(exc))
        records.sort(key=lambda r: r.started_at)
        return records

    def save(self, record: CompileRecord) -> None:
        compiles_dir = self._compiles_dir(record.project_folder)
        compiles_dir.mkdir(parents=True, exist_ok=True)
        path = compiles_dir / f"{record.id}.json"
        data = serialize_compile_record(record)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("compile record saved", compile_id=str(record.id))
