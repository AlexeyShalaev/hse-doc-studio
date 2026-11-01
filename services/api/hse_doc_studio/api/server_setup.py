"""Запуск серверной части мастера первого запуска: админ из окружения, токен установки, шлюз 503."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.config.auth import AuthConfig
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.use_cases.server_setup.admin import EnsureBootstrapAdminUC
from hse_doc_studio.use_cases.server_setup.state import SetupStateService
from hse_doc_studio.use_cases.server_setup.token import SetupToken

if TYPE_CHECKING:
    from dishka import AsyncContainer
    from fastapi import FastAPI

    from hse_doc_studio.api.observability.health import HealthRegistry

logger = structlog.get_logger(__name__)


def bootstrap_admin_password(cfg: AuthConfig) -> str | None:
    """Пароль админа из окружения: значение или файл (docker secret); пустой считается незаданным."""
    if cfg.admin_password is not None:
        return cfg.admin_password.get_secret_value() or None
    if cfg.admin_password_file is not None:
        return cfg.admin_password_file.read_text(encoding="utf-8").strip() or None
    return None


async def prepare_server_setup(
    app: FastAPI, container: AsyncContainer, cfg: Settings, health: HealthRegistry | None = None
) -> None:
    """Вызывается на старте приложения после миграций: включает шлюз `setup_required` и готовит первого админа.

    Админ из окружения создаётся идемпотентно. Иначе, если нужен токен установки, он печатается в журнал:
    пароль и токен больше нигде не показываются.
    """
    state = await container.get(SetupStateService)
    token = await container.get(SetupToken)
    app.state.setup_gate = state
    if health is not None:
        app.state.health_registry = health
    email, password = cfg.auth.admin_email, bootstrap_admin_password(cfg.auth)
    if bool(email) != bool(password):
        logger.warning("HSE_STUDIO__AUTH__ADMIN_EMAIL and the admin password must be set together, both are ignored")
    if email and password:
        try:
            result = await (await container.get(EnsureBootstrapAdminUC)).execute(
                email, password, cfg.auth.admin_name or ""
            )
        except IdentityError as error:
            # Текст ошибки не содержит пароль; запуск с заведомо негодным паролем не маскируем.
            msg = f"администратор из окружения не создан: {error.code.value}"
            raise RuntimeError(msg) from error
        logger.info("first admin from environment", email=email, outcome=result.outcome)
        token.revoke()
    elif await (await container.get(IUserRepository)).count() > 0:
        token.revoke()
    elif token.required:
        logger.warning("first-run setup token: enter it in the setup wizard", setup_token=token.value)
