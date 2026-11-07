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


# ---- SSH ----

SshAuthKindName = Literal["password", "key"]


class SshProbeRequest(StrictModel):
    """Секреты (`password`, `private_key`, `passphrase`) принимаются только здесь и никогда не возвращаются."""

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.@-]*$")
    auth_kind: SshAuthKindName
    password: str | None = Field(default=None, max_length=1024, repr=False)
    private_key: str | None = Field(default=None, max_length=16384, repr=False)
    passphrase: str | None = Field(default=None, max_length=1024, repr=False)
    sudo: bool = False
    save_credentials: bool = False
    label: str = Field(default="", max_length=80)


class HostKeyInfo(StrictModel):
    key_type: str
    fingerprint: str


class SshProbeResponse(StrictModel):
    session_id: str
    host_key: HostKeyInfo
    expires_in_s: int


class SshConfirmRequest(StrictModel):
    fingerprint: str = Field(min_length=10, max_length=128)


class RemoteSystemInfo(StrictModel):
    os: str
    arch: str
    distro: str
    has_docker: bool
    docker_usable: bool
    has_systemd: bool
    is_root: bool


PlanActionName = Literal["run", "skip", "install_docker", "blocked"]


class PlanStepInfo(StrictModel):
    key: str
    action: PlanActionName


class SshPlanResponse(StrictModel):
    session_id: str
    system: RemoteSystemInfo
    plan: list[PlanStepInfo]


class ModelServerInstall(StrictModel):
    """Вместо раннера поставить сервер ИИ-модели (docs/design/model-servers.md): слой SSH тот же."""

    engine: Literal["ollama", "vllm", "sglang"]
    model: str = Field(min_length=1, max_length=200)
    name: str = Field(default="", max_length=64)
    # localhost: слушает только loopback машины, провайдер не регистрируется; public: наружу, нужен ключ API.
    exposure: Literal["localhost", "public"] = "localhost"
    acknowledge_public: bool = False
    force: bool = False


class SshInstallRequest(StrictModel):
    name: str = Field(default="", max_length=40)
    install_docker: bool = False
    model_server: ModelServerInstall | None = None


class SavedCredentialInfo(StrictModel):
    """Факт наличия сохранённого доступа: значения пароля и ключа не показываются никогда."""

    id: str
    label: str
    host: str
    port: int
    username: str
    sudo: bool
    auth_kind: SshAuthKindName
    key_type: str
    fingerprint: str
    created_at: datetime
    last_used_at: datetime | None = None
    runner_name: str | None = None


class SshRunSavedRequest(StrictModel):
    action: Literal["update", "reinstall"]


class SshCapabilityResponse(StrictModel):
    enabled: bool
    can_save_credentials: bool
