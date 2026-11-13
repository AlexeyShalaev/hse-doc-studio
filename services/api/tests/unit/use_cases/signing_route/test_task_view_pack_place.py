"""Страница подписанта до размещения слота: место из пака для документа (docs/design/signing-route.md, 15.3)."""

from __future__ import annotations

from types import SimpleNamespace

from hse_doc_studio.core.catalog import SignatureDefaultPlacement, SignatureSlotDef
from hse_doc_studio.core.signing_route.entities import DocSlot
from hse_doc_studio.core.value_objects import SignaturePlacement
from hse_doc_studio.use_cases.signing_route.task_view import _placement

_SLOT = SignatureSlotDef(
    id="supervisor",
    label={"ru": "Научный руководитель"},
    applies_to=("proposal", "report"),
    default_placement=SignatureDefaultPlacement(1, 110, 130, 40),
    placements=(("proposal", SignatureDefaultPlacement(1, 80, 139, 40)),),
)
_POINT = SimpleNamespace(
    runtime={"supervisor": SimpleNamespace(slot_def=_SLOT)},
    documents={"proposal": SimpleNamespace(def_id="proposal"), "report": SimpleNamespace(def_id="report")},
)


def test__placement__not_placed_yet__pack_place_of_the_document_else_the_general_one() -> None:
    proposal = _placement(_POINT, {}, DocSlot("proposal", "supervisor"))  # type: ignore[arg-type]
    report = _placement(_POINT, {}, DocSlot("report", "supervisor"))  # type: ignore[arg-type]

    assert (proposal.enabled, proposal.page, proposal.x_mm, proposal.y_mm, proposal.width_mm) == (False, 1, 80, 139, 40)
    assert (report.x_mm, report.y_mm) == (110, 130)


def test__placement__placed__the_stored_place() -> None:
    stored = SignaturePlacement(enabled=True, page=2, x_mm=10, y_mm=20, width_mm=30)

    assert _placement(_POINT, {"proposal": {"supervisor": stored}}, DocSlot("proposal", "supervisor")) is stored  # type: ignore[arg-type]
