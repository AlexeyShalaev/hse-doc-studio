"""Личные раннеры: аккаунт (`/api/v1/account/runners*`), сопряжение, политика сборок проекта и размещение сборки.

Формы совпадают с эталонами `contracts/server/fixtures/{MyRunner*,RunnerPairing*,ProjectBuildRunners,CompilePlacement}`.
Секреты (`secret`, `runner_token`) есть только в ответах на создание и смену токена. Соавтор о раннере
владельца видит только имя и состояние (`OwnerRunnerChip`, `CompilePlacement`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel

MyRunnerStateName = Literal["online", "stale", "offline", "paused", "revoked", "disabled"]
RunnerHostKindName = Literal["cli", "desktop"]
AiEndpointFlavorName = Literal["openai", "ollama"]
PairingStatusName = Literal["pending", "approved", "denied", "expired"]
BuildRunnersPolicyName = Literal["shared", "owner"]
OwnerRunnerStateName = Literal["online", "stale", "offline", "paused", "disabled"]
PlacementStateName = Literal["waiting_personal", "personal", "shared"]
PlacementFallbackName = Literal["offline", "busy", "timeout", "lost", "disabled"]


class MyRunnerAiEndpoint(StrictModel):
    name: str
    flavor: AiEndpointFlavorName


class MyRunner(StrictModel):
    id: str
    name: str
    state: MyRunnerStateName
    host_kind: RunnerHostKindName
    tags: list[str]
    concurrency: int
    ai_concurrency: int
    version: str
    created_at: datetime
    last_seen_at: datetime | None
    last_seen_ip: str | None
    paused: bool
    revoked: bool
    running_jobs: int
    ai_endpoints: list[MyRunnerAiEndpoint]
    features: list[str]


class UpdateMyRunnerRequest(StrictModel):
    """`null` значит «не менять»."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    paused: bool | None = None


class MyRunnerRotated(StrictModel):
    runner: MyRunner
    runner_token: str
    # Команда запуска с новым токеном (`HSE_RUNNER__RUNNER_TOKEN` перекрывает identity.json).
    command: str


class MyRunnerToken(StrictModel):
    id: str
    label: str
    created_at: datetime
    expires_at: datetime | None
    used: bool
    revoked: bool


class CreateMyRunnerTokenRequest(StrictModel):
    label: str = Field(default="", max_length=128)
    ttl_hours: int = Field(default=24, ge=1, le=168)


class MyRunnerTokenCreated(StrictModel):
    token: MyRunnerToken
    secret: str
    # Команда для установленного пакета и для образа установки той же версии.
    command: str
    docker_command: str


class RunnerPairingInfo(StrictModel):
    user_code: str
    name: str
    host_kind: RunnerHostKindName
    requested_at: datetime
    expires_at: datetime
    client_ip: str | None
    status: PairingStatusName


class RunnerPairingDecisionRequest(StrictModel):
    decision: Literal["approve", "deny"]


class OwnerRunnerChip(StrictModel):
    name: str
    state: OwnerRunnerStateName


class ProjectBuildRunners(StrictModel):
    policy: BuildRunnersPolicyName
    # Править может только владелец личного проекта.
    editable: bool
    project_kind: Literal["personal", "org"]
    personal_runners_enabled: bool
    # Куда пойдёт сборка, которую поставит смотрящий: на личный раннер владельца сначала или сразу на общие.
    my_builds: Literal["personal_first", "shared"]
    wait_s: int
    owner_runners: list[OwnerRunnerChip]


class UpdateProjectBuildRunnersRequest(StrictModel):
    policy: BuildRunnersPolicyName


class CompilePlacement(StrictModel):
    state: PlacementStateName
    runner_name: str | None
    # `me`: раннер смотрящего, `owner`: раннер владельца проекта.
    runner_owner: Literal["me", "owner"] | None
    fallback: PlacementFallbackName | None
    wait_s: int | None
