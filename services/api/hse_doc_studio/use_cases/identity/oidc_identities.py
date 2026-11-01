"""Внешние входы аккаунта: список и отвязка. Привязка идёт через OIDC-поток (`oidc_login`)."""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.identity.entities import UserIdentity
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.oidc import IOidcProviderCatalog
from hse_doc_studio.core.identity.protocols import IAuditLog, ICredentialRepository, IUserRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService


@dataclass(frozen=True)
class IdentityView:
    identity: UserIdentity
    # Название провайдера для экрана; None, если провайдер уже удалён или выключен.
    label: str | None


class ListOidcIdentitiesUC:
    def __init__(self, users: IUserRepository, catalog: IOidcProviderCatalog) -> None:
        self._users = users
        self._catalog = catalog

    async def execute(self, user_id: str) -> list[IdentityView]:
        labels = dict(await self._catalog.list_enabled())
        return [IdentityView(i, labels.get(i.provider)) for i in await self._users.list_identities(user_id)]


class UnlinkOidcIdentityUC:
    """Отвязка провайдера. Последний способ войти убрать нельзя: человек остался бы без доступа."""

    def __init__(
        self,
        users: IUserRepository,
        credentials: ICredentialRepository,
        settings: AuthSettingsService,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._settings = settings
        self._audit = audit
        self._uow = uow

    async def execute(self, user_id: str, provider: str) -> None:
        password_enabled = (await self._settings.effective()).password_enabled
        async with self._uow.begin():
            # Блокировка строки пользователя: две параллельные отвязки не оставят аккаунт без входа.
            if await self._users.get_for_update(user_id) is None:
                raise IdentityError(IdentityErrorCode.not_found)
            identities = await self._users.list_identities(user_id)
            if not any(i.provider == provider for i in identities):
                raise IdentityError(IdentityErrorCode.not_found)
            other_providers = any(i.provider != provider for i in identities)
            has_password = password_enabled and await self._credentials.get_hash(user_id) is not None
            if not (other_providers or has_password):
                raise IdentityError(IdentityErrorCode.last_login_method)
            await self._users.delete_identity(user_id, provider)
            await self._audit.record("auth.oidc_unlink", actor_id=user_id, details={"provider": provider})
