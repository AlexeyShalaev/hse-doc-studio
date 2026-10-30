"""Права сессии редактора: подписанные токены документа и колбэка с повторной проверкой по `decide`.

Локально токенов нет: документ отдаёт обычный маршрут, колбэк проверяют подпись и JWT Document Server.
В серверном режиме Document Server ходит без cookie, поэтому адресам выдаём короткие подписанные токены.
Роль в токене не источник права: при каждом использовании ACL читается заново, так что отозванный
участник теряет возможность сохранять сразу, а не после срока токена.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.entities import Actor, ActorKind, ActorSource
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.office_tokens import (
    OfficeTokenClaims,
    OfficeTokenError,
    OfficeTokenPurpose,
    OfficeTokenSigner,
    new_nonce,
)


@dataclass(frozen=True)
class OfficeSessionTokens:
    document: str
    callback: str
    nonce: str
    role: str


class IOfficeAccess(Protocol):
    @property
    def enforced(self) -> bool:
        """True, когда адреса редактора защищены токенами (серверный режим)."""
        ...

    async def issue(self, project_id: UUID, doc_id: str, path: str) -> OfficeSessionTokens | None:
        """Токены сессии для текущего актора; None, когда токены не нужны."""
        ...

    async def authorize(
        self,
        token: str,
        purpose: OfficeTokenPurpose,
        project_id: UUID,
        doc_id: str | None = None,
        path: str | None = None,
    ) -> Actor:
        """Актор из токена, если подпись верна и права на запись сейчас есть; иначе PermissionError.

        Без doc_id документ не сверяется: файл по адресу скачивают, не зная идентификатора документа.
        """
        ...


def _denied() -> PermissionError:
    return PermissionError(
        localized_error("office-editor: доступ отклонён", "office-editor: access denied"),
    )


class LocalOfficeAccess:
    enforced = False

    async def issue(self, project_id: UUID, doc_id: str, path: str) -> OfficeSessionTokens | None:  # noqa: ARG002
        return None

    async def authorize(
        self,
        token: str,  # noqa: ARG002
        purpose: OfficeTokenPurpose,  # noqa: ARG002
        project_id: UUID,  # noqa: ARG002
        doc_id: str | None = None,  # noqa: ARG002
        path: str | None = None,  # noqa: ARG002
    ) -> Actor:
        return Actor.local()


class ServerOfficeAccess:
    enforced = True

    def __init__(
        self,
        signer: OfficeTokenSigner,
        acl_repo: IProjectAclRepository,
        *,
        ttl_s: int = 43_200,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._signer = signer
        self._acl_repo = acl_repo
        self._ttl = timedelta(seconds=ttl_s)
        self._clock = clock

    async def _role_of(self, actor: Actor, project_id: UUID, path: str) -> str:
        acl = await self._acl_repo.load_for(actor, project_id)
        if decide(actor, Action.FILES_WRITE, acl, path) is not Decision.allow or acl is None:
            raise _denied()
        grant = acl.grant_for(actor)
        if grant is None:
            raise _denied()
        return str(grant.role.value)

    async def issue(self, project_id: UUID, doc_id: str, path: str) -> OfficeSessionTokens | None:
        actor = require_actor()
        actor_id = actor.id
        if actor.kind is not ActorKind.user or actor_id is None:
            raise _denied()
        role = await self._role_of(actor, project_id, path)
        nonce = new_nonce()
        expires_at = self._clock() + self._ttl

        def make(purpose: OfficeTokenPurpose) -> str:
            return self._signer.sign(
                OfficeTokenClaims(purpose, str(project_id), doc_id, path, actor_id, role, nonce, expires_at)
            )

        return OfficeSessionTokens(
            document=make(OfficeTokenPurpose.document),
            callback=make(OfficeTokenPurpose.callback),
            nonce=nonce,
            role=role,
        )

    async def authorize(
        self,
        token: str,
        purpose: OfficeTokenPurpose,
        project_id: UUID,
        doc_id: str | None = None,
        path: str | None = None,
    ) -> Actor:
        try:
            claims = self._signer.verify(
                token, self._clock(), purpose=purpose, project_id=str(project_id), doc_id=doc_id
            )
        except OfficeTokenError:
            raise _denied() from None
        if path is not None and path != claims.path:
            raise _denied()
        actor = Actor.user(claims.actor_id, source=ActorSource.session)
        await self._role_of(actor, project_id, claims.path)
        return actor
