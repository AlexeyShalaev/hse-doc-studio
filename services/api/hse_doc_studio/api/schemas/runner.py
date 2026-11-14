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


# Отчёт раннера о том, как он развёрнут (`POST /deployment`, возможность `deployment_info`).
_K8S_NAME = Field(min_length=1, max_length=253)
_QUANTITY = Field(min_length=1, max_length=32)
BuildExecutorName = Literal["docker", "kubernetes"]
RunnerPlatformName = Literal["kubernetes", "container", "host"]
ResourceSourceName = Literal["pod", "cgroup", "config", "cluster"]


class RunnerResourcesBody(StrictModel):
    cpu_request: str | None = _QUANTITY
    cpu_limit: str | None = _QUANTITY
    memory_request: str | None = _QUANTITY
    memory_limit: str | None = _QUANTITY
    ephemeral_request: str | None = _QUANTITY
    ephemeral_limit: str | None = _QUANTITY
    source: ResourceSourceName


class RunnerSecurityBody(StrictModel):
    run_as_non_root: bool | None
    run_as_user: int | None = Field(ge=0, le=2**31 - 1)
    read_only_root: bool | None
    no_privilege_escalation: bool | None
    seccomp: bool | None
    capabilities_dropped: bool | None
    automount_token: bool | None


class RunnerBuildIsolationBody(StrictModel):
    namespace: str | None = _K8S_NAME
    image: str | None = Field(min_length=1, max_length=512)
    resources: RunnerResourcesBody | None
    network_disabled: bool | None
    pids_limit: int | None = Field(ge=1, le=1 << 22)
    work_size_limit: str | None = _QUANTITY
    tmp_size_limit: str | None = _QUANTITY
    active_deadline_s: int | None = Field(ge=1, le=7 * 24 * 3600)
    runtime_class: str | None = _K8S_NAME
    security: RunnerSecurityBody | None


class RunnerDeploymentBody(StrictModel):
    executor: BuildExecutorName
    platform: RunnerPlatformName
    namespace: str | None = _K8S_NAME
    pod_name: str | None = _K8S_NAME
    service_account: str | None = _K8S_NAME
    resources: RunnerResourcesBody | None
    security: RunnerSecurityBody | None
    build: RunnerBuildIsolationBody | None


# Канал команд (`/control/*`, возможность `control`) и диск раннера (`POST /disk`, возможность `disk`).
# Пределы те же, что в `core/jobs/disk.py`; отчёт больше 64 КБ сервер отвергает до разбора (413).
DiskTargetName = Literal[
    "old_versions", "unused_images", "build_cache", "dangling_images", "stopped_containers", "runner_cache"
]
DockerDiskReasonName = Literal["kubernetes", "managed_locally"]
DiskCategoryKeyName = Literal["compile", "languagetool", "office", "ai", "app", "cache", "runtime"]
StudioImageCategoryName = Literal["compile", "languagetool", "office", "ai", "app"]
OldItemKindName = Literal["studio_image", "service_image", "container"]
RunnerCommandKindName = Literal["disk.measure", "disk.cleanup"]
ReportedCommandStateName = Literal["running", "done", "cancelled", "error"]
CommandStepKindName = Literal[
    "build_cache", "dangling_images", "image", "container", "runner_blobs", "runner_workspaces"
]
CommandStepStatusName = Literal["pending", "running", "done", "error", "skipped"]
_BYTES = Field(ge=0)
_REF = Field(min_length=1, max_length=384)
_STEP_ERROR = Field(min_length=1, max_length=300)
_LISTED = 100


class ControlPollRequestBody(StrictModel):
    wait_s: int = Field(ge=0, le=25)


class DiskMeasurePayloadBody(StrictModel):
    pass


class DiskCleanupPayloadBody(StrictModel):
    targets: list[DiskTargetName] = Field(min_length=1, max_length=6)
    include_rollback: bool
    # Автоочистку поставил сервер по порогу места (`disk_auto`); едет только когда `true`.
    auto: bool = False

    @model_validator(mode="after")
    def _unique_targets(self) -> DiskCleanupPayloadBody:
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("targets must be unique")
        if self.include_rollback and "old_versions" not in self.targets:
            raise ValueError("include_rollback needs the old_versions target")
        if self.auto and self.include_rollback:
            raise ValueError("an automatic cleanup never removes the rollback image")
        return self


class RunnerCommandEnvelopeBody(StrictModel):
    id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    kind: RunnerCommandKindName
    payload: DiskCleanupPayloadBody | DiskMeasurePayloadBody
    issued_at: datetime

    @model_validator(mode="after")
    def _payload_matches_kind(self) -> RunnerCommandEnvelopeBody:
        cleanup = isinstance(self.payload, DiskCleanupPayloadBody)
        if cleanup != (self.kind == "disk.cleanup"):
            raise ValueError(f"{self.kind} does not take this payload")
        return self


class ControlPollResponseBody(StrictModel):
    command: RunnerCommandEnvelopeBody | None


class DiskCheckRequestBody(StrictModel):
    free_bytes: int = _BYTES
    total_bytes: int = _BYTES

    @model_validator(mode="after")
    def _free_within_total(self) -> DiskCheckRequestBody:
        if self.free_bytes > self.total_bytes:
            raise ValueError("free_bytes exceeds total_bytes")
        return self


class DiskCheckResponseBody(StrictModel):
    command: RunnerCommandEnvelopeBody | None


class CommandStepBody(StrictModel):
    kind: CommandStepKindName
    ref: str | None = _REF
    status: CommandStepStatusName
    freed_bytes: int = _BYTES
    error: str | None = _STEP_ERROR

    @model_validator(mode="after")
    def _ref_matches_kind(self) -> CommandStepBody:
        if (self.ref is not None) != (self.kind in ("image", "container")):
            raise ValueError(f"{self.kind} step ref mismatch")
        return self


class CommandProgressBody(StrictModel):
    steps: list[CommandStepBody] = Field(max_length=512)
    freed_bytes: int = _BYTES
    error: str | None = _STEP_ERROR


class CommandProgressRequestBody(StrictModel):
    state: ReportedCommandStateName
    progress: CommandProgressBody


class CommandProgressResponseBody(StrictModel):
    cancel: bool


class DiskCategoryBody(StrictModel):
    key: DiskCategoryKeyName
    bytes: int = _BYTES


class DiskBuildCacheBody(StrictModel):
    bytes: int = _BYTES
    reclaimable_bytes: int = _BYTES
    count: int = _BYTES


class DiskCountBody(StrictModel):
    bytes: int = _BYTES
    count: int = _BYTES


class UnusedImageBody(StrictModel):
    ref: str = _REF
    category: StudioImageCategoryName
    size_bytes: int = _BYTES


class OldItemBody(StrictModel):
    kind: OldItemKindName
    ref: str = _REF
    version: str = Field(max_length=64)
    size_bytes: int = _BYTES


class OldVersionsBody(StrictModel):
    current_version: str = Field(max_length=64)
    rollback: OldItemBody | None
    items: list[OldItemBody] = Field(max_length=_LISTED)
    reclaimable_bytes: int = _BYTES
    rollback_bytes: int = _BYTES


class DockerVolumeBody(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    size_bytes: int = _BYTES


class DockerDiskBody(StrictModel):
    available: bool
    categories: list[DiskCategoryBody] = Field(max_length=7)
    total_bytes: int = _BYTES
    cleanable_bytes: int = _BYTES
    build_cache: DiskBuildCacheBody
    dangling: DiskCountBody
    stopped_containers: DiskCountBody
    unused_images: list[UnusedImageBody] = Field(max_length=_LISTED)
    unused_truncated: bool
    old_versions: OldVersionsBody
    volumes: list[DockerVolumeBody] = Field(max_length=32)


class BlobCacheDiskBody(StrictModel):
    bytes: int = _BYTES
    count: int = _BYTES
    limit_bytes: int = _BYTES


class WorkspacesDiskBody(StrictModel):
    bytes: int = _BYTES
    count: int = _BYTES
    limit_bytes: int = _BYTES
    busy: int = _BYTES


class RunnerCacheDiskBody(StrictModel):
    blobs: BlobCacheDiskBody
    workspaces: WorkspacesDiskBody


class DataVolumeBody(StrictModel):
    total_bytes: int = _BYTES
    free_bytes: int = _BYTES


class RunnerDiskReportBody(StrictModel):
    measured_at: datetime
    targets: list[DiskTargetName] = Field(max_length=6)
    docker: DockerDiskBody | None
    docker_reason: DockerDiskReasonName | None
    cache: RunnerCacheDiskBody
    volume: DataVolumeBody | None

    @model_validator(mode="after")
    def _consistent(self) -> RunnerDiskReportBody:
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("targets must be unique")
        if (self.docker is None) == (self.docker_reason is None):
            raise ValueError("docker is null exactly when docker_reason is set")
        docker_usable = self.docker is not None and self.docker.available
        if not docker_usable and set(self.targets) - {"runner_cache"}:
            raise ValueError("docker targets need a reachable docker")
        return self
