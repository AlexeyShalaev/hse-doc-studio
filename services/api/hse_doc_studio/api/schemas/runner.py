"""Контракт раннера: тела запросов и ответов `/api/runner/v1`.

Описание в contracts/runner/openapi.yaml; модели строгие (extra=forbid), а контрактный тест
(tests/unit/contract/test_runner_contract.py) сверяет их с описанием и с проводными датаклассами
`core/jobs/wire.py`. Форму меняют так: сначала openapi и эталоны, затем обе модели и тесты в одном коммите.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from hse_doc_studio.api.schemas.common import StrictModel

JobKindName = Literal["compile", "office.convert", "signature.verify_detached", "pack.submission", "ai.relay"]
JobStatusName = Literal["succeeded", "failed", "cancelled", "timed_out"]
JobStateName = Literal["queued", "running", "succeeded", "failed", "cancelled", "timed_out"]
ActorKindName = Literal["local", "user", "guest"]
ActorSourceName = Literal["session", "pat", "link", "local"]
ProjectRoleName = Literal["reader", "reviewer", "editor", "owner"]
LangName = Literal["ru", "en"]
RunnerHostKindName = Literal["cli", "desktop"]
RunnerOwnerKindName = Literal["instance", "user"]
AiEndpointFlavorName = Literal["openai", "ollama"]
PairStatusName = Literal["pending", "approved", "denied", "expired"]
RelayEventKindName = Literal["head", "data", "end", "error"]
Sha256 = Field(pattern=r"^[0-9a-f]{64}$")

# Пределы того, что раннер пишет о себе в свою запись: регистрироваться может любой человек (личные раннеры),
# а запись читают списки админки и аккаунта и маршрутизатор (ёмкость по `concurrency`). Двоеточие и
# заглавные буквы в тегах допустимы: `archive:7z` и теги общих раннеров из окружения до этих пределов.
RunnerTag = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,31}$")]
MAX_RUNNER_TAGS = 32
MAX_RUNNER_VERSION = 64
MAX_RUNNER_CONCURRENCY = 64
MAX_RUNNER_AI_CONCURRENCY = 16
MAX_RESOURCE_CLASS = 32


class RunnerErrorBody(StrictModel):
    detail: str
    code: str


class ManifestEntry(StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Sha256
    size: int = Field(ge=0)


class ArtifactRefBody(StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Sha256
    size: int = Field(ge=0)


class ActorWire(StrictModel):
    kind: ActorKindName
    id: str | None
    name: str | None
    email: str | None
    link_id: str | None
    is_instance_admin: bool
    source: ActorSourceName | None
    scopes: list[str]


class JobSpecWire(StrictModel):
    id: str
    kind: JobKindName
    tags: list[str]
    project_id: str
    actor: ActorWire
    locale: LangName
    payload: dict[str, Any]


class JobEnvelopeBody(StrictModel):
    spec: JobSpecWire
    manifest: list[ManifestEntry]
    timeout_s: float = Field(gt=0)
    attempt: int = Field(ge=1)
    job_token: str = Field(min_length=1)
    actor_role: ProjectRoleName | None


class RunnerRegisterRequestBody(StrictModel):
    name: str = Field(min_length=1)
    protocol: int
    version: str = Field(max_length=MAX_RUNNER_VERSION)
    tags: list[RunnerTag] = Field(max_length=MAX_RUNNER_TAGS)
    concurrency: int = Field(ge=1, le=MAX_RUNNER_CONCURRENCY)
    resource_class: str = Field(max_length=MAX_RESOURCE_CLASS)


class RunnerRegisterResponseBody(StrictModel):
    runner_id: str
    runner_token: str
    lease_s: int
    heartbeat_s: int
    max_poll_wait_s: int


class PollRequestBody(StrictModel):
    wait_s: int = Field(ge=0, le=25)
    free_slots: int = Field(ge=0)
    # Только у раннера с возможностью `ai_slots`; старый раннер поле не шлёт.
    free_ai_slots: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _some_slot_is_free(self) -> PollRequestBody:
        if self.free_slots + self.free_ai_slots < 1:
            raise ValueError("a poll needs at least one free slot")
        return self


class PollResponseBody(StrictModel):
    envelope: JobEnvelopeBody | None


class HeartbeatRequestBody(StrictModel):
    attempt: int = Field(ge=1)


class HeartbeatResponseBody(StrictModel):
    cancel: bool
    lease_until: datetime


class LogBatchBody(StrictModel):
    attempt: int = Field(ge=1)
    seq: int = Field(ge=0)
    lines: list[str]


class BlobNeedRequestBody(StrictModel):
    attempt: int = Field(ge=1)
    sha256: list[str]


class BlobLocationBody(StrictModel):
    sha256: str = Sha256
    url: str | None


class BlobNeedResponseBody(StrictModel):
    blobs: list[BlobLocationBody]


class ArtifactUploadRequestBody(StrictModel):
    attempt: int = Field(ge=1)
    artifact: ArtifactRefBody


class ArtifactUploadResponseBody(StrictModel):
    url: str | None


class JobResultWire(StrictModel):
    status: JobStatusName
    data: dict[str, Any] | None
    error: dict[str, Any] | None


class CompleteRequestBody(StrictModel):
    attempt: int = Field(ge=1)
    result: JobResultWire
    artifacts: list[ArtifactRefBody]


class CompleteResponseBody(StrictModel):
    accepted: bool


class DeclaredAiEndpointBody(StrictModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")
    flavor: AiEndpointFlavorName


class RunnerAnnounceRequestBody(StrictModel):
    name: str | None = Field(min_length=1, max_length=128)
    version: str = Field(max_length=MAX_RUNNER_VERSION)
    tags: list[RunnerTag] = Field(max_length=MAX_RUNNER_TAGS)
    concurrency: int = Field(ge=1, le=MAX_RUNNER_CONCURRENCY)
    ai_concurrency: int = Field(ge=0, le=MAX_RUNNER_AI_CONCURRENCY)
    host_kind: RunnerHostKindName
    # Неизвестные возможности сервер отбрасывает, но длину списка и имён держит.
    features: list[Annotated[str, Field(max_length=32)]] = Field(max_length=16)
    ai_endpoints: list[DeclaredAiEndpointBody] = Field(max_length=16)

    @model_validator(mode="after")
    def _unique_endpoint_names(self) -> RunnerAnnounceRequestBody:
        names = [endpoint.name for endpoint in self.ai_endpoints]
        if len(set(names)) != len(names):
            raise ValueError("ai endpoint names must be unique")
        return self


class RunnerAnnounceResponseBody(StrictModel):
    runner_id: str
    server_features: list[str]
    owner_kind: RunnerOwnerKindName
    paused: bool
    relay_keepalive_s: int


class RunnerPairStartRequestBody(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    host_kind: RunnerHostKindName


class RunnerPairStartResponseBody(StrictModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


class RunnerPairPollRequestBody(StrictModel):
    device_code: str = Field(min_length=1, max_length=256)


class RunnerPairPollResponseBody(StrictModel):
    status: PairStatusName
    registration_token: str | None


class RelayEventBody(StrictModel):
    kind: RelayEventKindName
    status: int | None = Field(ge=100, le=599)
    content_type: str | None = Field(max_length=128)
    # base64: 64 KiB данных занимают не больше 87382 символов.
    data: str | None = Field(min_length=1, max_length=87384)
    code: str | None = Field(max_length=64)


class RelayEventBatchBody(StrictModel):
    attempt: int = Field(ge=1)
    seq: int = Field(ge=0)
    events: list[RelayEventBody] = Field(min_length=1, max_length=64)


class RelayEventAckBody(StrictModel):
    cancel: bool
