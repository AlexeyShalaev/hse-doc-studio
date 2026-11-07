"""`/api/admin/model-servers`: установка серверов ИИ-моделей (Ollama, vLLM, SGLang) рядом со Студией."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status

from hse_doc_studio.api.schemas.admin_model_servers import (
    CapabilitiesResponse,
    CatalogModelView,
    CatalogResponse,
    EngineAvailabilityView,
    EngineName,
    EstimateRequest,
    EstimateResponse,
    HardwareView,
    InstallRequest,
    LogsResponse,
    ModelServerList,
    ModelServerResponse,
    ModelServerSettingsResponse,
    SaveHfTokenRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.model_servers import Engine
from hse_doc_studio.use_cases.admin.model_servers import (
    Capabilities,
    ModelServersUC,
    ServerView,
)
from hse_doc_studio.use_cases.admin.model_servers import (
    InstallRequest as InstallInput,
)

router = APIRouter(prefix="/model-servers")

_NO_STORE = {"Cache-Control": "no-store"}


async def _uc(request: Request) -> ModelServersUC:
    return await request.state.dishka_container.get(ModelServersUC)


def _server(view: ServerView) -> ModelServerResponse:
    return ModelServerResponse(
        id=view.id,
        engine=view.engine.value,
        model=view.model,
        name=view.name,
        status=view.status.value,
        endpoint=view.endpoint,
        provider_id=view.provider_id,
        image=view.image,
        steps={key: state.value for key, state in view.steps.items()},
        percent=view.percent,
        text=view.text,
        error=view.error,
        target=view.target.value,
        host=view.host,
        exposure=view.exposure.value,
        manageable=view.manageable,
    )


def _capabilities(caps: Capabilities) -> CapabilitiesResponse:
    hw, res = caps.hardware, caps.resources
    return CapabilitiesResponse(
        local_enabled=caps.local_enabled,
        docker_available=caps.docker_available,
        hardware=HardwareView(
            gpu_vendor=hw.gpu_vendor.value,
            gpu_name=hw.gpu_name,
            vram_mb=hw.vram_mb,
            total_ram_mb=hw.total_ram_mb,
            cpu_count=hw.cpu_count,
            docker_gpu_supported=hw.docker_gpu_supported,
            arch=res.arch,
            disk_free_mb=res.disk_free_mb,
        ),
        engines=[
            EngineAvailabilityView(engine=e.engine.value, image=e.image, available=e.available, reasons=list(e.reasons))
            for e in caps.engines
        ],
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities(request: Request, response: Response) -> CapabilitiesResponse:
    response.headers.update(_NO_STORE)
    return _capabilities(await (await _uc(request)).capabilities(require_actor()))


@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(
    request: Request, engine: EngineName, q: Annotated[str, Query(max_length=100)] = ""
) -> CatalogResponse:
    items = await (await _uc(request)).catalog(require_actor(), Engine(engine), q)
    return CatalogResponse(
        items=[CatalogModelView(ref=m.ref, title=m.title, params_b=m.params_b, quant=m.quant) for m in items]
    )


@router.post("/estimate", response_model=EstimateResponse)
async def post_estimate(body: EstimateRequest, request: Request) -> EstimateResponse:
    est = await (await _uc(request)).estimate(require_actor(), Engine(body.engine), body.model.strip(), body.params_b)
    return EstimateResponse(
        fit=est.fit.value,
        params_b=est.params_b,
        weights_mb=est.weights_mb,
        needed_mb=est.needed_mb,
        available_mb=est.available_mb,
        memory_kind="vram" if est.memory_kind == "vram" else "ram",
        disk_ok=est.disk_ok,
        reasons=list(est.reasons),
    )


@router.get("/settings", response_model=ModelServerSettingsResponse)
async def get_settings(request: Request, response: Response) -> ModelServerSettingsResponse:
    response.headers.update(_NO_STORE)
    return ModelServerSettingsResponse(hf_token_set=await (await _uc(request)).hf_token_set(require_actor()))


@router.put("/settings", response_model=ModelServerSettingsResponse)
async def put_settings(body: SaveHfTokenRequest, request: Request, response: Response) -> ModelServerSettingsResponse:
    response.headers.update(_NO_STORE)
    uc = await _uc(request)
    await uc.save_hf_token(require_actor(), body.hf_token)
    return ModelServerSettingsResponse(hf_token_set=True)


@router.delete("/settings", response_model=ModelServerSettingsResponse)
async def delete_settings(request: Request, response: Response) -> ModelServerSettingsResponse:
    response.headers.update(_NO_STORE)
    await (await _uc(request)).clear_hf_token(require_actor())
    return ModelServerSettingsResponse(hf_token_set=False)


@router.get("", response_model=ModelServerList)
async def list_servers(request: Request, response: Response) -> ModelServerList:
    response.headers.update(_NO_STORE)
    views = await (await _uc(request)).list(require_actor())
    return ModelServerList(items=[_server(v) for v in views])


@router.post("", response_model=ModelServerResponse, status_code=status.HTTP_202_ACCEPTED)
async def install(body: InstallRequest, request: Request) -> ModelServerResponse:
    view = await (await _uc(request)).install(
        require_actor(),
        InstallInput(engine=Engine(body.engine), model=body.model, name=body.name, force=body.force),
    )
    return _server(view)


@router.get("/{server_id}", response_model=ModelServerResponse)
async def get_server(server_id: str, request: Request, response: Response) -> ModelServerResponse:
    response.headers.update(_NO_STORE)
    return _server(await (await _uc(request)).get(require_actor(), server_id))


@router.get("/{server_id}/logs", response_model=LogsResponse)
async def get_logs(
    server_id: str, request: Request, response: Response, tail: Annotated[int, Query(ge=1, le=2000)] = 200
) -> LogsResponse:
    response.headers.update(_NO_STORE)
    return LogsResponse(text=await (await _uc(request)).logs(require_actor(), server_id, tail))


@router.post("/{server_id}/start", response_model=ModelServerResponse)
async def start_server(server_id: str, request: Request) -> ModelServerResponse:
    return _server(await (await _uc(request)).start(require_actor(), server_id))


@router.post("/{server_id}/stop", response_model=ModelServerResponse)
async def stop_server(server_id: str, request: Request) -> ModelServerResponse:
    return _server(await (await _uc(request)).stop(require_actor(), server_id))


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_server(server_id: str, request: Request, purge_models: bool = False) -> Response:
    await (await _uc(request)).remove(require_actor(), server_id, purge_models=purge_models)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
