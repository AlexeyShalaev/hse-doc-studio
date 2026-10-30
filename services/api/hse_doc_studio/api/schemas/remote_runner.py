"""Локальная Студия как личный раннер (`/api/v1/remote-runner*`, только локальный режим).

Формы совпадают с эталонами `contracts/server/fixtures/{RemoteRunner*,UpdateRemoteRunnerRequest}`.
Токен регистрации в ответах не появляется никогда; ключи локальных провайдеров на сервер не уходят.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel

RemoteRunnerStateName = Literal[
    "off", "unpaired", "pairing", "connecting", "online", "paused", "offline", "revoked", "disabled", "error"
]


class RemoteAiEndpoint(StrictModel):
    name: str
    provider_id: str
    flavor: Literal["openai", "ollama"]
    url: str


class RemoteRunnerPairing(StrictModel):
    user_code: str
    verification_uri_complete: str
    expires_at: datetime


class RemoteRunnerStatus(StrictModel):
    enabled: bool
    server_url: str | None
    paired: bool
    runner_id: str | None
    runner_name: str | None
    state: RemoteRunnerStateName
    detail_code: str | None
    running_jobs: int
    concurrency: int
    yield_to_local: bool
    docker: Literal["ok", "missing"]
    tex_image: Literal["ready", "missing"]
    ai_endpoints: list[RemoteAiEndpoint]
    pairing: RemoteRunnerPairing | None


class RemoteAiEndpointChoice(StrictModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
    provider_id: str


class UpdateRemoteRunnerRequest(StrictModel):
    """`null` значит «не менять»."""

    enabled: bool | None = None
    server_url: str | None = Field(default=None, max_length=2048)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    concurrency: int | None = Field(default=None, ge=1, le=4)
    yield_to_local: bool | None = None
    ai_endpoints: list[RemoteAiEndpointChoice] | None = Field(default=None, max_length=16)


class RemoteRunnerPairRequest(StrictModel):
    server_url: str = Field(min_length=1, max_length=2048)
    name: str = Field(min_length=1, max_length=128)


class RemoteRunnerTokenRequest(StrictModel):
    server_url: str = Field(min_length=1, max_length=2048)
    token: str = Field(min_length=1, max_length=256)
