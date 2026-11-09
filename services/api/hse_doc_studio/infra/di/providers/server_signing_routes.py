"""Провайдер маршрутов подписания (серверный режим): хранилище в Postgres.

Локальная Студия маршрутов не хранит (docs/design/signing-route.md, раздел 6.9): порта там нет, сценарии маршрута
подключаются только в `MODE=server`.
"""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository
from hse_doc_studio.infra.db.repositories.signing_routes import SqlSigningRouteRepository
from hse_doc_studio.infra.db.session import SessionProvider


class ServerSigningRoutesProvider(Provider):
    scope = Scope.APP

    @provide
    def get_signing_route_repository(self, sessions: SessionProvider) -> ISigningRouteRepository:
        return SqlSigningRouteRepository(sessions)
