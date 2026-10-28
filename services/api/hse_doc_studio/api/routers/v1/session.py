"""Состояние входа для клиента: единственный публичный ответ о режиме, первом запуске и пользователе."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from hse_doc_studio.api.auth_cookie import credentials_from_request
from hse_doc_studio.api.config import ServerConfig, settings
from hse_doc_studio.api.schemas.session import (
    AuthOptions,
    BootstrapResponse,
    Capabilities,
    SessionUser,
)
from hse_doc_studio.core.identity.entities import User
from hse_doc_studio.core.identity.normalize import avatar_initials
from hse_doc_studio.core.identity.passwords import PASSWORD_MIN_LENGTH
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC

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
        ),
        csrf_token=None,
    )


@router.get("/session/bootstrap", response_model=BootstrapResponse)
async def bootstrap(request: Request, response: Response) -> BootstrapResponse:
    # Ответ несёт токен CSRF текущей сессии: кэшировать его нельзя.
    response.headers["Cache-Control"] = "no-store"
    if settings.mode is StudioMode.local:
        return _local_bootstrap()
    uc = await request.state.dishka_container.get(BootstrapUC)
    result = await uc.execute(credentials_from_request(request).session_secret)
    is_admin = result.user is not None and result.user.is_instance_admin
    caps = ServerConfig.from_settings(settings).caps
    return BootstrapResponse(
        mode="server",
        version=settings.get_app_version(),
        setup_state=result.setup_state,
        auth=AuthOptions(
            registration_mode=result.auth.registration_mode.value,
            password_enabled=result.auth.password_enabled,
            # Провайдеры OIDC подключит их срез.
            oidc_providers=[],
            smtp_enabled=result.smtp_enabled,
            password_min_length=result.password_min_length,
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
            personal_signing_keys=caps.personal_signing_keys,
        ),
        csrf_token=result.session.csrf_token if result.session else None,
    )
