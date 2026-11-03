"""Онбординг: состояние человека и частичное обновление."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from hse_doc_studio.api.schemas.common import StrictModel

OnboardingStatusValue = Literal["pending", "suggested", "in_progress", "completed", "skipped"]
_Token = Annotated[str, StringConstraints(min_length=1, max_length=96)]


class OnboardingStateResponse(StrictModel):
    # pending: новичок, тур откроется сам; suggested: давний пользователь, только приглашение.
    status: OnboardingStatusValue
    scenario_version: int
    step: str | None
    answers: dict[str, str]
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime | None


class UpdateOnboardingRequest(StrictModel):
    # `suggested` выставляет только сервер: клиент его прислать не может.
    status: Literal["pending", "in_progress", "completed", "skipped"] | None = None
    scenario_version: Annotated[int, Field(ge=0, le=10_000)] | None = None
    # Пустая строка снимает шаг (тур закончен или начат с начала).
    step: Annotated[str, StringConstraints(max_length=64)] | None = None
    answers: Annotated[dict[Literal["role", "work", "latex", "git"], _Token], Field(max_length=4)] | None = None
