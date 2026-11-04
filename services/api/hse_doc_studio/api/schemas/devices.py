"""Контракт подключённых Студий: сигнал присутствия и вид устройств (docs/design/connected-devices.md, раздел 5).

Запрос строгий: лишних полей нет, строки ограничены по длине и виду. Только метаданные состояния: путей, содержимого
документов и ключей в контракте нет.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.devices.entities import (
    DEVICE_ID_RE,
    MAX_DOC_ID,
    MAX_ENDPOINTS,
    MAX_MODELS,
    MAX_PROJECTS,
    MAX_VERSION,
    DeviceActivity,
    DeviceOs,
    DeviceReport,
    EndpointReport,
    PdfReport,
    ProjectReport,
    RunnerReport,
    SyncCode,
    sanitize_code,
    sanitize_doc_id,
    sanitize_endpoint_name,
    sanitize_model,
    sanitize_name,
)

SyncCodeName = Literal[
    "synced",
    "syncing",
    "ahead",
    "behind",
    "diverged",
    "conflicts",
    "offline",
    "auth_failed",
    "blocked",
    "error",
    "unfetched",
]
AiStateName = Literal[
    "ready",
    "not_opened",
    "runner_unpaired",
    "runner_offline",
    "runner_paused",
    "runner_revoked",
    "disabled",
    "endpoint_unreachable",
    "no_models",
    "no_provider",
    "studio_offline",
    "unknown",
]


class PdfSignal(StrictModel):
    doc_id: str = Field(max_length=MAX_DOC_ID)
    at: datetime
    ok: bool
    code: str | None = Field(default=None, max_length=64)


class ProjectSignal(StrictModel):
    project_id: str = Field(min_length=36, max_length=36)
    sync: SyncCodeName
    ahead: int = Field(default=0, ge=0, le=1_000_000)
    behind: int = Field(default=0, ge=0, le=1_000_000)
    last_sync_at: datetime | None = None
    auto_sync: bool = False
    pdf: PdfSignal | None = None


class RunnerSignal(StrictModel):
    runner_id: str | None = Field(default=None, max_length=64)
    state: str | None = Field(default=None, max_length=32)
    running_jobs: int = Field(default=0, ge=0, le=64)


class EndpointSignal(StrictModel):
    name: str = Field(max_length=32)
    flavor: Literal["openai", "ollama"]
    reachable: bool | None = None
    models: list[str] = Field(default_factory=list, max_length=MAX_MODELS)


class HeartbeatRequest(StrictModel):
    device_id: str
    name: str = Field(max_length=200)
    version: str = Field(max_length=MAX_VERSION)
    os: Literal["macos", "windows", "linux", "other"] = "other"
    activity: Literal["idle", "syncing", "building"] = "idle"
    runner: RunnerSignal | None = None
    endpoints: list[EndpointSignal] = Field(default_factory=list, max_length=MAX_ENDPOINTS)
    projects: list[ProjectSignal] = Field(default_factory=list, max_length=MAX_PROJECTS)

    @field_validator("device_id")
    @classmethod
    def _device_id(cls, value: str) -> str:
        if not DEVICE_ID_RE.fullmatch(value):
            raise ValueError("device_id must be 32 lowercase hex characters")
        return value

    def to_report(self) -> DeviceReport:
        from uuid import UUID  # noqa: PLC0415

        projects: list[ProjectReport] = []
        for item in self.projects:
            try:
                project_id = UUID(item.project_id)
            except ValueError:
                continue
            pdf = None
            if item.pdf is not None and (doc := sanitize_doc_id(item.pdf.doc_id)) is not None:
                pdf = PdfReport(doc_id=doc, at=item.pdf.at, ok=item.pdf.ok, code=sanitize_code(item.pdf.code))
            projects.append(
                ProjectReport(
                    project_id=project_id,
                    sync=SyncCode(item.sync),
                    ahead=item.ahead,
                    behind=item.behind,
                    last_sync_at=item.last_sync_at,
                    auto_sync=item.auto_sync,
                    pdf=pdf,
                )
            )
        endpoints: list[EndpointReport] = []
        for item in self.endpoints:
            name = sanitize_endpoint_name(item.name)
            if name is None:
                continue
            models = tuple(m for m in (sanitize_model(m) for m in item.models[:MAX_MODELS]) if m)
            endpoints.append(EndpointReport(name=name, flavor=item.flavor, reachable=item.reachable, models=models))
        runner = None
        if self.runner is not None:
            runner = RunnerReport(
                runner_id=self.runner.runner_id if _runner_id(self.runner.runner_id) else None,
                state=sanitize_code(self.runner.state),
                running_jobs=self.runner.running_jobs,
            )
        return DeviceReport(
            device_id=self.device_id,
            name=sanitize_name(self.name) or "Studio",
            version=sanitize_name(self.version) or "unknown",
            os=DeviceOs(self.os),
            activity=DeviceActivity(self.activity),
            runner=runner,
            endpoints=tuple(endpoints),
            projects=tuple(projects),
        )


def _runner_id(value: str | None) -> bool:
    return value is not None and value.isalnum() and len(value) <= 64


class HeartbeatResponse(StrictModel):
    interval_s: int
    online_window_s: int
    server_time: datetime


class RunnerOut(StrictModel):
    id: str
    name: str
    state: Literal["online", "stale", "offline", "paused", "revoked", "disabled"]
    tags: list[str]
    concurrency: int
    running_jobs: int
    busy: bool


class EndpointOut(StrictModel):
    name: str
    flavor: Literal["openai", "ollama"]
    reachable: bool | None
    models: list[str]
    provider_id: str | None
    provider_name: str | None
    state: AiStateName


class AiOut(StrictModel):
    state: AiStateName
    endpoints: list[EndpointOut]


class PdfOut(StrictModel):
    doc_id: str
    at: datetime
    ok: bool
    code: str | None


class ProjectSyncOut(StrictModel):
    sync: SyncCodeName
    ahead: int
    behind: int
    last_sync_at: datetime | None
    auto_sync: bool
    pdf: PdfOut | None


class DeviceOut(StrictModel):
    id: str
    name: str
    version: str
    os: Literal["macos", "windows", "linux", "other"]
    presence: Literal["online", "offline"]
    last_seen_at: datetime
    activity: Literal["idle", "syncing", "building"]
    projects_count: int
    runner: RunnerOut | None
    ai: AiOut
    project: ProjectSyncOut | None


class WorkingLocallyOut(StrictModel):
    user_id: str
    name: str


class ProjectStudiosResponse(StrictModel):
    online_window_s: int
    mine: list[DeviceOut]
    # Другие участники проекта, чья Студия сейчас в сети: ни имени машины, ни версии, ни раннера.
    others: list[WorkingLocallyOut]


class AccountDevicesResponse(StrictModel):
    online_window_s: int
    items: list[DeviceOut]


class DevicesOverviewResponse(StrictModel):
    online_window_s: int
    device: DeviceOut | None
    others: list[WorkingLocallyOut]
