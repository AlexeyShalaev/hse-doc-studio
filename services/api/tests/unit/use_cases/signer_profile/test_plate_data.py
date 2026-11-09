"""Заглушка порта данных плашки до R6: читает только `slot.signer`, профиль и ключи подписанта не трогает."""

from __future__ import annotations

from hse_doc_studio.core.signatures.ports import ISignerPlateData
from hse_doc_studio.core.value_objects import SignatureSlot, SignaturesState, SignerInfo
from hse_doc_studio.use_cases.signer_profile.plate_data import SlotSignerPlateData

PLATE = SignerInfo(kind="openpgp", owner="Пётр Петров", cert_id="1A2B 3C4D", signer_id="F" * 40)


async def test__plate_for__slot_with_a_signer__that_signer_whoever_asks() -> None:
    state = SignaturesState(slots={"supervisor": SignatureSlot(None, None, None, signer=PLATE)}, placements={})
    port: ISignerPlateData = SlotSignerPlateData()

    assert await port.plate_for(state, "supervisor", "user-1") == PLATE
    assert await port.plate_for(state, "supervisor", None) == PLATE


async def test__plate_for__no_slot_or_no_signer__unknown() -> None:
    state = SignaturesState(slots={"author": SignatureSlot("a.png", 10, 10)}, placements={})

    assert await SlotSignerPlateData().plate_for(state, "author", "user-1") is None
    assert await SlotSignerPlateData().plate_for(state, "supervisor", "user-1") is None
