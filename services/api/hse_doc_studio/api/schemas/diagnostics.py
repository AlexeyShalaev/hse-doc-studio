"""Схемы админки «Самодиагностика»: проверки со статусом и подсказкой, итог, пороги."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel

StatusName = Literal["ok", "warn", "fail"]
GroupName = Literal["data", "compute", "security", "operations"]


class DiagCheckBody(StrictModel):
    id: str
    group: GroupName
    # Не проверялась ни разу (свежая установка до первого прохода): статус null.
    status: StatusName | None
    reason: str | None
    # Код подсказки «что делать»; null, пока всё в порядке.
    hint: str | None
    values: dict[str, str | int | float]
    applicable: bool
    checked_at: datetime | None
    status_since: datetime | None
    duration_ms: int | None


class DiagThresholdBody(StrictModel):
    name: str
    value: int
    default: int
    min: int
    max: int


class DiagOverviewBody(StrictModel):
    overall: StatusName
    enabled: bool
    interval_s: float
    last_tick_at: datetime | None
    checks: list[DiagCheckBody]
    thresholds: list[DiagThresholdBody]
    notify: bool


class DiagThresholdsRequest(StrictModel):
    values: dict[str, int]
    notify: bool


class DiagRunRequest(StrictModel):
    # null: все проверки.
    check: str | None = Field(default=None, max_length=64)
