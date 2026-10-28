"""Цепочка определения актора: локальный запуск, cookie сессии, Bearer (персональные токены придут позже)."""

from __future__ import annotations

from collections.abc import Sequence

from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.entities import ActorCredentials
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.use_cases.identity.sessions import SessionService


class LocalActorResolver:
    """Локальная установка одна и у неё один актор; предъявленные данные не нужны."""

    async def resolve(self, credentials: ActorCredentials) -> Actor | None:  # noqa: ARG002
        return Actor.local()


class SessionCookieResolver:
    def __init__(self, sessions: SessionService) -> None:
        self._sessions = sessions

    async def resolve(self, credentials: ActorCredentials) -> Actor | None:
        if not credentials.session_secret:
            return None
        resolved = await self._sessions.resolve(credentials.session_secret)
        if resolved is None:
            return None
        user = resolved.user
        return Actor.user(
            user.id,
            user.name,
            user.email,
            is_instance_admin=user.is_instance_admin,
            source=ActorSource.session,
        )


class BearerActorResolver:
    """Заглушка: персональные токены появятся отдельным срезом, пока Bearer никого не опознаёт."""

    async def resolve(self, credentials: ActorCredentials) -> Actor | None:  # noqa: ARG002
        return None


class ChainActorResolver:
    """Первый способ, опознавший актора, побеждает; аноним даёт None."""

    def __init__(self, resolvers: Sequence[IActorResolver]) -> None:
        self._resolvers = tuple(resolvers)

    async def resolve(self, credentials: ActorCredentials) -> Actor | None:
        for resolver in self._resolvers:
            actor = await resolver.resolve(credentials)
            if actor is not None:
                return actor
        return None
