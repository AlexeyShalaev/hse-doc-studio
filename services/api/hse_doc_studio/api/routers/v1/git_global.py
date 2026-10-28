"""Git-синхронизация вне проекта: доступы (токены и ключи ssh) и состояние шифрования секретов.

Секреты только входят: ни один ответ их не содержит. Ошибки домена (`GitSyncError`) превращаются
в `{detail, code, ...}` общим обработчиком, а не в каждом эндпоинте.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.git_mapping import map_operation, map_probe, map_provider_info, map_token_info
from hse_doc_studio.api.schemas.git_sync import (
    CloneDefaultsResponse,
    CloneRequest,
    CreateCredentialRequest,
    CreatePatCredentialRequest,
    GitCredentialCheckResponse,
    GitCredentialResponse,
    GitCredentialUsage,
    GitHostResponse,
    GitHostSettingsResponse,
    OperationResponse,
    OperationStartedResponse,
    ProbeRequest,
    ProbeResponse,
    SecretsStatusResponse,
    SharedFolderInfo,
    SharedFolderResponse,
    TrustHostRequest,
    UpdateCredentialRequest,
    UpdateGitHostSettingsRequest,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import GitCredentialKind
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.use_cases.git_sync.bundles import BundleScratch, CloneFromBundleInput, CloneFromBundleUC
from hse_doc_studio.use_cases.git_sync.clone_project import CloneProjectInput, CloneProjectUC, GetCloneDefaultsUC
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
from hse_doc_studio.use_cases.git_sync.host_settings import (
    FIELD_CA_PEM,
    FIELD_PINNED_FINGERPRINT,
    FIELD_PROVIDER_OVERRIDE,
    CheckCredentialUC,
    HostSettingsView,
    ListHostSettingsUC,
    UpdateHostSettingsInput,
    UpdateHostSettingsUC,
)
from hse_doc_studio.use_cases.git_sync.hosts import ForgetHostUC, ListHostsUC, TrustHostInput, TrustHostUC
from hse_doc_studio.use_cases.git_sync.operations import CancelOperationUC, GetOperationUC
from hse_doc_studio.use_cases.git_sync.probe_remote import ProbeInput, ProbeRemoteUC
from hse_doc_studio.use_cases.git_sync.shared_folder import DetectSharedFolderInput, DetectSharedFolderUC

router = APIRouter(route_class=SafeDishkaRoute)


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
        expires_at=credential.expires_at,
        used_by=[GitCredentialUsage(project_id=u.project_id, name=u.name) for u in view.used_by],
    )


def _map_host_settings(view: HostSettingsView) -> GitHostSettingsResponse:
    settings = view.settings
    return GitHostSettingsResponse(
        host=settings.host,
        port=settings.port,
        provider_override=None if settings.provider_override is None else settings.provider_override.value,
        provider_info=map_provider_info(view.provider),
        ca_present=settings.ca_pem is not None,
        pinned_fingerprint=settings.pinned_fingerprint,
    )


@router.get("/git/credentials", response_model=list[GitCredentialResponse])
async def list_git_credentials(uc: FromDishka[ListCredentialsUC]) -> list[GitCredentialResponse]:
    return [_map_credential(view) for view in await uc.execute()]


@router.post("/git/credentials", response_model=GitCredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_git_credential(
    body: CreateCredentialRequest, uc: FromDishka[CreateCredentialUC], policy: FromDishka[GitSyncPolicy]
) -> GitCredentialResponse:
    # Без синхронизации токены и ключи копить негде и незачем: ни запись, ни файл ключа шифрования не появляются.
    policy.require_enabled()
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
    credential_id: UUID,
    body: UpdateCredentialRequest,
    uc: FromDishka[UpdateCredentialUC],
    policy: FromDishka[GitSyncPolicy],
) -> GitCredentialResponse:
    policy.require_enabled()
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


@router.post("/git/credentials/{credential_id}/check", response_model=GitCredentialCheckResponse)
async def check_git_credential(
    credential_id: UUID, uc: FromDishka[CheckCredentialUC], policy: FromDishka[GitSyncPolicy]
) -> GitCredentialCheckResponse:
    policy.require_enabled()
    try:
        view = await uc.execute(credential_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GitCredentialCheckResponse(
        credential=_map_credential(view.credential),
        provider_info=map_provider_info(view.provider),
        token_info=map_token_info(view.token.info if view.token else None),
    )


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
        data_dir_shared_folder=None
        if result.data_dir_shared_folder is None
        else SharedFolderInfo(
            provider=result.data_dir_shared_folder.provider.value, root=result.data_dir_shared_folder.root
        ),
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
async def trust_git_host(
    body: TrustHostRequest, uc: FromDishka[TrustHostUC], policy: FromDishka[GitSyncPolicy]
) -> None:
    policy.require_enabled()
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


@router.get("/git/host-settings", response_model=list[GitHostSettingsResponse])
async def list_git_host_settings(uc: FromDishka[ListHostSettingsUC]) -> list[GitHostSettingsResponse]:
    return [_map_host_settings(view) for view in await uc.execute()]


@router.put("/git/host-settings", response_model=GitHostSettingsResponse)
async def update_git_host_settings(
    body: UpdateGitHostSettingsRequest, uc: FromDishka[UpdateHostSettingsUC], policy: FromDishka[GitSyncPolicy]
) -> GitHostSettingsResponse:
    policy.require_enabled()
    given = body.model_fields_set & {FIELD_PROVIDER_OVERRIDE, FIELD_CA_PEM, FIELD_PINNED_FINGERPRINT}
    view = await uc.execute(
        UpdateHostSettingsInput(
            host=body.host,
            port=body.port,
            provider_override=body.provider_override,
            ca_pem=body.ca_pem,
            pinned_fingerprint=body.pinned_fingerprint,
            given=frozenset(given),
        )
    )
    return _map_host_settings(view)


@router.post("/git/remote/probe", response_model=ProbeResponse)
async def probe_git_remote(body: ProbeRequest, uc: FromDishka[ProbeRemoteUC]) -> ProbeResponse:
    try:
        view = await uc.execute(
            ProbeInput(
                url=body.url,
                credential_id=body.credential_id,
                project_id=body.project_id,
                branch=body.branch,
                insecure_http=bool(body.insecure_http),
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return map_probe(view)


@router.post("/git/clone", response_model=OperationStartedResponse, status_code=status.HTTP_202_ACCEPTED)
async def clone_git_project(body: CloneRequest, uc: FromDishka[CloneProjectUC]) -> OperationStartedResponse:
    try:
        operation = await uc.execute(
            CloneProjectInput(
                url=body.url,
                folder=body.folder,
                credential_id=body.credential_id,
                branch=body.branch,
                name=body.name,
                insecure_http=bool(body.insecure_http),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OperationStartedResponse(operation_id=operation.id)


@router.post("/git/clone/bundle", response_model=OperationStartedResponse, status_code=status.HTTP_202_ACCEPTED)
async def clone_git_project_from_bundle(
    uc: FromDishka[CloneFromBundleUC],
    scratch: FromDishka[BundleScratch],
    file: UploadFile = File(...),
    folder: str = Form(...),
    password: str | None = Form(default=None),
) -> OperationStartedResponse:
    """Новый проект из файла bundle: те же шаги, что у клонирования, но объекты берутся из файла.

    Проект зовётся так, как записан в файле: поле `name` клиента нужно только для предложения папки.
    """
    stored = await scratch.receive(file.read)
    try:
        operation = await uc.execute(
            CloneFromBundleInput(upload=stored, folder=folder, password=Secret(password) if password else None)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OperationStartedResponse(operation_id=operation.id)


@router.get("/git/clone/defaults", response_model=CloneDefaultsResponse)
async def get_git_clone_defaults(
    uc: FromDishka[GetCloneDefaultsUC],
    paths: FromDishka[PathMapping],
    name: str | None = Query(default=None, max_length=256),
) -> CloneDefaultsResponse:
    """Свободная папка под клон, в терминах хозяина машины: как её видит пользователь."""
    return CloneDefaultsResponse(folder=paths.display(str(await uc.execute(name))))


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


@router.get("/git/shared-folder", response_model=SharedFolderResponse)
async def get_shared_folder(
    uc: FromDishka[DetectSharedFolderUC],
    paths: FromDishka[PathMapping],
    folder: str = Query(..., min_length=1, max_length=4096),
) -> SharedFolderResponse:
    """Лежит ли папка в каталоге, который синхронизирует служба: только предупреждение."""
    if "\0" in folder:
        raise HTTPException(status_code=400, detail="invalid folder")
    info = await uc.execute(DetectSharedFolderInput(folder=Path(paths.accept(folder))))
    if info is None:
        return SharedFolderResponse(detected=False, provider=None, root=None, evidence=[])
    return SharedFolderResponse(
        detected=True, provider=info.provider.value, root=info.root, evidence=list(info.evidence)
    )
