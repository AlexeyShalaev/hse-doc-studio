"""Мастер первого запуска сервера: администратор, режим регистрации, завершение (серверный режим).

Ручки существуют, пока мастер не завершён; после завершения все отвечают 404. Администратора создаёт
тот, кто знает токен установки (его печатает журнал api), либо он приходит из окружения. Остальные
шаги идут сессией этого администратора.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.auth_cookie import credentials_from_request, is_secure_public_url, set_session_cookie
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.api.observability.health import HealthRegistry
from hse_doc_studio.api.rate_limit import enforce_ip
from hse_doc_studio.api.routers.v1.session import session_user
from hse_doc_studio.api.schemas.session import (
    LoginResponse,
    ServerSetupAdminRequest,
    ServerSetupCheck,
    ServerSetupEnvironment,
    ServerSetupSettingsRequest,
    ServerSetupStatus,
)
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import RegistrationMode
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.rate_limit import AUTH_IP
from hse_doc_studio.use_cases.server_setup.admin import CreateFirstAdminUC
from hse_doc_studio.use_cases.server_setup.settings import ApplyInitialSettingsUC, CompleteSetupUC, InitialSettings
from hse_doc_studio.use_cases.server_setup.state import GetSetupStatusUC, SetupStateService, SetupStatus
from hse_doc_studio.use_cases.server_setup.token import SetupToken

SETUP_TOKEN_HEADER = "X-Setup-Token"  # noqa: S105 — имя заголовка, не секрет
_DAY_S = 24 * 60 * 60

# Проверка окружения для экрана мастера: имя в экране -> имя проверки в /health/ready.
ENVIRONMENT_PROBES = {"database": "database", "storage": "s3", "runner": "runners"}


async def require_setup_open(request: Request) -> None:
    """После завершения мастера его ручек нет."""
    state = await request.state.dishka_container.get(SetupStateService)
    if await state.is_completed():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(prefix="/server-setup", dependencies=[Depends(require_server_mode), Depends(require_setup_open)])


async def _admin_actor(request: Request) -> Actor:
    """Шаги после создания админа выполняет только он сам: аноним получает 401, другой пользователь 403."""
    resolver = await request.state.dishka_container.get(IActorResolver)
    actor = await resolver.resolve(credentials_from_request(request))
    if actor is None or not actor.id:
        raise IdentityError(IdentityErrorCode.auth_required)
    if not actor.is_instance_admin:
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor


def _status_body(result: SetupStatus) -> ServerSetupStatus:
    return ServerSetupStatus(
        state=result.state, token_required=result.token_required, steps_done=list(result.steps_done)
    )


async def _status(request: Request) -> ServerSetupStatus:
    return _status_body(await (await request.state.dishka_container.get(GetSetupStatusUC)).execute())


@router.get("/status", response_model=ServerSetupStatus)
async def setup_status(request: Request, response: Response) -> ServerSetupStatus:
    response.headers["Cache-Control"] = "no-store"
    return await _status(request)


@router.post("/admin", response_model=LoginResponse)
async def create_admin(body: ServerSetupAdminRequest, request: Request, response: Response) -> LoginResponse:
    await enforce_ip(request, AUTH_IP)
    result = await (await request.state.dishka_container.get(CreateFirstAdminUC)).execute(
        body.setup_token,
        body.name,
        body.email,
        body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    set_session_cookie(
        response,
        result.secret,
        secure=is_secure_public_url(settings.auth.public_url),
        max_age_s=settings.auth.session_absolute_days * _DAY_S,
    )
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(user=session_user(result.user), csrf_token=result.session.csrf_token)


@router.get("/environment", response_model=ServerSetupEnvironment)
async def setup_environment(request: Request, response: Response) -> ServerSetupEnvironment:
    """Состояние базы, хранилища и раннеров для экрана мастера.

    Пока админа нет, пускает токен установки (заголовок X-Setup-Token), потом только сессия админа.
    """
    container = request.state.dishka_container
    if "admin" in (await _status(request)).steps_done:
        await _admin_actor(request)
    elif not (await container.get(SetupToken)).verify(request.headers.get(SETUP_TOKEN_HEADER)):
        raise IdentityError(IdentityErrorCode.setup_token_invalid)
    registry: HealthRegistry = getattr(request.app.state, "health_registry", None) or HealthRegistry()
    results = await registry.run(ENVIRONMENT_PROBES.values())
    checks = [
        ServerSetupCheck(
            id=check_id,
            status="not_configured" if probe not in results else "ok" if results[probe] is None else "fail",
            reason=results.get(probe),
        )
        for check_id, probe in ENVIRONMENT_PROBES.items()
    ]
    response.headers["Cache-Control"] = "no-store"
    return ServerSetupEnvironment(checks=checks)


@router.post("/settings", response_model=ServerSetupStatus)
async def apply_settings(body: ServerSetupSettingsRequest, request: Request) -> ServerSetupStatus:
    admin_id = (await _admin_actor(request)).id or ""
    await (await request.state.dishka_container.get(ApplyInitialSettingsUC)).execute(
        admin_id,
        InitialSettings(
            registration_mode=RegistrationMode(body.registration_mode),
            registration_domains=body.registration_domains,
            require_approval=body.require_approval,
            password_enabled=body.password_enabled,
        ),
    )
    return await _status(request)


@router.post("/complete", response_model=ServerSetupStatus)
async def complete(request: Request) -> ServerSetupStatus:
    admin_id = (await _admin_actor(request)).id or ""
    await (await request.state.dishka_container.get(CompleteSetupUC)).execute(admin_id)
    return await _status(request)
