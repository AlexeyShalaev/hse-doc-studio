"""Git-синхронизация вне проекта: доступы (токены и ключи ssh) и состояние шифрования секретов.

Секреты только входят: ни один ответ их не содержит. Ошибки домена (`GitSyncError`) превращаются
в `{detail, code, ...}` общим обработчиком, а не в каждом эндпоинте.
"""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query, status

from hse_doc_studio.api.git_mapping import map_operation, map_probe
from hse_doc_studio.api.schemas.git_sync import (
    CreateCredentialRequest,
    CreatePatCredentialRequest,
    GitCredentialResponse,
    GitCredentialUsage,
    GitHostResponse,
    OperationResponse,
    ProbeRequest,
    ProbeResponse,
    SecretsStatusResponse,
    TrustHostRequest,
    UpdateCredentialRequest,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import GitCredentialKind
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.use_cases.git_sync.credentials import (
    CreateCredentialInput,
    CreateCredentialUC,
    CredentialView,
    DeleteCredentialInput,
    DeleteCredentialUC,
    GetSecretsStatusUC,
    ListCredentialsUC,
    UpdateCredentialInput,
    UpdateCredentialUC,
)
from hse_doc_studio.use_cases.git_sync.hosts import ForgetHostUC, ListHostsUC, TrustHostInput, TrustHostUC
from hse_doc_studio.use_cases.git_sync.operations import CancelOperationUC, GetOperationUC
from hse_doc_studio.use_cases.git_sync.probe_remote import ProbeInput, ProbeRemoteUC

router = APIRouter(route_class=DishkaRoute)


def _map_credential(view: CredentialView) -> GitCredentialResponse:
    credential = view.credential
    return GitCredentialResponse(
        id=credential.id,
        kind=credential.kind.value,
        label=credential.label,
        host=credential.host,
        username=credential.username,
        status=credential.status.value,
        token_family=credential.token_family,
        public_key=credential.public_key,
        fingerprint_sha256=credential.fingerprint_sha256,
        created_at=credential.created_at,
        last_used_at=credential.last_used_at,
        used_by=[GitCredentialUsage(project_id=u.project_id, name=u.name) for u in view.used_by],
    )


@router.get("/git/credentials", response_model=list[GitCredentialResponse])
async def list_git_credentials(uc: FromDishka[ListCredentialsUC]) -> list[GitCredentialResponse]:
    return [_map_credential(view) for view in await uc.execute()]


@router.post("/git/credentials", response_model=GitCredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_git_credential(
    body: CreateCredentialRequest, uc: FromDishka[CreateCredentialUC]
) -> GitCredentialResponse:
    if isinstance(body, CreatePatCredentialRequest):
        inp = CreateCredentialInput(
            kind=GitCredentialKind.pat,
            label=body.label,
            host=body.host,
            username=body.username,
            token=Secret(body.token),
        )
    else:
        inp = CreateCredentialInput(kind=GitCredentialKind.ssh_key, label=body.label, host=body.host, port=body.port)
    return _map_credential(await uc.execute(inp))


@router.patch("/git/credentials/{credential_id}", response_model=GitCredentialResponse)
async def update_git_credential(
    credential_id: UUID, body: UpdateCredentialRequest, uc: FromDishka[UpdateCredentialUC]
) -> GitCredentialResponse:
    try:
        view = await uc.execute(
            UpdateCredentialInput(
                credential_id=credential_id,
                label=body.label,
                username=body.username,
                token=None if body.token is None else Secret(body.token),
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _map_credential(view)


@router.delete("/git/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_git_credential(credential_id: UUID, uc: FromDishka[DeleteCredentialUC], force: bool = False) -> None:
    try:
        await uc.execute(DeleteCredentialInput(credential_id=credential_id, force=force))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/git/secrets/status", response_model=SecretsStatusResponse)
async def get_git_secrets_status(uc: FromDishka[GetSecretsStatusUC]) -> SecretsStatusResponse:
    result = await uc.execute()
    return SecretsStatusResponse(
        ok=result.ok,
        source=result.source.value,
        permissions_enforced=result.permissions_enforced,
        credentials_total=result.credentials_total,
        credentials_unreadable=result.credentials_unreadable,
        # Предупреждение об общей папке (Яндекс.Диск, Dropbox) дописывает срез с детектором общих папок.
        data_dir_shared_folder=None,
    )


@router.get("/git/hosts", response_model=list[GitHostResponse])
async def list_git_hosts(uc: FromDishka[ListHostsUC]) -> list[GitHostResponse]:
    return [
        GitHostResponse(
            host=host.host,
            port=host.port,
            key_types=list(host.key_types),
            fingerprints_sha256=list(host.fingerprints_sha256),
            added_at=host.added_at,
        )
        for host in await uc.execute()
    ]


@router.post("/git/hosts/trust", status_code=status.HTTP_204_NO_CONTENT)
async def trust_git_host(body: TrustHostRequest, uc: FromDishka[TrustHostUC]) -> None:
    await uc.execute(
        TrustHostInput(
            host=body.host,
            port=body.port,
            fingerprint_sha256=body.fingerprint_sha256,
            replace=bool(body.replace),
            confirm_host=body.confirm_host,
        )
    )


@router.delete("/git/hosts", status_code=status.HTTP_204_NO_CONTENT)
async def forget_git_host(uc: FromDishka[ForgetHostUC], host: str = Query(...), port: int | None = None) -> None:
    await uc.execute(host, port)


@router.post("/git/remote/probe", response_model=ProbeResponse)
async def probe_git_remote(body: ProbeRequest, uc: FromDishka[ProbeRemoteUC]) -> ProbeResponse:
    try:
        view = await uc.execute(
            ProbeInput(url=body.url, credential_id=body.credential_id, project_id=body.project_id, branch=body.branch)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return map_probe(view)


@router.get("/git/operations/{operation_id}", response_model=OperationResponse)
async def get_git_operation(operation_id: str, uc: FromDishka[GetOperationUC]) -> OperationResponse:
    try:
        return map_operation(await uc.execute(operation_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/git/operations/{operation_id}/cancel", response_model=OperationResponse)
async def cancel_git_operation(operation_id: str, uc: FromDishka[CancelOperationUC]) -> OperationResponse:
    try:
        return map_operation(await uc.execute(operation_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
