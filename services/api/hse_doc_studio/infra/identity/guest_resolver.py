"""Гостевой актор по cookie `hse_guest`: последнее звено цепочки `ChainActorResolver`."""

from __future__ import annotations

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import ActorCredentials
from hse_doc_studio.use_cases.sharing.open_link import GuestSessionService


class GuestSessionResolver:
    """Гость по ссылке (cookie `hse_guest`). Стоит в конце цепочки: гость существует, только если ни сессия
    пользователя, ни персональный токен не опознаны (S1)."""

    def __init__(self, guests: GuestSessionService) -> None:
        self._guests = guests

    async def resolve(self, credentials: ActorCredentials) -> Actor | None:
        if credentials.bearer_token:
            # Запрос с токеном аутентифицирует токен; неверный токен не превращается в гостя.
            return None
        session = await self._guests.resolve(credentials.guest_secret)
        if session is None:
            return None
        return Actor.guest(session.id, session.name)
