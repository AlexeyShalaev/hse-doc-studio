"""Состояние входа для клиента: единственный публичный ответ о режиме, первом запуске и пользователе."""

from __future__ import annotations

from dishka.exceptions import NoFactoryError
from fastapi import APIRouter, Request, Response

from hse_doc_studio.api.admin_access import admin_request_allowed
from hse_doc_studio.api.auth_cookie import credentials_from_request
from hse_doc_studio.api.config import ServerConfig, settings
from hse_doc_studio.api.git_remote_capabilities import git_remote_capabilities
from hse_doc_studio.api.invitation_views import inbox_badge
from hse_doc_studio.api.passkey_party import relying_party
from hse_doc_studio.api.routers.v1.share_link_public import guest_bootstrap
from hse_doc_studio.api.schemas.session import (
    AuthOptions,
    BootstrapResponse,
    Capabilities,
    LandingInfo,
    OidcProviderOption,
    SessionUser,
)
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import User
from hse_doc_studio.core.identity.normalize import avatar_initials
from hse_doc_studio.core.identity.passwords import PASSWORD_MIN_LENGTH
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess

router = APIRouter()


def session_user(user: User) -> SessionUser:
    return SessionUser(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar_initials=avatar_initials(user.name, user.email),
        is_instance_admin=user.is_instance_admin,
        email_verified=user.email_verified,
        locale="ru" if user.locale == "ru" else "en" if user.locale == "en" else None,
        # Организации приходят вместе с их хранилищем; до него у человека нет ролей в организациях.
        org_roles=[],
    )


def _local_bootstrap() -> BootstrapResponse:
    return BootstrapResponse(
        mode="local",
        version=settings.get_app_version(),
        setup_state="ready",
        auth=AuthOptions(
            registration_mode="closed",
            password_enabled=False,
            oidc_providers=[],
            smtp_enabled=False,
            password_min_length=PASSWORD_MIN_LENGTH,
        ),
        user=None,
        capabilities=Capabilities(
            fs_browse=True,
            connect_folder=True,
            open_in_editor=True,
            move_project=True,
            docker_ui=True,
            self_update=True,
            local_services_ui=True,
            admin=False,
            personal_signing_keys=False,
            # Студия может собирать облачные проекты хозяина как его личный раннер (только по его включению).
            remote_runner=True,
            **git_remote_capabilities(),
        ),
        csrf_token=None,
    )


async def _pack_studio_allowed(request: Request, actor: Actor) -> bool:
    """Раздел «Студия шаблонов» включён и человеку дано право (template-studio.md, D4)."""
    container = getattr(request.state, "dishka_container", None) or request.app.state.dishka_container
    try:
        access = await container.get(PackStudioAccess)
    except NoFactoryError:
        # Сборка без Студии шаблонов (урезанные контейнеры тестов): раздела нет, вход от этого не ломается.
        return False
    return await access.allowed(actor)


@router.get("/session/bootstrap", response_model=BootstrapResponse)
async def bootstrap(request: Request, response: Response) -> BootstrapResponse:
    # Ответ несёт токен CSRF текущей сессии: кэшировать его нельзя.
    response.headers["Cache-Control"] = "no-store"
    if settings.mode is StudioMode.local:
        local = _local_bootstrap()
        local.capabilities.pack_studio = await _pack_studio_allowed(request, Actor.local())
        return local
    uc = await request.state.dishka_container.get(BootstrapUC)
    result = await uc.execute(credentials_from_request(request).session_secret)
    # С чужого host/IP админки для человека нет, даже если он админ установки
    is_admin = result.user is not None and result.user.is_instance_admin and admin_request_allowed(request)
    caps = ServerConfig.from_settings(settings).caps
    # links: без пользовательской сессии запрос может нести гостевую сессию по ссылке.
    guest, guest_csrf = (None, None) if result.user is not None else await guest_bootstrap(request)
    response_body = BootstrapResponse(
        mode="server",
        version=settings.get_app_version(),
        setup_state=result.setup_state,
        auth=AuthOptions(
            registration_mode=result.auth.registration_mode.value,
            password_enabled=result.auth.password_enabled,
            oidc_providers=[OidcProviderOption(id=pid, label=label) for pid, label in result.oidc_providers],
            smtp_enabled=result.smtp_enabled,
            password_min_length=result.password_min_length,
            passkeys_enabled=result.auth.passkeys_enabled and relying_party(request) is not None,
        ),
        user=session_user(result.user) if result.user else None,
        capabilities=Capabilities(
            fs_browse=caps.fs_browse,
            connect_folder=caps.connect_folder,
            open_in_editor=caps.open_in_editor,
            move_project=caps.move_project,
            docker_ui=caps.docker_ui,
            self_update=caps.self_update,
            local_services_ui=caps.local_services_ui,
            admin=is_admin,
            personal_signing_keys=caps.personal_signing_keys and result.personal_signing_keys,
            # Свои раннеры подключает вошедший человек, пока админ не выключил личные раннеры.
            personal_runners=result.user is not None and result.personal_runners,
            **git_remote_capabilities(),
        ),
        csrf_token=result.session.csrf_token if result.session else guest_csrf,
        guest=guest,
        # invites: счётчик «Входящих» для шапки.
        inbox=await inbox_badge(request, result.user.id if result.user else None),
        landing=LandingInfo(enabled=result.landing_enabled, name=result.instance_name),
    )
    if result.user is not None:
        user_actor = Actor.user(result.user.id, is_instance_admin=result.user.is_instance_admin)
        response_body.capabilities.pack_studio = await _pack_studio_allowed(request, user_actor)
    if guest is not None:
        # Гостю недоступно ничего из возможностей установки.
        response_body.capabilities = Capabilities(**dict.fromkeys(Capabilities.model_fields, False))
    return response_body
