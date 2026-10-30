"""Контракт раннера: тела запросов и ответов `/api/runner/v1`.

Описание в contracts/runner/openapi.yaml; модели строгие (extra=forbid), а контрактный тест
(tests/unit/contract/test_runner_contract.py) сверяет их с описанием и с проводными датаклассами
`core/jobs/wire.py`. Форму меняют так: сначала openapi и эталоны, затем обе модели и тесты в одном коммите.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from hse_doc_studio.api.schemas.common import StrictModel

JobKindName = Literal["compile", "office.convert", "signature.verify_detached", "pack.submission", "ai.relay"]
JobStatusName = Literal["succeeded", "failed", "cancelled", "timed_out"]
JobStateName = Literal["queued", "running", "succeeded", "failed", "cancelled", "timed_out"]
ActorKindName = Literal["local", "user", "guest"]
ActorSourceName = Literal["session", "pat", "link", "local"]
ProjectRoleName = Literal["reader", "reviewer", "editor", "owner"]
LangName = Literal["ru", "en"]
Sha256 = Field(pattern=r"^[0-9a-f]{64}$")


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
    version: str
    tags: list[str]
    concurrency: int = Field(ge=1)
    resource_class: str


class RunnerRegisterResponseBody(StrictModel):
    runner_id: str
    runner_token: str
    lease_s: int
    heartbeat_s: int
    max_poll_wait_s: int


class PollRequestBody(StrictModel):
    wait_s: int = Field(ge=0, le=25)
    free_slots: int = Field(ge=0)
    # Шлёт только раннер с возможностью `ai_slots`; старый раннер не шлёт, и это валидно.
    free_ai_slots: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _some_slot_is_free(self) -> PollRequestBody:
        if self.free_slots + self.free_ai_slots < 1:
            raise ValueError("at least one free slot is needed to poll")
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


HostKindName = Literal["cli", "desktop"]
AiEndpointFlavorName = Literal["openai", "ollama"]
OwnerKindName = Literal["instance", "user"]
_ENDPOINT_NAME = r"^[a-z0-9][a-z0-9_-]{0,31}$"


class AiEndpointDeclBody(StrictModel):
    name: str = Field(pattern=_ENDPOINT_NAME)
    flavor: AiEndpointFlavorName


class RunnerAnnounceRequestBody(StrictModel):
    name: str | None = Field(min_length=1, max_length=128)
    version: str
    tags: list[str]
    concurrency: int = Field(ge=1)
    ai_concurrency: int = Field(ge=0)
    host_kind: HostKindName
    # Неизвестные сервер молча отбрасывает: так новый раннер говорит со старым сервером.
    features: list[str]
    ai_endpoints: list[AiEndpointDeclBody] = Field(max_length=16)


class RunnerAnnounceResponseBody(StrictModel):
    runner_id: str
    server_features: list[str]
    owner_kind: OwnerKindName
    paused: bool
    relay_keepalive_s: int


class RunnerPairStartRequestBody(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    host_kind: HostKindName


class RunnerPairStartResponseBody(StrictModel):
    device_code: str
    user_code: str = Field(pattern=r"^[BCDFGHJKLMNPQRSTVWXZ2-9]{4}-[BCDFGHJKLMNPQRSTVWXZ2-9]{4}$")
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


class RunnerPairPollRequestBody(StrictModel):
    device_code: str = Field(min_length=1)


class RunnerPairPollResponseBody(StrictModel):
    status: Literal["pending", "approved", "denied", "expired"]
    registration_token: str | None


class RelayEventBody(StrictModel):
    kind: Literal["head", "data", "end", "error"]
    status: int | None = Field(ge=100, le=599)
    content_type: str | None = Field(max_length=128)
    # base64; декодированный размер проверяет сервер (до 64 KiB на событие).
    data: str | None = Field(min_length=1)
    code: str | None


class RelayEventBatchBody(StrictModel):
    attempt: int = Field(ge=1)
    seq: int = Field(ge=0)
    events: list[RelayEventBody] = Field(min_length=1, max_length=64)


class RelayEventAckBody(StrictModel):
    cancel: bool
