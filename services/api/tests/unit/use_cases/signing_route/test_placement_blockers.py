"""Помеха отправки `placement_off`: слот с видимой меткой без места на странице (docs/design/signing-route.md, 8.1)."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signing_route.entities import DocSlot
from hse_doc_studio.core.signing_route.readiness import Blocker, BlockerCode
from hse_doc_studio.core.value_objects import SignaturePlacement, SignatureSlot, SignaturesState
from hse_doc_studio.use_cases.signing_route.author import _placement_blockers
from hse_doc_studio.use_cases.signing_route.point import RoutePoint

from tests.factories.signing_routes import make_route

PAIR = DocSlot("topic_application", "supervisor")


def _point(*allowed: str) -> RoutePoint:
    """Точка, которой расчёт помехи касается только способами пары (пусто: любой способ)."""
    return cast(RoutePoint, SimpleNamespace(allowed={PAIR: allowed}))


def _state(mode: SignMode | None, *, enabled: bool | None) -> SignaturesState:
    """Слот научрука со способом `mode` (None: слота в состоянии нет); место включено, выключено или не задано."""
    slots = {} if mode is None else {"supervisor": SignatureSlot(None, None, None, sign_mode=mode)}
    placements = (
        {}
        if enabled is None
        else {PAIR.doc_id: {"supervisor": SignaturePlacement(enabled=enabled, page=1, x_mm=10, y_mm=10, width_mm=30)}}
    )
    return SignaturesState(slots=slots, placements=placements)


@pytest.mark.parametrize(
    ("mode", "enabled", "allowed", "blocked"),
    [
        (SignMode.image, False, (), True),
        (SignMode.image, None, (), True),
        (None, None, (), True),
        (SignMode.detached_text, False, (), True),
        (SignMode.image_crypto, False, (), True),
        (SignMode.image, True, (), False),
        (SignMode.detached_text, True, (), False),
        (SignMode.crypto_invisible, False, (), False),
        (SignMode.crypto_invisible, None, ("pades",), False),
        # Способ слота точка не принимает: подписант выберет сам, и картинке или плашке понадобится место.
        (SignMode.crypto_invisible, False, ("image", "detached"), True),
        (SignMode.image, False, ("pades",), False),
    ],
    ids=[
        "image_off",
        "image_unset",
        "no_slot_unset",
        "plate_off",
        "pades_with_image_off",
        "image_placed",
        "plate_placed",
        "invisible_off",
        "invisible_only_unset",
        "signer_will_choose_visible",
        "signer_will_choose_invisible",
    ],
)
def test__placement_blockers__slot_without_place(
    mode: SignMode | None, enabled: bool | None, allowed: tuple[str, ...], blocked: bool
) -> None:
    route = make_route(uuid4())
    supervisor = route.participants[1]

    blockers = _placement_blockers(_point(*allowed), route, _state(mode, enabled=enabled))

    expected = [Blocker(BlockerCode.placement_off, PAIR.doc_id, PAIR.slot_id, supervisor.id)] if blocked else []
    assert [b for b in blockers if b.slot_id == "supervisor"] == expected


def test__placement_blockers__approver_without_slots__nothing() -> None:
    route = make_route(uuid4())
    approver = route.participants[1]
    route = route.with_participant(replace(approver, assignments=()))

    blockers = _placement_blockers(_point(), route, SignaturesState(slots={}, placements={}))

    assert all(b.participant_id != approver.id for b in blockers)
