"""Схемы `/api/admin/model-servers`. Секретов в ответах нет: ключ сервера лежит у провайдера и наружу не отдаётся."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EngineName = Literal["ollama", "vllm", "sglang"]
StatusName = Literal["installing", "running", "stopped", "failed"]
StepStateName = Literal["pending", "running", "done", "failed"]
FitName = Literal["fits", "tight", "too_large", "unknown"]


class HardwareView(BaseModel):
    gpu_vendor: Literal["nvidia", "amd", "apple", "none"]
    gpu_name: str | None
    vram_mb: int | None
    total_ram_mb: int | None
    cpu_count: int | None
    docker_gpu_supported: bool
    arch: str | None
    disk_free_mb: int | None


class EngineAvailabilityView(BaseModel):
    engine: EngineName
    image: str
    available: bool
    reasons: list[str]


class CapabilitiesResponse(BaseModel):
    local_enabled: bool
    docker_available: bool
    hardware: HardwareView
    engines: list[EngineAvailabilityView]


class CatalogModelView(BaseModel):
    ref: str
    title: str
    params_b: float
    quant: str


class CatalogResponse(BaseModel):
    items: list[CatalogModelView]


class EstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: EngineName
    model: str = Field(min_length=1, max_length=200)
    params_b: float | None = Field(default=None, gt=0, le=2000)


class EstimateResponse(BaseModel):
    fit: FitName
    params_b: float | None
    weights_mb: int | None
    needed_mb: int | None
    available_mb: int | None
    memory_kind: Literal["vram", "ram"]
    disk_ok: bool | None
    reasons: list[str]


class InstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: EngineName
    model: str = Field(min_length=1, max_length=200)
    name: str = Field(default="", max_length=64)
    force: bool = False


class ModelServerResponse(BaseModel):
    id: str
    engine: EngineName
    model: str
    name: str
    status: StatusName
    endpoint: str | None
    provider_id: UUID | None
    image: str
    steps: dict[str, StepStateName]
    percent: int | None
    text: str
    error: str | None


class ModelServerList(BaseModel):
    items: list[ModelServerResponse]


class LogsResponse(BaseModel):
    text: str


class ModelServerSettingsResponse(BaseModel):
    """Токен Hugging Face наружу не отдаётся никогда: только признак, что он сохранён."""

    hf_token_set: bool


class SaveHfTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hf_token: str = Field(min_length=1, max_length=512, repr=False)
