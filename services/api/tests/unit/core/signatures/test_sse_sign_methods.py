"""КП СПИ с 2026.1.3: точки сдачи принимают подпись картинкой или открепленной ЭП, не PAdES."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signatures.plan import profile_restrictions, slot_mode_conflict
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

from tests.factories import make_project

_PACKS = Path(__file__).resolve().parents[6] / "packs"
_PADES = (SignMode.image_crypto, SignMode.crypto_invisible)
_ACCEPTED = (SignMode.image, SignMode.detached, SignMode.detached_text)


@pytest.fixture(scope="module")
def templates() -> YamlTemplateRepository:
    return YamlTemplateRepository(_PACKS)


def _version(templates: YamlTemplateRepository, version: str) -> TemplateVersion:
    found = templates.get_version("hse-cs-sse", "coursework", version)
    assert found is not None
    return found


def _project(version: str) -> Project:
    project = make_project()
    project.lock = dataclasses.replace(project.lock, pack_id="hse-cs-sse", template_id="coursework", version=version)
    return project


@pytest.mark.unit
def test__sse_2026_1_3__every_signed_item__accepts_image_or_detached(templates: YamlTemplateRepository) -> None:
    version = _version(templates, "2026.1.3")
    assert version.pack_submission is not None
    signed = [(p.id, i) for p in version.pack_submission.profiles for i in p.items if i.signatures]
    assert {(pid, i.doc_id) for pid, i in signed} == {
        ("topic-approval", "project_proposal"),
        ("topic-approval", "topic_application"),
        ("final", "report"),
    }
    for _, item in signed:
        for slot_id in item.signatures:
            assert item.allowed_methods(slot_id) == ("image", "detached")


@pytest.mark.unit
@pytest.mark.parametrize("slot_id", ["author", "supervisor"])
def test__sse_2026_1_3__pades__rejected_by_every_checkpoint(templates: YamlTemplateRepository, slot_id: str) -> None:
    project = _project("2026.1.3")
    restrictions = profile_restrictions(project, _version(templates, "2026.1.3"), slot_id, "ru")
    assert restrictions
    for mode in _PADES:
        message = slot_mode_conflict(mode, "pkcs12", restrictions)
        assert message is not None
        assert "не принимает ни одна контрольная точка" in message
    for mode in _ACCEPTED:
        assert slot_mode_conflict(mode, None, restrictions) is None


@pytest.mark.unit
@pytest.mark.parametrize("slot_id", ["co_supervisor", "academic_supervisor"])
def test__sse_2026_1_3__unrequired_slot__keeps_any_method(templates: YamlTemplateRepository, slot_id: str) -> None:
    """Консультант и академический руководитель не требуются ни одной точкой: способ не ограничен."""
    restrictions = profile_restrictions(_project("2026.1.3"), _version(templates, "2026.1.3"), slot_id, "ru")
    assert restrictions == []
    assert slot_mode_conflict(SignMode.image_crypto, "pkcs12", restrictions) is None


@pytest.mark.unit
def test__sse_2026_1_2__released_version__has_no_restrictions(templates: YamlTemplateRepository) -> None:
    """Выпущенная 2026.1.2 не тронута: проекты на ней сохраняют PAdES до обновления шаблона."""
    restrictions = profile_restrictions(_project("2026.1.2"), _version(templates, "2026.1.2"), "author", "ru")
    assert restrictions
    assert all(allowed == () for _, allowed in restrictions)
    assert slot_mode_conflict(SignMode.image_crypto, "pkcs12", restrictions) is None
