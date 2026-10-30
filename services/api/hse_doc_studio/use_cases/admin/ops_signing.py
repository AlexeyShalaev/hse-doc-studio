"""Политика серверных ключей подписи: разрешены ли ключи, которые хранит сервер."""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.signatures.key_policy import (
    KEY_SERVER_KEYS,
    IServerKeyCounter,
    ServerKeyPolicy,
    server_key_policy_from,
)
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import SOURCE_ADMIN


@dataclass(frozen=True)
class SigningPolicy:
    server_keys: ServerKeyPolicy
    stored_keys: int


class GetSigningPolicyUC:
    def __init__(self, repo: IInstanceSettingsRepository, counter: IServerKeyCounter) -> None:
        self._repo = repo
        self._counter = counter

    async def execute(self, actor: Actor) -> SigningPolicy:
        require_admin(actor)
        return SigningPolicy(
            server_key_policy_from(await self._repo.get_all()), await self._counter.count_server_keys()
        )


class UpdateSigningPolicyUC:
    def __init__(
        self, repo: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork, counter: IServerKeyCounter
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._uow = uow
        self._counter = counter

    async def execute(self, actor: Actor, policy: ServerKeyPolicy) -> SigningPolicy:
        """Запрет не удаляет уже сохранённые ключи, он только закрывает их использование."""
        admin_id = require_admin(actor)
        before = server_key_policy_from(await self._repo.get_all())
        async with self._uow.begin():
            await self._repo.set(KEY_SERVER_KEYS, policy.value, source=SOURCE_ADMIN)
            if policy is not before:
                await self._audit.record(
                    "settings.signing_policy_update",
                    actor_id=admin_id,
                    details={"before": before.value, "after": policy.value},
                )
        return SigningPolicy(policy, await self._counter.count_server_keys())
