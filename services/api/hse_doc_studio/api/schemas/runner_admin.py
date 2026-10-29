"""Админка раннеров: токены регистрации и список раннеров (`/api/admin`).

Секреты (`token`, `runner_token`) есть только в ответах на создание и ротацию; в списках их нет.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateRegistrationTokenRequest(StrictModel):
    label: str = Field(default="", max_length=128)
    ttl_hours: int = Field(default=24, ge=1, le=24 * 30)
    max_uses: int = Field(default=1, ge=1, le=100)


class RegistrationTokenInfo(StrictModel):
    id: str
    label: str
    created_at: datetime
    expires_at: datetime | None
    max_uses: int
    uses: int
    revoked: bool


class CreatedRegistrationTokenResponse(StrictModel):
    token: RegistrationTokenInfo
    secret: str


class RunnerInfo(StrictModel):
    id: str
    name: str
    tags: list[str]
    concurrency: int
    resource_class: str
    version: str
    created_at: datetime
    last_seen_at: datetime | None
    paused: bool
    revoked: bool


class UpdateRunnerRequest(StrictModel):
    paused: bool


class RotatedRunnerTokenResponse(StrictModel):
    runner: RunnerInfo
    runner_token: str
