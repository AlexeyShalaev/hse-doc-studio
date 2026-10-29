"""Контракт раннера: тела запросов и ответов `/api/runner/v1`.

Описание в contracts/runner/openapi.yaml; модели строгие (extra=forbid), а контрактный тест
(tests/unit/contract/test_runner_contract.py) сверяет их с описанием и с проводными датаклассами
`core/jobs/wire.py`. Форму меняют так: сначала openapi и эталоны, затем обе модели и тесты в одном коммите.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobKindName = Literal["compile", "office.convert", "signature.verify_detached", "pack.submission"]
JobStatusName = Literal["succeeded", "failed", "cancelled", "timed_out"]
JobStateName = Literal["queued", "running", "succeeded", "failed", "cancelled", "timed_out"]
ActorKindName = Literal["local", "user", "guest"]
ActorSourceName = Literal["session", "pat", "link", "local"]
ProjectRoleName = Literal["reader", "reviewer", "editor", "owner"]
LangName = Literal["ru", "en"]
Sha256 = Field(pattern=r"^[0-9a-f]{64}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    free_slots: int = Field(ge=1)


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
