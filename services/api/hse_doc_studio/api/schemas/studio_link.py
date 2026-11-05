"""Контракт связи локальной Студии с облаком: устройство, присутствие и сборки (docs/design/connected-devices.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.builds import BuildOut
from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.api.schemas.devices import DevicesOverviewResponse, ProjectSyncOut

BuildRelationName = Literal["none", "cloud_only", "local_only", "same", "cloud_newer", "local_newer"]
FetchStatusName = Literal[
    "downloaded", "unchanged", "kept_local", "skipped_stale", "too_large", "no_cloud_build", "failed"
]


class LocalDeviceOut(StrictModel):
    device_id: str
    name: str
    default_name: str
    custom: bool


class DeviceNameRequest(StrictModel):
    # Пустое имя или null возвращает имя по умолчанию.
    name: str | None = Field(default=None, max_length=200)


class LocalRunnerOut(StrictModel):
    state: str
    paired: bool
    name: str | None
    running_jobs: int
    enabled: bool


class LocalEndpointOut(StrictModel):
    name: str
    flavor: Literal["openai", "ollama"]
    # Адрес дошёл до сервера (`/announce`): пока нет, облако о нём не знает.
    announced: bool
    reachable: bool | None
    models: list[str]


class LastPresenceOut(StrictModel):
    at: datetime
    ok: bool
    code: str | None
    interval_s: int
    online_window_s: int


class LinkServerOut(StrictModel):
    credential_id: str
    server_url: str
    host: str
    # ok, expired, revoked, unreachable: как у списка серверов.
    state: str
    account_name: str | None
    last: LastPresenceOut | None
    # Как облако видит эту Студию; null, если сервер не ответил (причина в cloud_error).
    cloud: DevicesOverviewResponse | None
    cloud_error: str | None


class StudioLinkResponse(StrictModel):
    device: LocalDeviceOut
    runner: LocalRunnerOut
    endpoints: list[LocalEndpointOut]
    servers: list[LinkServerOut]
    project: ProjectSyncOut | None


class LocalBuildOut(StrictModel):
    at: datetime
    commit: str | None
    fresh: bool | None
    sha256: str | None
    pages: int | None
    from_cloud: bool


class DocumentBuildStatusOut(StrictModel):
    doc_id: str
    local: LocalBuildOut | None
    cloud: BuildOut | None
    cloud_running: bool
    studio: BuildOut | None
    relation: BuildRelationName
    can_fetch: bool


class LocalBuildsResponse(StrictModel):
    connected: bool
    cloud_error: str | None
    local_head: str | None
    local_dirty: bool
    cloud_head: str | None
    documents: list[DocumentBuildStatusOut]


class FetchBuildRequest(StrictModel):
    # Без документа берутся все документы проекта, у которых есть облачная сборка.
    doc_id: str | None = Field(default=None, max_length=128)
    # Перезаписать и более свежую локальную сборку.
    force: bool = False
    # Автоматический заход: берёт только сборку из версии, что лежит у человека сейчас.
    auto: bool = False


class FetchOutcomeOut(StrictModel):
    doc_id: str
    status: FetchStatusName
    code: str | None
    size: int | None


class FetchBuildResponse(StrictModel):
    items: list[FetchOutcomeOut]


class CancelCloudBuildsRequest(StrictModel):
    # Без документа останавливаются все облачные сборки проекта.
    doc_id: str | None = Field(default=None, max_length=128)


class CancelCloudBuildsResponse(StrictModel):
    cancelled: int
