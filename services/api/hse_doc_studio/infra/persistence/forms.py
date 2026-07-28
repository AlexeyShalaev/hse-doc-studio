from __future__ import annotations

import json
from pathlib import Path

import structlog

from hse_doc_studio.core.value_objects import FormState
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_form_state,
    migrate_legacy_ai_usage,
    serialize_form_state,
)

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"
_FORMS_DIR = "forms"
# Pre-engine single-form file. Only the AI-declaration form migrates from it.
_LEGACY_AI_USAGE_FILE = "ai-usage.json"
_AI_DECLARATION_FORM_ID = "ai_declaration"


class JsonFormStateRepository:
    """Reads/writes FormState to <folder>/.hse-studio/forms/<form_id>.json.

    Form-agnostic: it round-trips the answers blob and knows nothing about which
    fields a form declares. The only special case is a one-time migration of the
    legacy `ai-usage.json` into the `ai_declaration` form on first read.
    """

    def get_state(self, project_folder: Path, form_id: str) -> FormState | None:
        path = project_folder / _HSE_STUDIO / _FORMS_DIR / f"{form_id}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return deserialize_form_state(data)
            except Exception as exc:
                logger.warning("form state read error", folder=str(project_folder), form_id=form_id, exc=str(exc))
                return None

        if form_id == _AI_DECLARATION_FORM_ID:
            legacy = project_folder / _HSE_STUDIO / _LEGACY_AI_USAGE_FILE
            if legacy.exists():
                try:
                    data = json.loads(legacy.read_text(encoding="utf-8"))
                    logger.info("migrating legacy ai-usage.json", folder=str(project_folder))
                    return migrate_legacy_ai_usage(data)
                except Exception as exc:
                    logger.warning("legacy ai-usage.json migrate error", folder=str(project_folder), exc=str(exc))
        return None

    def save_state(self, project_folder: Path, form_id: str, state: FormState) -> None:
        forms_dir = project_folder / _HSE_STUDIO / _FORMS_DIR
        forms_dir.mkdir(parents=True, exist_ok=True)
        path = forms_dir / f"{form_id}.json"
        data = serialize_form_state(state)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("form state saved", folder=str(project_folder), form_id=form_id)
