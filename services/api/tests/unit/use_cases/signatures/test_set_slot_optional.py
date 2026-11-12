"""Проверки отметки «Подпись необязательна» без сервера (docs/design/signing-route.md, 13.3 и 13.6)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.core.catalog import (
    PackSubmissionConfig,
    SignatureDefaultPlacement,
    SignaturesConfig,
    SignatureSlotDef,
    SubmissionDocItem,
    SubmissionProfile,
    TemplateVersion,
)
from hse_doc_studio.core.services import SignatureSlotService
from hse_doc_studio.core.signing_route.entities import DocSlot, RouteConflictError, RouteInputError
from hse_doc_studio.core.signing_route.ports import HeldRoute
from hse_doc_studio.core.value_objects import SignaturesState, SkippedSlot
from hse_doc_studio.infra.template.yaml_template_repository import _parse_signature_slot
from hse_doc_studio.use_cases.signatures.set_slot_optional import SetSlotOptionalInput, SetSlotOptionalUC

from tests.factories import make_document, make_project, make_template_version

_PLACE = SignatureDefaultPlacement(page=1, x_mm=10, y_mm=10, width_mm=30)


def _version(*, author_required: bool = False) -> TemplateVersion:
    slots = (
        SignatureSlotDef("author", {"ru": "Автор"}, ("tz",), _PLACE, required=author_required),
        SignatureSlotDef("supervisor", {"ru": "Научный руководитель"}, ("tz",), _PLACE),
        SignatureSlotDef("academic_supervisor", {"ru": "Академический руководитель"}, ("tz",), _PLACE),
    )
    profile = SubmissionProfile(
        id="topic-approval",
        name={"ru": "Заявка"},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="tz", signatures=("author", "supervisor")),),
        extra_items=(),
    )
    return replace(
        make_template_version(),
        signatures_config=SignaturesConfig(slots=slots),
        pack_submission=PackSubmissionConfig(profiles=(profile,)),
    )


def _check(
    slot_id: str,
    *,
    optional: bool = True,
    version: TemplateVersion | None = None,
    routes: tuple[HeldRoute, ...] = (),
    state: SignaturesState | None = None,
) -> None:
    uc = SetSlotOptionalUC(MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
    project = make_project(documents=[make_document("tz")])
    inp = SetSlotOptionalInput(project.id, "tz", slot_id, "topic-approval", optional)
    uc._check_slot(project, version or _version(), project.documents[0], inp, routes, state or SignaturesState.empty())


def test__check_slot__slot_of_the_point__allowed() -> None:
    _check("supervisor")


def test__check_slot__pack_forbids__optional_forbidden_but_unmarking_allowed() -> None:
    version = _version(author_required=True)

    with pytest.raises(RouteConflictError) as caught:
        _check("author", version=version)

    assert caught.value.code == "optional_forbidden"
    _check("author", optional=False, version=version)


def test__check_slot__extra_slot__only_while_the_route_of_the_point_includes_it() -> None:
    route = HeldRoute(uuid4(), "topic-approval", frozenset({"tz"}), frozenset({DocSlot("tz", "academic_supervisor")}))
    other_point = replace(route, profile_id="defence")

    _check("academic_supervisor", routes=(route,))
    with pytest.raises(RouteInputError) as caught:
        _check("academic_supervisor", routes=(other_point,))

    assert caught.value.code == "unknown_slot"


def test__check_slot__recorded_skip_or_flag__can_be_removed_without_the_route() -> None:
    skip = SkippedSlot(profile_id="topic-approval", route_id="r", round=1, at="t")
    skipped = replace(SignaturesState.empty(), skipped={"tz": {"academic_supervisor": skip}})

    _check("academic_supervisor", optional=False, state=skipped)
    with pytest.raises(RouteInputError):
        _check("academic_supervisor", optional=False)
    with pytest.raises(RouteInputError):
        _check("academic_supervisor", state=skipped)


def test__pack_slot__required_key__read_and_given_to_runtime_slots() -> None:
    raw = {"id": "author", "label": {"ru": "Автор"}, "applies_to": ["tz"], "required": True}

    parsed = _parse_signature_slot(raw)
    legacy = _parse_signature_slot({"id": "supervisor", "applies_to": ["tz"]})

    assert (parsed.required, legacy.required) == (True, False)
    version = replace(make_template_version(), signatures_config=SignaturesConfig(slots=(parsed, legacy)))
    runtime = {s.id: s.required for s in SignatureSlotService().runtime_slots(make_project(), version)}
    assert runtime == {"author": True, "supervisor": False}
