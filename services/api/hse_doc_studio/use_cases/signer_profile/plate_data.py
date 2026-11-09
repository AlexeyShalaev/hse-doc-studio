"""Порт открытых данных плашки (`ISignerPlateData`) до сценариев подписанта: заглушка, читающая только `slot.signer`.

Полный источник (сертификат или открытый ключ из профиля подписанта, затем открытая часть его ключа по умолчанию)
подключает срез R6 (docs/design/signing-route.md, раздел 10): там же у маршрута появляются участники и их аккаунты.
"""

from __future__ import annotations

from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo


class SlotSignerPlateData:
    async def plate_for(self, state: SignaturesState, slot_id: str, user_id: str | None) -> SignerInfo | None:
        slot = state.slots.get(slot_id)
        return None if slot is None else slot.signer
