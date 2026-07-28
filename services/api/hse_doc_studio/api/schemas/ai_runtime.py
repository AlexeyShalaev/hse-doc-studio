from __future__ import annotations

from pydantic import BaseModel, Field


class HardwareInfoResponse(BaseModel):
    gpu_vendor: str = Field(description="nvidia | apple | amd | none")
    gpu_name: str | None
    vram_mb: int | None
    total_ram_mb: int | None
    cpu_count: int | None
    docker_gpu_supported: bool = Field(
        description="True only when the GPU can be passed into a Docker container on this OS (NVIDIA on Linux/WSL2)."
    )


class CatalogModelResponse(BaseModel):
    name: str = Field(description="Exact `ollama pull` tag.")
    label: str
    family: str = Field(default="", description="Model family for grouping/filter.")
    params_b: float
    size_gb: float
    min_vram_gb: float
    min_ram_gb: float
    tasks: list[str]
    description: str
    runnable: bool = Field(description="Fits the detected hardware at all (GPU or CPU).")
    on_gpu: bool = Field(description="Fits within the detected GPU memory budget.")
    recommended: bool = Field(description="The single best default for this hardware.")
    note: str = Field(description="Short RU explanation of the fit.")


class ModelCatalogResponse(BaseModel):
    hardware: HardwareInfoResponse
    models: list[CatalogModelResponse]
    allow_custom: bool = Field(description="Whether pulling arbitrary (non-catalog) models by name is allowed.")


class RegistryModelResponse(BaseModel):
    name: str = Field(description="Library model name; `ollama pull <name>` defaults to :latest.")
    description: str
    pulls: str = Field(description="Human-readable popularity (e.g. '31.8M Pulls'); may be empty.")
    capabilities: list[str]


class RegistrySearchResponse(BaseModel):
    models: list[RegistryModelResponse]


class OllamaRuntimeStatusResponse(BaseModel):
    mode: str = Field(description="native | docker | none")
    base_url: str | None
    version: str | None
    docker_available: bool
    engine_image_installed: bool
    installed_models: list[str]


class StartRuntimeResponse(BaseModel):
    started: bool
    status: OllamaRuntimeStatusResponse


class StopRuntimeResponse(BaseModel):
    stopped: bool
    detail: str | None
    status: OllamaRuntimeStatusResponse


class DeleteModelResponse(BaseModel):
    deleted: bool
    installed_models: list[str]


class PullJobResponse(BaseModel):
    name: str
    state: str = Field(description="running | success | failure")
    message: str = Field(description="Latest progress line (embeds the percent).")
    error: str | None


class PullJobsResponse(BaseModel):
    jobs: list[PullJobResponse]


class SyncProviderResponse(BaseModel):
    provider_id: str | None
    models: list[str]


class LoadedModelResponse(BaseModel):
    name: str
    size_bytes: int = Field(description="Total bytes held in memory.")
    vram_bytes: int = Field(description="Bytes in VRAM (0 = running on CPU).")
    expires_at: str | None = Field(description="ISO timestamp of automatic unload, if known.")


class LoadedModelsResponse(BaseModel):
    models: list[LoadedModelResponse]


class UnloadModelResponse(BaseModel):
    unloaded: bool
