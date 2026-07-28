from __future__ import annotations

import json
from collections.abc import AsyncIterator

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.schemas.ai_runtime import (
    CatalogModelResponse,
    DeleteModelResponse,
    HardwareInfoResponse,
    LoadedModelResponse,
    LoadedModelsResponse,
    ModelCatalogResponse,
    OllamaRuntimeStatusResponse,
    PullJobResponse,
    PullJobsResponse,
    RegistryModelResponse,
    RegistrySearchResponse,
    StartRuntimeResponse,
    StopRuntimeResponse,
    SyncProviderResponse,
    UnloadModelResponse,
)
from hse_doc_studio.core.ai_catalog import ModelFit, localize_tasks
from hse_doc_studio.core.entities import (
    HardwareInfo,
    LoadedModel,
    OllamaRuntimeStatus,
    PullJob,
    RegistryModel,
)
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.ai_runtime.delete_model import DeleteOllamaModelInput, DeleteOllamaModelUC
from hse_doc_studio.use_cases.ai_runtime.detect_hardware import DetectHardwareUC
from hse_doc_studio.use_cases.ai_runtime.dismiss_pull import DismissPullInput, DismissPullUC
from hse_doc_studio.use_cases.ai_runtime.get_runtime_status import GetOllamaStatusUC
from hse_doc_studio.use_cases.ai_runtime.install_ollama_engine import InstallOllamaEngineUC
from hse_doc_studio.use_cases.ai_runtime.list_loaded_models import ListLoadedModelsUC
from hse_doc_studio.use_cases.ai_runtime.list_model_catalog import ListModelCatalogUC
from hse_doc_studio.use_cases.ai_runtime.list_pulls import ListPullsUC
from hse_doc_studio.use_cases.ai_runtime.search_registry import SearchRegistryInput, SearchRegistryUC
from hse_doc_studio.use_cases.ai_runtime.start_pull import StartPullInput, StartPullUC
from hse_doc_studio.use_cases.ai_runtime.start_runtime import StartOllamaRuntimeUC
from hse_doc_studio.use_cases.ai_runtime.stop_runtime import StopOllamaRuntimeUC
from hse_doc_studio.use_cases.ai_runtime.sync_local_provider import SyncLocalOllamaProviderUC
from hse_doc_studio.use_cases.ai_runtime.unload_model import UnloadModelInput, UnloadModelUC

router = APIRouter(route_class=DishkaRoute)
logger = structlog.get_logger()


def _map_hardware(hw: HardwareInfo) -> HardwareInfoResponse:
    return HardwareInfoResponse(
        gpu_vendor=str(hw.gpu_vendor),
        gpu_name=hw.gpu_name,
        vram_mb=hw.vram_mb,
        total_ram_mb=hw.total_ram_mb,
        cpu_count=hw.cpu_count,
        docker_gpu_supported=hw.docker_gpu_supported,
    )


def _map_registry(m: RegistryModel) -> RegistryModelResponse:
    return RegistryModelResponse(
        name=m.name,
        description=m.description,
        pulls=m.pulls,
        capabilities=m.capabilities,
    )


def _map_model(fit: ModelFit, language: Lang) -> CatalogModelResponse:
    m = fit.model
    return CatalogModelResponse(
        name=m.name,
        label=m.label,
        family=m.family,
        params_b=m.params_b,
        size_gb=m.size_gb,
        min_vram_gb=m.min_vram_gb,
        min_ram_gb=m.min_ram_gb,
        tasks=localize_tasks(m.tasks, language),
        description=m.description,
        runnable=fit.runnable,
        on_gpu=fit.on_gpu,
        recommended=fit.recommended,
        note=fit.note,
    )


def _map_job(j: PullJob) -> PullJobResponse:
    return PullJobResponse(name=j.name, state=j.state, message=j.message, error=j.error)


def _map_loaded(m: LoadedModel) -> LoadedModelResponse:
    return LoadedModelResponse(
        name=m.name,
        size_bytes=m.size_bytes,
        vram_bytes=m.vram_bytes,
        expires_at=m.expires_at,
    )


def _map_status(s: OllamaRuntimeStatus) -> OllamaRuntimeStatusResponse:
    return OllamaRuntimeStatusResponse(
        mode=str(s.mode),
        base_url=s.base_url,
        version=s.version,
        docker_available=s.docker_available,
        engine_image_installed=s.engine_image_installed,
        installed_models=s.installed_models,
    )


def _sse(stream: AsyncIterator[str]) -> StreamingResponse:
    """Wrap a `__DONE__`/`__FAILED__`-terminated line stream as SSE.

    Same shape as the LanguageTool / compile installs so the frontend reuses one
    consumer: `event: log` per line, `event: done` with {status} at the end.
    """

    async def _event_stream() -> AsyncIterator[str]:
        done_payload: dict[str, object] = {"status": "success"}
        async for line in stream:
            if line == "__DONE__":
                done_payload["status"] = "success"
                continue
            if line == "__FAILED__":
                done_payload["status"] = "failure"
                continue
            yield f"event: log\ndata: {json.dumps(line, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/ai-runtime/hardware", response_model=HardwareInfoResponse)
async def get_hardware(uc: FromDishka[DetectHardwareUC]) -> HardwareInfoResponse:
    result = await uc.execute()
    return _map_hardware(result.hardware)


@router.get("/ai-runtime/catalog", response_model=ModelCatalogResponse)
async def get_catalog(uc: FromDishka[ListModelCatalogUC]) -> ModelCatalogResponse:
    result = await uc.execute()
    language = current_interface_language()
    return ModelCatalogResponse(
        hardware=_map_hardware(result.hardware),
        models=[_map_model(f, language) for f in result.models],
        allow_custom=settings.ollama.allow_custom_models,
    )


@router.get("/ai-runtime/registry/search", response_model=RegistrySearchResponse)
async def search_registry(q: str, uc: FromDishka[SearchRegistryUC]) -> RegistrySearchResponse:
    """Best-effort discovery: search ollama.com for installable models."""
    result = await uc.execute(SearchRegistryInput(query=q))
    return RegistrySearchResponse(models=[_map_registry(m) for m in result.models])


@router.get("/ai-runtime/status", response_model=OllamaRuntimeStatusResponse)
async def get_runtime_status(uc: FromDishka[GetOllamaStatusUC]) -> OllamaRuntimeStatusResponse:
    result = await uc.execute()
    return _map_status(result.status)


@router.post("/ai-runtime/start", response_model=StartRuntimeResponse)
async def start_runtime(
    uc: FromDishka[StartOllamaRuntimeUC],
    sync_uc: FromDishka[SyncLocalOllamaProviderUC],
) -> StartRuntimeResponse:
    result = await uc.execute()
    await sync_uc.execute()  # keep the managed provider's models/base_url current
    return StartRuntimeResponse(started=result.started, status=_map_status(result.status))


@router.post("/ai-runtime/stop", response_model=StopRuntimeResponse)
async def stop_runtime(uc: FromDishka[StopOllamaRuntimeUC]) -> StopRuntimeResponse:
    result = await uc.execute()
    return StopRuntimeResponse(stopped=result.stopped, detail=result.detail, status=_map_status(result.status))


@router.get("/ai-runtime/engine/install")
async def install_engine(uc: FromDishka[InstallOllamaEngineUC]) -> StreamingResponse:
    """Stream `docker pull ollama/ollama` progress via SSE (GET, like LT install)."""
    stream = await uc.execute()
    return _sse(stream)


@router.post("/ai-runtime/models/pull", response_model=PullJobResponse)
async def start_pull(name: str, uc: FromDishka[StartPullUC]) -> PullJobResponse:
    """Start a BACKGROUND download job for `name` and return its initial state.

    The job runs independently of this request, so closing the UI never stops
    it — the client polls GET /ai-runtime/models/pulls for progress.
    """
    try:
        job = await uc.execute(StartPullInput(name=name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _map_job(job)


@router.get("/ai-runtime/models/pulls", response_model=PullJobsResponse)
async def list_pulls(uc: FromDishka[ListPullsUC]) -> PullJobsResponse:
    result = await uc.execute()
    return PullJobsResponse(jobs=[_map_job(j) for j in result.jobs])


@router.delete("/ai-runtime/models/pulls", status_code=204)
async def dismiss_pull(name: str, uc: FromDishka[DismissPullUC]) -> None:
    await uc.execute(DismissPullInput(name=name))


@router.get("/ai-runtime/models/loaded", response_model=LoadedModelsResponse)
async def list_loaded_models(uc: FromDishka[ListLoadedModelsUC]) -> LoadedModelsResponse:
    """Models currently in memory (Ollama auto-unloads them after keep_alive idle)."""
    result = await uc.execute()
    return LoadedModelsResponse(models=[_map_loaded(m) for m in result.models])


@router.post("/ai-runtime/models/unload", response_model=UnloadModelResponse)
async def unload_model(name: str, uc: FromDishka[UnloadModelUC]) -> UnloadModelResponse:
    """Free a model from memory now, without waiting for the idle window."""
    try:
        result = await uc.execute(UnloadModelInput(name=name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return UnloadModelResponse(unloaded=result.unloaded)


@router.post("/ai-runtime/provider/sync", response_model=SyncProviderResponse)
async def sync_provider(uc: FromDishka[SyncLocalOllamaProviderUC]) -> SyncProviderResponse:
    """Refresh the auto-managed `ollama` provider (call after a pull finishes)."""
    result = await uc.execute()
    return SyncProviderResponse(
        provider_id=str(result.provider_id) if result.provider_id else None,
        models=result.models,
    )


@router.delete("/ai-runtime/models", response_model=DeleteModelResponse)
async def delete_model(
    name: str,
    uc: FromDishka[DeleteOllamaModelUC],
    sync_uc: FromDishka[SyncLocalOllamaProviderUC],
) -> DeleteModelResponse:
    try:
        result = await uc.execute(DeleteOllamaModelInput(name=name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    synced = await sync_uc.execute()
    return DeleteModelResponse(deleted=result.deleted, installed_models=synced.models)
