"""Провайдер identity серверного режима.

Срезы identity регистрируют здесь репозитории пользователей и сессий, цепочку резолверов
актора, почтовик и ограничитель. Подключается лениво, только из ``create_container(server)``.
"""

from __future__ import annotations

from datetime import timedelta

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.identity.protocols import IActorResolver, ISessionRepository, IUserRepository
from hse_doc_studio.core.identity.session_policy import SessionPolicy
from hse_doc_studio.infra.db.repositories.auth import SqlSessionRepository
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver, ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.sessions import SessionService


class ServerIdentityProvider(Provider):
    scope = Scope.APP

    @provide
    def get_user_repository(self, sessions: SessionProvider) -> IUserRepository:
        return SqlUserRepository(sessions)

    @provide
    def get_session_repository(self, sessions: SessionProvider) -> ISessionRepository:
        return SqlSessionRepository(sessions)

    @provide
    def get_session_policy(self) -> SessionPolicy:
        return SessionPolicy(
            idle=timedelta(days=settings.auth.session_idle_days),
            absolute=timedelta(days=settings.auth.session_absolute_days),
        )

    @provide
    def get_session_service(
        self, sessions: ISessionRepository, users: IUserRepository, policy: SessionPolicy
    ) -> SessionService:
        return SessionService(sessions, users, policy)

    @provide
    def get_actor_resolver(self, sessions: SessionService) -> IActorResolver:
        return ChainActorResolver([SessionCookieResolver(sessions), BearerActorResolver()])
