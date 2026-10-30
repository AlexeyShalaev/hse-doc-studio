"""`/api/admin`: очередь задач, квоты, здоровье сервисов, место, политика подписи и общие ИИ-провайдеры.

Гард и префикс задаёт `make_admin_router`; не админ получает 404 раньше любого обработчика.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import AwareDatetime

from hse_doc_studio.api.schemas.admin import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Page,
    PageParams,
    PickerPage,
    cursor_param,
    encode_cursor,
    page_params,
    picker_limit,
    picker_page,
    search_param,
    sort_param,
)
from hse_doc_studio.api.schemas.admin_ops import (
    AdminAiProvider,
    AdminAiProviderCheck,
    AdminJob,
    AdminJobPage,
    AdminQueueSummary,
    AdminQuotas,
    AdminServiceHealth,
    AdminSigningPolicy,
    AdminStorageOwner,
    AdminStorageOwnerRow,
    AdminStorageUsage,
    AiProviderTypeName,
    CreateAdminAiProviderRequest,
    JobKindName,
    JobStateName,
    UpdateAdminAiProviderRequest,
    UpdateAdminQuotasRequest,
    UpdateAdminSigningPolicyRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.jobs.admin import JobAdminFilter, JobListing
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass, JobState
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError
from hse_doc_studio.core.jobs.quotas import QuotaSettings, org_key
from hse_doc_studio.core.listing import SortOrder
from hse_doc_studio.core.repositories import INSTANCE_AI_PROVIDER_SORT_FIELDS, InstanceAiProviderQuery
from hse_doc_studio.core.signatures.key_policy import ServerKeyPolicy
from hse_doc_studio.core.storage.usage import (
    STORAGE_OWNER_SORT_FIELDS,
    StorageOwnerKind,
    StorageOwnerQuery,
    StorageUsage,
)
from hse_doc_studio.use_cases.admin.ops_ai_providers import (
    CheckInstanceAiProviderUC,
    CreateInstanceAiProviderUC,
    DeleteInstanceAiProviderUC,
    GetInstanceAiProviderUC,
    InstanceAiProvider,
    InstanceAiProviderInput,
    InstanceAiProviderPatch,
    ListInstanceAiProvidersUC,
    UpdateInstanceAiProviderUC,
)
from hse_doc_studio.use_cases.admin.ops_queue import CancelJobUC, ListQueueUC, PickProjectsUC, QueueSummaryUC
from hse_doc_studio.use_cases.admin.ops_quotas import GetQuotasUC, UpdateQuotasUC
from hse_doc_studio.use_cases.admin.ops_services import ServiceHealth, ServicesOverviewUC
from hse_doc_studio.use_cases.admin.ops_signing import GetSigningPolicyUC, UpdateSigningPolicyUC
from hse_doc_studio.use_cases.admin.ops_storage import GetStorageUsageUC, ListStorageOwnersUC

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}
_OWNER_SORT = sort_param(allowed=STORAGE_OWNER_SORT_FIELDS, default="-projects")
_PROVIDER_SORT = sort_param(allowed=INSTANCE_AI_PROVIDER_SORT_FIELDS, default="created_at")


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def _job(listing: JobListing) -> AdminJob:
    job = listing.job
    return AdminJob(
        id=str(job.id),
        kind=job.kind.value,
        state=job.state.value,
        project_id=str(job.project_id),
        user_id=str(job.user_id),
        org_id=str(job.org_id) if job.org_id else None,
        tags=sorted(job.tags),
        priority_class=JobPriorityClass(job.priority_class).name,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        runner_id=job.runner_id.hex if job.runner_id else None,
        cancel_requested=job.cancel_requested,
        error_code=job.error_code,
        user_name=listing.user_name,
        user_email=listing.user_email,
        org_name=listing.org_name,
        project_name=listing.project_name,
        runner_name=listing.runner_name,
    )


@router.get("/queue", response_model=AdminJobPage)
async def list_queue(
    request: Request,
    response: Response,
    before_seq: Annotated[int | None, Depends(cursor_param)],
    state: Annotated[list[JobStateName] | None, Query()] = None,
    kind: Annotated[list[JobKindName] | None, Query()] = None,
    user_id: Annotated[UUID | None, Query()] = None,
    # Id организации (`org_...`) или её ключ в очереди: оба приводятся к ключу.
    org_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    project_id: Annotated[UUID | None, Query()] = None,
    runner_id: Annotated[UUID | None, Query()] = None,
    queued_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    queued_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> AdminJobPage:
    response.headers.update(_NO_STORE)
    page = await (await _uc(request, ListQueueUC)).execute(
        _actor(),
        JobAdminFilter(
            states=frozenset(JobState(s) for s in state or ()),
            kinds=frozenset(JobKind(k) for k in kind or ()),
            user_id=user_id,
            org_id=org_key(org_id) if org_id else None,
            project_id=project_id,
            runner_id=runner_id,
            queued_from=queued_from,
            queued_to=queued_to,
        ),
        before_seq=before_seq,
        limit=limit,
    )
    return AdminJobPage(
        items=[_job(j) for j in page.items],
        next_cursor=encode_cursor(page.next_before_seq) if page.next_before_seq is not None else None,
        total_estimate=page.total_estimate,
    )


@router.get("/pickers/projects", response_model=PickerPage)
async def pick_projects(
    request: Request,
    response: Response,
    q: Annotated[str | None, Depends(search_param)],
    limit: Annotated[int, Depends(picker_limit)],
) -> PickerPage:
    response.headers.update(_NO_STORE)
    return picker_page(await (await _uc(request, PickProjectsUC)).execute(_actor(), q, limit))


@router.get("/queue/summary", response_model=AdminQueueSummary)
async def queue_summary(request: Request, response: Response) -> AdminQueueSummary:
    response.headers.update(_NO_STORE)
    stats = await (await _uc(request, QueueSummaryUC)).execute(_actor())
    return AdminQueueSummary(
        by_state={state.value: stats.by_state.get(state, 0) for state in JobState},
        queued_by_class={JobPriorityClass(c).name: n for c, n in sorted(stats.queued_by_class.items())},
        oldest_queued_at=stats.oldest_queued_at,
        wait_p50_s=stats.wait_p50_s,
        wait_p95_s=stats.wait_p95_s,
    )


@router.post("/queue/{job_id}/cancel", response_model=AdminJob)
async def cancel_job(job_id: UUID, request: Request, response: Response) -> AdminJob:
    response.headers.update(_NO_STORE)
    try:
        job = await (await _uc(request, CancelJobUC)).execute(_actor(), job_id)
    except QueuedJobNotFoundError as exc:
        raise IdentityError(IdentityErrorCode.not_found) from exc
    return _job(job)


def _quotas(quotas: QuotaSettings) -> AdminQuotas:
    return AdminQuotas(
        user_concurrent=quotas.user_concurrent,
        org_concurrent=quotas.org_concurrent,
        max_duration_s=quotas.max_duration_s,
        on_exhausted="wait",
    )


@router.get("/quotas", response_model=AdminQuotas)
async def get_quotas(request: Request, response: Response) -> AdminQuotas:
    response.headers.update(_NO_STORE)
    return _quotas(await (await _uc(request, GetQuotasUC)).execute(_actor()))


@router.put("/quotas", response_model=AdminQuotas)
async def put_quotas(body: UpdateAdminQuotasRequest, request: Request, response: Response) -> AdminQuotas:
    response.headers.update(_NO_STORE)
    saved = await (await _uc(request, UpdateQuotasUC)).execute(
        _actor(),
        QuotaSettings(
            user_concurrent=body.user_concurrent,
            org_concurrent=body.org_concurrent,
            max_duration_s=body.max_duration_s,
        ),
    )
    return _quotas(saved)


def _service(item: ServiceHealth) -> AdminServiceHealth:
    return AdminServiceHealth(
        id=item.id, state=item.state.value, reason=item.reason, total=item.total, online=item.online
    )


@router.get("/services", response_model=list[AdminServiceHealth])
async def list_services(request: Request, response: Response) -> list[AdminServiceHealth]:
    response.headers.update(_NO_STORE)
    registry = getattr(request.app.state, "health_registry", None)
    probes = await registry.run() if registry is not None else {}
    return [_service(s) for s in await (await _uc(request, ServicesOverviewUC)).execute(_actor(), probes)]


def _storage(usage: StorageUsage) -> AdminStorageUsage:
    return AdminStorageUsage(
        blob_count=usage.blob_count,
        blob_bytes=usage.blob_bytes,
        projects=usage.projects,
        deleted_projects=usage.deleted_projects,
        top_owners=[
            AdminStorageOwner(owner_id=o.owner_id, owner_name=o.owner_name, projects=o.projects)
            for o in usage.top_owners
        ],
        volume_total_bytes=usage.volume_total_bytes,
        volume_free_bytes=usage.volume_free_bytes,
        computed_at=usage.computed_at,
    )


@router.get("/storage", response_model=AdminStorageUsage)
async def get_storage(
    request: Request, response: Response, refresh: Annotated[bool, Query()] = False
) -> AdminStorageUsage:
    response.headers.update(_NO_STORE)
    return _storage(await (await _uc(request, GetStorageUsageUC)).execute(_actor(), refresh=refresh))


@router.get("/storage/owners", response_model=Page[AdminStorageOwnerRow])
async def list_storage_owners(
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortOrder, Depends(_OWNER_SORT)],
    kind: Annotated[list[Literal["user", "org"]] | None, Query()] = None,
) -> Page[AdminStorageOwnerRow]:
    response.headers.update(_NO_STORE)
    page = await (await _uc(request, ListStorageOwnersUC)).execute(
        _actor(),
        StorageOwnerQuery(
            q=q, kinds=frozenset(StorageOwnerKind(k) for k in kind or ()), sort=sort, window=params.window
        ),
    )
    return params.page(
        [
            AdminStorageOwnerRow(
                kind=o.kind.value, id=o.id, name=o.name, email=o.email, projects=o.projects, bytes=o.bytes
            )
            for o in page.items
        ],
        page.total,
    )


@router.get("/settings/signing", response_model=AdminSigningPolicy)
async def get_signing_policy(request: Request, response: Response) -> AdminSigningPolicy:
    response.headers.update(_NO_STORE)
    policy = await (await _uc(request, GetSigningPolicyUC)).execute(_actor())
    return AdminSigningPolicy(server_keys=policy.server_keys.value, stored_keys=policy.stored_keys)


@router.put("/settings/signing", response_model=AdminSigningPolicy)
async def put_signing_policy(
    body: UpdateAdminSigningPolicyRequest, request: Request, response: Response
) -> AdminSigningPolicy:
    response.headers.update(_NO_STORE)
    policy = await (await _uc(request, UpdateSigningPolicyUC)).execute(_actor(), ServerKeyPolicy(body.server_keys))
    return AdminSigningPolicy(server_keys=policy.server_keys.value, stored_keys=policy.stored_keys)


def _provider(provider: InstanceAiProvider) -> AdminAiProvider:
    return AdminAiProvider(
        id=str(provider.id),
        name=provider.name,
        type=provider.type.value,
        base_url=provider.base_url,
        models=list(provider.models),
        key_set=provider.key_set,
        ssl_verify=provider.ssl_verify,
        connect_timeout_s=provider.connect_timeout_s,
        request_timeout_s=provider.request_timeout_s,
        created_at=provider.created_at,
    )


@router.get("/ai-providers", response_model=Page[AdminAiProvider])
async def list_ai_providers(
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortOrder, Depends(_PROVIDER_SORT)],
    provider_type: Annotated[list[AiProviderTypeName] | None, Query(alias="type")] = None,
) -> Page[AdminAiProvider]:
    response.headers.update(_NO_STORE)
    page = await (await _uc(request, ListInstanceAiProvidersUC)).execute(
        _actor(),
        InstanceAiProviderQuery(
            q=q,
            types=frozenset(AIProviderType(t) for t in provider_type or ()),
            sort=sort,
            window=params.window,
        ),
    )
    return params.page([_provider(p) for p in page.items], page.total)


@router.post("/ai-providers", response_model=AdminAiProvider, status_code=status.HTTP_201_CREATED)
async def create_ai_provider(
    body: CreateAdminAiProviderRequest, request: Request, response: Response
) -> AdminAiProvider:
    response.headers.update(_NO_STORE)
    created = await (await _uc(request, CreateInstanceAiProviderUC)).execute(
        _actor(),
        InstanceAiProviderInput(
            name=body.name,
            type=AIProviderType(body.type),
            api_key=body.api_key,
            base_url=body.base_url,
            models=tuple(body.models),
            ssl_verify=body.ssl_verify,
            connect_timeout_s=body.connect_timeout_s,
            request_timeout_s=body.request_timeout_s,
        ),
    )
    return _provider(created)


@router.get("/ai-providers/{provider_id}", response_model=AdminAiProvider)
async def get_ai_provider(provider_id: UUID, request: Request, response: Response) -> AdminAiProvider:
    response.headers.update(_NO_STORE)
    return _provider(await (await _uc(request, GetInstanceAiProviderUC)).execute(_actor(), provider_id))


@router.patch("/ai-providers/{provider_id}", response_model=AdminAiProvider)
async def update_ai_provider(
    provider_id: UUID, body: UpdateAdminAiProviderRequest, request: Request, response: Response
) -> AdminAiProvider:
    response.headers.update(_NO_STORE)
    updated = await (await _uc(request, UpdateInstanceAiProviderUC)).execute(
        _actor(),
        provider_id,
        InstanceAiProviderPatch(
            name=body.name,
            type=AIProviderType(body.type) if body.type else None,
            api_key=body.api_key,
            clear_key=body.clear_key,
            base_url=body.base_url,
            models=tuple(body.models) if body.models is not None else None,
            ssl_verify=body.ssl_verify,
            connect_timeout_s=body.connect_timeout_s,
            request_timeout_s=body.request_timeout_s,
        ),
    )
    return _provider(updated)


@router.delete("/ai-providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_provider(provider_id: UUID, request: Request) -> Response:
    await (await _uc(request, DeleteInstanceAiProviderUC)).execute(_actor(), provider_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ai-providers/{provider_id}/check", response_model=AdminAiProviderCheck)
async def check_ai_provider(provider_id: UUID, request: Request, response: Response) -> AdminAiProviderCheck:
    response.headers.update(_NO_STORE)
    result = await (await _uc(request, CheckInstanceAiProviderUC)).execute(_actor(), provider_id)
    return AdminAiProviderCheck(ok=result.ok, models=list(result.models), error=result.error)
