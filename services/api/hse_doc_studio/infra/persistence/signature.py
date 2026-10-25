from __future__ import annotations

import json
from pathlib import Path

import structlog

from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.infra.persistence.project import assert_project_writable, read_json_or_none
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_signatures_state,
    serialize_signatures_state,
)
from hse_doc_studio.infra.persistence.unknown_fields import SIGNATURES_SHAPE, preserve_unknown

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"


class JsonSignatureRepository:
    """Reads/writes SignaturesState to <folder>/.hse-studio/signatures.json."""

    def get_state(self, project_folder: Path) -> SignaturesState:
        path = project_folder / _HSE_STUDIO / "signatures.json"
        if not path.exists():
            return SignaturesState.empty()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return deserialize_signatures_state(data)
        except Exception as exc:
            logger.warning("signatures.json read error", folder=str(project_folder), exc=str(exc))
            return SignaturesState.empty()

    def save_state(self, project_folder: Path, state: SignaturesState) -> None:
        assert_project_writable(project_folder)
        studio_dir = project_folder / _HSE_STUDIO
        studio_dir.mkdir(parents=True, exist_ok=True)
        path = studio_dir / "signatures.json"
        # Поля, которых эта Студия не знает (их записала более новая), сохраняются.
        data = preserve_unknown(serialize_signatures_state(state), read_json_or_none(path), SIGNATURES_SHAPE)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("signatures state saved", folder=str(project_folder))
