"""Состояние онбординга: значения без HTTP и SQL.

Сценарий тура (шаги, тексты, версия) живёт во фронтенде; сервер хранит только где человек
остановился и что ответил, поэтому шаг и версия здесь непрозрачны.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum


class OnboardingStatus(StrEnum):
    # Новый человек: тур откроется сам при первом входе.
    pending = "pending"
    # Работал до появления онбординга: только ненавязчивое приглашение пройти тур.
    suggested = "suggested"
    in_progress = "in_progress"
    completed = "completed"
    skipped = "skipped"


# Статусы, которые клиент выставляет сам. `suggested` назначает только сервер.
CLIENT_STATUSES = frozenset(
    {OnboardingStatus.pending, OnboardingStatus.in_progress, OnboardingStatus.completed, OnboardingStatus.skipped}
)
FINISHED_STATUSES = frozenset({OnboardingStatus.completed, OnboardingStatus.skipped})

ANSWER_KEYS = frozenset({"role", "work", "latex", "git"})
MAX_STEP_LENGTH = 64
MAX_ANSWER_LENGTH = 96
MAX_SCENARIO_VERSION = 10_000
_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_./-]*$")


class OnboardingInvalidError(ValueError):
    """Тело обновления не прошло правила домена; `field` называет поле."""

    def __init__(self, field_name: str, message: str) -> None:
        super().__init__(message)
        self.field = field_name


@dataclass(frozen=True)
class OnboardingState:
    status: OnboardingStatus
    scenario_version: int = 0
    step: str | None = None
    answers: dict[str, str] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def fresh(cls, status: OnboardingStatus) -> OnboardingState:
        return cls(status=status)


@dataclass(frozen=True)
class OnboardingPatch:
    """Частичное обновление: `None` значит «не менять»."""

    status: OnboardingStatus | None = None
    scenario_version: int | None = None
    step: str | None = None
    clear_step: bool = False
    answers: dict[str, str] | None = None


def normalize_step(step: str) -> str:
    value = step.strip()
    if not value or len(value) > MAX_STEP_LENGTH or not _TOKEN.match(value):
        raise OnboardingInvalidError("step", "шаг тура: латиница, цифры и ._-/, до 64 символов")
    return value


def normalize_answers(answers: dict[str, str]) -> dict[str, str]:
    unknown = sorted(set(answers) - ANSWER_KEYS)
    if unknown:
        raise OnboardingInvalidError("answers", f"неизвестные вопросы анкеты: {', '.join(unknown)}")
    clean: dict[str, str] = {}
    for key, raw in answers.items():
        value = raw.strip()
        if not value or len(value) > MAX_ANSWER_LENGTH or not _TOKEN.match(value):
            raise OnboardingInvalidError("answers", f"ответ на «{key}»: код варианта до {MAX_ANSWER_LENGTH} символов")
        clean[key] = value
    return clean


def apply_patch(state: OnboardingState, patch: OnboardingPatch, now: datetime) -> OnboardingState:
    """Новое состояние после обновления; время начала и окончания ставится по переходу статуса."""
    if patch.status is not None and patch.status not in CLIENT_STATUSES:
        raise OnboardingInvalidError("status", "этот статус назначает только сервер")
    if patch.scenario_version is not None and not 0 <= patch.scenario_version <= MAX_SCENARIO_VERSION:
        raise OnboardingInvalidError("scenario_version", "версия сценария вне допустимого диапазона")
    status = patch.status or state.status
    step = None if patch.clear_step else (normalize_step(patch.step) if patch.step is not None else state.step)
    answers = normalize_answers(patch.answers) if patch.answers is not None else state.answers
    started_at = state.started_at
    finished_at = state.finished_at
    if status is OnboardingStatus.in_progress and (state.status is not OnboardingStatus.in_progress or not started_at):
        started_at = now
        finished_at = None
    if status in FINISHED_STATUSES and status is not state.status:
        finished_at = now
    if status is OnboardingStatus.pending:
        started_at = finished_at = None
    return replace(
        state,
        status=status,
        scenario_version=state.scenario_version if patch.scenario_version is None else patch.scenario_version,
        step=step,
        answers=answers,
        started_at=started_at,
        finished_at=finished_at,
        updated_at=now,
    )


def restart(state: OnboardingState, now: datetime) -> OnboardingState:
    """«Пройти заново»: тур с начала, ответы анкеты остаются подсказкой по умолчанию."""
    return replace(
        state,
        status=OnboardingStatus.pending,
        step=None,
        started_at=None,
        finished_at=None,
        updated_at=now,
    )
