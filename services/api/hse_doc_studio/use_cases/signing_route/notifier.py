"""Уведомления маршрута до среза R8: реализация `ISigningNotifier` без доставки.

Сценарии вызывают порт в своей транзакции так же, как будут с R8; запросы участникам при этом отмечаются
(`mark_notified`), поэтому R8 заменяет только эту реализацию.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.entities import SigningRoute


class SilentSigningNotifier:
    async def notify(
        self,
        route: SigningRoute,
        notices: Sequence[Notify],
        *,
        actor_id: UUID | None,
        comment: str | None = None,
    ) -> None:
        return None
