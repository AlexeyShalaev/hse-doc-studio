"""Онбординг локальной Студии: человек один, состояние лежит в data_dir/onboarding.json."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.onboarding.entities import OnboardingState, OnboardingStatus
from hse_doc_studio.core.repositories import IProjectIndexRepository

logger = structlog.get_logger()

FILE_NAME = "onboarding.json"


def _dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) and value else None


def state_to_json(state: OnboardingState) -> dict[str, Any]:
    return {
        "status": state.status.value,
        "scenario_version": state.scenario_version,
        "step": state.step,
        "answers": dict(state.answers),
        "started_at": state.started_at.isoformat() if state.started_at else None,
        "finished_at": state.finished_at.isoformat() if state.finished_at else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def state_from_json(raw: dict[str, Any]) -> OnboardingState:
    answers = raw.get("answers")
    return OnboardingState(
        status=OnboardingStatus(raw["status"]),
        scenario_version=int(raw.get("scenario_version") or 0),
        step=raw.get("step") or None,
        answers={str(k): str(v) for k, v in answers.items()} if isinstance(answers, dict) else {},
        started_at=_dt(raw.get("started_at")),
        finished_at=_dt(raw.get("finished_at")),
        updated_at=_dt(raw.get("updated_at")),
    )


class JsonOnboardingRepository:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._path = data_dir / FILE_NAME

    async def get(self) -> OnboardingState | None:
        if not self._path.exists():
            return None
        try:
            return state_from_json(json.loads(self._path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Испорченный файл не должен запирать приложение: считаем, что записи нет.
            logger.warning("onboarding.json read error", path=str(self._path), exc=str(exc))
            return None

    async def save(self, state: OnboardingState) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state_to_json(state), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)


class LocalExistingUserProbe:
    """Локально «давний пользователь» это тот, у кого уже есть проекты в индексе Студии."""

    def __init__(self, project_index: IProjectIndexRepository) -> None:
        self._project_index = project_index

    async def is_existing_user(self) -> bool:
        return bool(self._project_index.list_known())
