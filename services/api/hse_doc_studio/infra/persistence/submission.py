from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import PackSubmissionRecord
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_pack_submission_record,
    serialize_pack_submission_record,
)

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"


class JsonPackSubmissionRepository:
    """Reads/writes PackSubmissionRecord to <folder>/.hse-studio/submissions/<uuid>.json."""

    def _submissions_dir(self, project_folder: Path) -> Path:
        return project_folder / _HSE_STUDIO / "submissions"

    def list_for_project(self, project_folder: Path) -> list[PackSubmissionRecord]:
        submissions_dir = self._submissions_dir(project_folder)
        if not submissions_dir.exists():
            return []
        records: list[PackSubmissionRecord] = []
        for json_file in submissions_dir.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                records.append(deserialize_pack_submission_record(data, project_folder=project_folder))
            except Exception as exc:
                logger.warning("submission record read error", path=str(json_file), exc=str(exc))
        records.sort(key=lambda r: r.created_at)
        return records

    def get(self, project_folder: Path, submission_id: UUID) -> PackSubmissionRecord | None:
        path = self._submissions_dir(project_folder) / f"{submission_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return deserialize_pack_submission_record(data, project_folder=project_folder)
        except Exception as exc:
            logger.warning("submission record read error", path=str(path), exc=str(exc))
            return None

    def save(self, record: PackSubmissionRecord) -> None:
        submissions_dir = self._submissions_dir(record.project_folder)
        submissions_dir.mkdir(parents=True, exist_ok=True)
        path = submissions_dir / f"{record.id}.json"
        data = serialize_pack_submission_record(record)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("submission record saved", submission_id=str(record.id))
