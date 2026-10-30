"""`/api/admin`: настройки установки (регистрация, способы входа, SMTP) и провайдеры единого входа.

Секреты (пароль SMTP, секрет клиента OIDC) принимаются на запись и не возвращаются никогда.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from hse_doc_studio.api.schemas.session import (
    AdminAuthSettings,
    AdminOidcProvider,
    AdminRegistrationSettings,
    AdminRetentionSettings,
    AdminSmtpSettings,
    AdminSmtpTestRequest,
    AdminSmtpTestResult,
    CreateAdminOidcProviderRequest,
    SettingState,
    UpdateAdminAuthRequest,
    UpdateAdminOidcProviderRequest,
    UpdateAdminRegistrationRequest,
    UpdateAdminSmtpRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import OidcProvider, RegistrationMode
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.setting_source import SettingDescription
from hse_doc_studio.use_cases.admin.lifecycle import GetRetentionUC
from hse_doc_studio.use_cases.admin.oidc import (
    CreateOidcProviderUC,
    DeleteOidcProviderUC,
    GetOidcProviderUC,
    ListOidcProvidersUC,
    OidcProviderInput,
    OidcProviderPatch,
    UpdateOidcProviderUC,
)
from hse_doc_studio.use_cases.admin.settings import (
    GetAuthGroupUC,
    SettingsGroupView,
    UpdateAuthMethodsUC,
    UpdateRegistrationUC,
)
from hse_doc_studio.use_cases.identity.smtp_settings import (
    GetSmtpSettingsUC,
    SendTestMailUC,
    SmtpPatch,
    SmtpSettingsView,
    UpdateSmtpSettingsUC,
)

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def _fields(descriptions: dict[str, SettingDescription]) -> dict[str, SettingState]:
    return {key: SettingState(source=d.source.value, locked=d.locked) for key, d in descriptions.items()}


def _registration(view: SettingsGroupView) -> AdminRegistrationSettings:
    return AdminRegistrationSettings(
        registration_mode=view.settings.registration_mode.value,
        registration_domains=list(view.settings.registration_domains),
        require_approval=view.settings.require_approval,
        fields=_fields(view.descriptions),
    )


def _auth(view: SettingsGroupView) -> AdminAuthSettings:
    return AdminAuthSettings(
        password_enabled=view.settings.password_enabled,
        oidc_enabled_count=view.enabled_providers,
        fields=_fields(view.descriptions),
    )


def _smtp(view: SmtpSettingsView) -> AdminSmtpSettings:
    config = view.config
    return AdminSmtpSettings(
        enabled=config.enabled,
        host=config.host,
        port=config.port,
        security=config.security,
        username=config.username,
        password_set=config.password_set,
        from_address=config.from_address,
        from_name=config.from_name,
        fields=_fields(view.descriptions),
    )


def _provider(provider: OidcProvider) -> AdminOidcProvider:
    return AdminOidcProvider(
        id=provider.id,
        label=provider.label,
        issuer=provider.issuer,
        client_id=provider.client_id,
        client_secret_set=bool(provider.client_secret_enc),
        scopes=provider.scopes,
        enabled=provider.enabled,
        auto_provision=provider.auto_provision,
        created_at=provider.created_at,
    )


@router.get("/settings/retention", response_model=AdminRetentionSettings)
async def get_retention(request: Request, response: Response) -> AdminRetentionSettings:
    response.headers.update(_NO_STORE)
    policy = await (await _uc(request, GetRetentionUC)).execute(_actor())
    return AdminRetentionSettings(
        audit_days=policy.audit_days,
        deleted_projects_days=policy.deleted_projects_days,
        unused_blobs_days=policy.unused_blobs_days,
    )


@router.get("/settings/registration", response_model=AdminRegistrationSettings)
async def get_registration(request: Request, response: Response) -> AdminRegistrationSettings:
    response.headers.update(_NO_STORE)
    return _registration(await (await _uc(request, GetAuthGroupUC)).registration(_actor()))


@router.put("/settings/registration", response_model=AdminRegistrationSettings)
async def put_registration(
    body: UpdateAdminRegistrationRequest, request: Request, response: Response
) -> AdminRegistrationSettings:
    response.headers.update(_NO_STORE)
    view = await (await _uc(request, UpdateRegistrationUC)).execute(
        _actor(),
        mode=RegistrationMode(body.registration_mode) if body.registration_mode else None,
        domains=body.registration_domains,
        require_approval=body.require_approval,
    )
    return _registration(view)


@router.get("/settings/auth", response_model=AdminAuthSettings)
async def get_auth(request: Request, response: Response) -> AdminAuthSettings:
    response.headers.update(_NO_STORE)
    return _auth(await (await _uc(request, GetAuthGroupUC)).methods(_actor()))


@router.put("/settings/auth", response_model=AdminAuthSettings)
async def put_auth(body: UpdateAdminAuthRequest, request: Request, response: Response) -> AdminAuthSettings:
    response.headers.update(_NO_STORE)
    view = await (await _uc(request, UpdateAuthMethodsUC)).execute(_actor(), password_enabled=body.password_enabled)
    return _auth(view)


@router.get("/settings/smtp", response_model=AdminSmtpSettings)
async def get_smtp(request: Request, response: Response) -> AdminSmtpSettings:
    response.headers.update(_NO_STORE)
    return _smtp(await (await _uc(request, GetSmtpSettingsUC)).execute(_actor()))


@router.put("/settings/smtp", response_model=AdminSmtpSettings)
async def put_smtp(body: UpdateAdminSmtpRequest, request: Request, response: Response) -> AdminSmtpSettings:
    response.headers.update(_NO_STORE)
    view = await (await _uc(request, UpdateSmtpSettingsUC)).execute(_actor(), SmtpPatch(**body.model_dump()))
    return _smtp(view)


@router.post("/settings/smtp/test", response_model=AdminSmtpTestResult)
async def post_smtp_test(body: AdminSmtpTestRequest, request: Request, response: Response) -> AdminSmtpTestResult:
    response.headers.update(_NO_STORE)
    result = await (await _uc(request, SendTestMailUC)).execute(_actor(), body.to)
    return AdminSmtpTestResult(ok=result.ok, error=result.error)


@router.get("/oidc-providers", response_model=list[AdminOidcProvider])
async def list_oidc_providers(request: Request, response: Response) -> list[AdminOidcProvider]:
    response.headers.update(_NO_STORE)
    return [_provider(p) for p in await (await _uc(request, ListOidcProvidersUC)).execute(_actor())]


@router.post("/oidc-providers", response_model=AdminOidcProvider, status_code=status.HTTP_201_CREATED)
async def create_oidc_provider(
    body: CreateAdminOidcProviderRequest, request: Request, response: Response
) -> AdminOidcProvider:
    response.headers.update(_NO_STORE)
    created = await (await _uc(request, CreateOidcProviderUC)).execute(_actor(), OidcProviderInput(**body.model_dump()))
    return _provider(created)


@router.get("/oidc-providers/{provider_id}", response_model=AdminOidcProvider)
async def get_oidc_provider(provider_id: str, request: Request, response: Response) -> AdminOidcProvider:
    response.headers.update(_NO_STORE)
    return _provider(await (await _uc(request, GetOidcProviderUC)).execute(_actor(), provider_id))


@router.patch("/oidc-providers/{provider_id}", response_model=AdminOidcProvider)
async def update_oidc_provider(
    provider_id: str, body: UpdateAdminOidcProviderRequest, request: Request, response: Response
) -> AdminOidcProvider:
    response.headers.update(_NO_STORE)
    updated = await (await _uc(request, UpdateOidcProviderUC)).execute(
        _actor(), provider_id, OidcProviderPatch(**body.model_dump())
    )
    return _provider(updated)


@router.delete("/oidc-providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_oidc_provider(provider_id: str, request: Request) -> Response:
    await (await _uc(request, DeleteOidcProviderUC)).execute(_actor(), provider_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
