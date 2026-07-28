from __future__ import annotations

import json
from pathlib import Path

import structlog

from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_signatures_state,
    serialize_signatures_state,
)

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
        studio_dir = project_folder / _HSE_STUDIO
        studio_dir.mkdir(parents=True, exist_ok=True)
        path = studio_dir / "signatures.json"
        data = serialize_signatures_state(state)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("signatures state saved", folder=str(project_folder))
