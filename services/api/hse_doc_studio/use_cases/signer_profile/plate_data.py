"""Открытые данные плашки слота, известные о его подписанте (`ISignerPlateData`, signing-route.md, 4.2 и 6.5).

- `SlotSignerPlateData`: только `slot.signer` из состояния подписей. Так работает локальная Студия: человек там
  один, профилей подписантов нет, плашку он задаёт сам.
- `ProfileSignerPlateData`: `slot.signer`, а если его нет, сертификат или открытый ключ из профиля подписанта
  (срез R10). Так работает сервер: маршрут знает плашку участника до его шага и заполняет её перед фиксацией.

Закрытые ключи никто не читает. Открытая часть ключа Студии другого человека сюда не попадает: ключи видит только их
владелец, поэтому он сам кладёт её в плашку на своём шаге (`task/plate` или «Согласовать и подписать»).
"""

from __future__ import annotations

from hse_doc_studio.core.signatures.signer_profile import ISignerProfileRepository
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo


class SlotSignerPlateData:
    async def plate_for(self, state: SignaturesState, slot_id: str, user_id: str | None) -> SignerInfo | None:
        slot = state.slots.get(slot_id)
        return None if slot is None else slot.signer


class ProfileSignerPlateData:
    def __init__(self, profiles: ISignerProfileRepository) -> None:
        self._profiles = profiles

    async def plate_for(self, state: SignaturesState, slot_id: str, user_id: str | None) -> SignerInfo | None:
        slot = state.slots.get(slot_id)
        if slot is not None and slot.signer is not None:
            return slot.signer
        if user_id is None:
            return None
        key = (await self._profiles.get(user_id)).public_key
        return key.plate if key is not None else None
