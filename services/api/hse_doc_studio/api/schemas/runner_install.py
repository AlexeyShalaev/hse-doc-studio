"""Установка раннеров из админки (`/api/admin/runner-install`). Секретов в ответах нет: токен остаётся в Студии."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel

UnavailableReasonName = Literal["disabled", "no_socket", "docker_unreachable", "not_in_cluster", "no_permission"]
LocalTargetName = Literal["docker", "kubernetes"]
StepStateName = Literal["pending", "running", "done", "failed", "skipped"]


class CapabilityInfo(StrictModel):
    available: bool
    reason: UnavailableReasonName | None = None


class LocalCapabilitiesResponse(StrictModel):
    docker: CapabilityInfo
    kubernetes: CapabilityInfo


class StartLocalInstallRequest(StrictModel):
    name: str = Field(default="", max_length=40)
    concurrency: int = Field(default=1, ge=1, le=8)


class InstallStepInfo(StrictModel):
    key: str
    state: StepStateName
    detail: str = ""


class InstallJobInfo(StrictModel):
    id: str
    target: Literal["docker", "kubernetes", "ssh"]
    name: str
    state: Literal["running", "succeeded", "failed"]
    steps: list[InstallStepInfo]
    error_code: str | None = None
    error_detail: str = ""
    created_at: datetime


class LocalInstanceInfo(StrictModel):
    target: LocalTargetName
    name: str
    image: str
    state: str
    created_at: datetime | None = None
