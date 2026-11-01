"""Цепочка определения актора: локальный запуск, cookie сессии, Bearer с персональным токеном."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.commit_identity import DEFAULT_NOREPLY_DOMAIN, commit_identity
from hse_doc_studio.core.identity.entities import ActorCredentials
from hse_doc_studio.core.identity.normalize import hash_token, is_pat
from hse_doc_studio.core.identity.protocols import IActorResolver, IApiTokenRepository, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.use_cases.identity.sessions import SessionService


class LocalActorResolver:
    """Локальная установка одна и у неё один актор; предъявленные данные не нужны."""

    async def resolve(self, credentials: ActorCredentials) -> Actor | None:  # noqa: ARG002
        return Actor.local()


class SessionCookieResolver:
    """Имя и e-mail актора это подпись его коммитов (см. `commit_identity`), а не данные аккаунта."""

    def __init__(self, sessions: SessionService, noreply_domain: str = DEFAULT_NOREPLY_DOMAIN) -> None:
        self._sessions = sessions
        self._noreply_domain = noreply_domain

    async def resolve(self, credentials: ActorCredentials) -> Actor | None:
        if not credentials.session_secret:
            return None
        resolved = await self._sessions.resolve(credentials.session_secret)
        if resolved is None:
            return None
        user = resolved.user
        author = commit_identity(user, self._noreply_domain)
        return Actor.user(
            user.id,
            author.name,
            author.email,
            is_instance_admin=user.is_instance_admin,
            source=ActorSource.session,
        )


class BearerActorResolver:
    """Персональный токен из `Authorization: Bearer`. Чужие, истёкшие и неизвестные токены, как и токены
    отключённых пользователей, не опознаются: запрос остаётся анонимным и получает 401."""

    def __init__(
        self,
        tokens: IApiTokenRepository,
        users: IUserRepository,
        clock: Clock = utc_now,
        touch_interval: timedelta = timedelta(minutes=5),
        noreply_domain: str = DEFAULT_NOREPLY_DOMAIN,
    ) -> None:
        self._tokens = tokens
        self._users = users
        self._clock = clock
        self._touch_interval = touch_interval
        self._noreply_domain = noreply_domain

    async def resolve(self, credentials: ActorCredentials) -> Actor | None:
        secret = credentials.bearer_token
        if not secret or not is_pat(secret):
            return None
        token = await self._tokens.get_by_hash(hash_token(secret))
        now = self._clock()
        if token is None or (token.expires_at is not None and now >= token.expires_at):
            return None
        user = await self._users.get(token.user_id)
        if user is None or not user.can_sign_in:
            return None
        # Отметку использования пишем не чаще интервала: токен дёргают на каждый запрос CLI.
        if token.last_used_at is None or now - token.last_used_at >= self._touch_interval:
            await self._tokens.touch(token.id, now)
        author = commit_identity(user, self._noreply_domain)
        return Actor.user(
            user.id,
            author.name,
            author.email,
            is_instance_admin=user.is_instance_admin,
            source=ActorSource.pat,
            scopes=frozenset(scope.value for scope in token.scopes),
        )


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
