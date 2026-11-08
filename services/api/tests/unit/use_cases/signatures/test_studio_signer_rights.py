"""Кто вправе подписать слот ключом из Студии (docs/design/signature-plan.md, раздел 5)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ProjectStaffing
from hse_doc_studio.core.value_objects import Author, SignatureSlot, SignaturesState, SignerInfo
from hse_doc_studio.use_cases.signatures._studio_signer import (
    PlateSignerMismatchError,
    SlotNotYoursError,
    StudioSigner,
)

from tests.factories import make_project


class _Scope:
    def __init__(self, personas: set[str], *, single_user: bool) -> None:
        self._personas = frozenset(personas)
        self._single = single_user

    async def personas(self, project: Project) -> frozenset[str]:
        return self._personas

    def single_user(self) -> bool:
        return self._single


def _signer(scope: _Scope) -> StudioSigner:
    unused = cast(Any, None)
    return StudioSigner(unused, unused, unused, unused, unused, scope, unused)


def _team() -> Project:
    return replace(
        make_project(),
        staffing=ProjectStaffing.team,
        authors=[Author(name="Иванов", slug="ivanov"), Author(name="Петров", slug="petrov")],
    )


_KEY = SignerInfo(kind="x509", owner="Иванов", signer_id="mine")
_EMPTY = SignaturesState.empty()


async def test__may_sign__cloud_author_signs_own_slot_only() -> None:
    signer = _signer(_Scope({"ivanov"}, single_user=False))

    await signer.may_sign(_team(), _EMPTY, "author--ivanov", "Автор", _KEY, explicit=True)
    with pytest.raises(SlotNotYoursError):
        await signer.may_sign(_team(), _EMPTY, "author--petrov", "Автор — Петров", _KEY, explicit=True)
    with pytest.raises(SlotNotYoursError):
        await signer.may_sign(_team(), _EMPTY, "supervisor", "Руководитель", _KEY, explicit=True)


async def test__may_sign__cloud_owner_cannot_sign_supervisor_slot_with_own_key() -> None:
    signer = _signer(_Scope({"author"}, single_user=False))

    with pytest.raises(SlotNotYoursError):
        await signer.may_sign(make_project(), _EMPTY, "supervisor", "Руководитель", _KEY, explicit=True)


async def test__may_sign__bound_supervisor_signs_supervisor_slot() -> None:
    signer = _signer(_Scope({"supervisor"}, single_user=False))

    await signer.may_sign(make_project(), _EMPTY, "supervisor", "Руководитель", _KEY, explicit=False)


async def test__may_sign__plate_names_other_signer__refused_even_for_own_slot() -> None:
    signer = _signer(_Scope({"author"}, single_user=False))
    plate = SignerInfo(kind="x509", owner="Сидоров", signer_id="other")
    state = SignaturesState(slots={"author": SignatureSlot(None, None, None, signer=plate)}, placements={})

    with pytest.raises(PlateSignerMismatchError):
        await signer.may_sign(make_project(), state, "author", "Автор", _KEY, explicit=True)


async def test__may_sign__local_explicit_slot_without_plate__allowed_bulk_is_not() -> None:
    signer = _signer(_Scope({"author"}, single_user=True))

    await signer.may_sign(make_project(), _EMPTY, "supervisor", "Руководитель", _KEY, explicit=True)
    with pytest.raises(SlotNotYoursError):
        await signer.may_sign(make_project(), _EMPTY, "supervisor", "Руководитель", _KEY, explicit=False)
