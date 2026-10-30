"""Облачные сборки локальной Студии (`/api/v1/remote-runner`, только локальный режим).

Токен регистрации приходит в теле `RemoteRunnerTokenRequest` и дальше живёт только в памяти
процесса; в ответах секретов нет. Адрес ИИ (`url`) показывается хозяину машины, на сервер он
не уходит: сервер знает только имя и вид.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.remote_runner import (
    AI_ENDPOINT_NAME_PATTERN,
    REMOTE_RUNNER_MAX_CONCURRENCY,
    REMOTE_RUNNER_NAME_MAX,
)

RemoteRunnerStateName = Literal[
    "off", "unpaired", "pairing", "connecting", "online", "paused", "offline", "revoked", "disabled", "error"
]


class RemoteRunnerAiEndpoint(StrictModel):
    name: str
    provider_id: str
    flavor: Literal["openai", "ollama"]
    url: str


class RemoteRunnerPairingInfo(StrictModel):
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
    ai_endpoints: list[RemoteRunnerAiEndpoint]
    pairing: RemoteRunnerPairingInfo | None


class RemoteAiEndpointChoiceBody(StrictModel):
    name: str = Field(pattern=AI_ENDPOINT_NAME_PATTERN)
    provider_id: str = Field(min_length=1, max_length=64)


class UpdateRemoteRunnerRequest(StrictModel):
    """null значит «не менять»."""

    enabled: bool | None = None
    server_url: str | None = Field(default=None, max_length=2048)
    name: str | None = Field(default=None, min_length=1, max_length=REMOTE_RUNNER_NAME_MAX)
    concurrency: int | None = Field(default=None, ge=1, le=REMOTE_RUNNER_MAX_CONCURRENCY)
    yield_to_local: bool | None = None
    ai_endpoints: list[RemoteAiEndpointChoiceBody] | None = Field(default=None, max_length=16)


class RemoteRunnerPairRequest(StrictModel):
    server_url: str = Field(max_length=2048)
    name: str = Field(min_length=1, max_length=REMOTE_RUNNER_NAME_MAX)


class RemoteRunnerTokenRequest(StrictModel):
    server_url: str = Field(max_length=2048)
    token: str = Field(pattern=r"^\s*hsrt_[A-Za-z0-9_-]{16,}\s*$", max_length=256)
