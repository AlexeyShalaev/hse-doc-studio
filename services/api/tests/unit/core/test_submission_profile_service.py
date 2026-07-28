from __future__ import annotations

from datetime import date

import pytest
from hse_doc_studio.core.catalog import (
    ChecksVersionConfig,
    EngineConfig,
    PackSubmissionConfig,
    SignaturesConfig,
    SubmissionDocItem,
    SubmissionProfile,
    TemplateVersion,
)
from hse_doc_studio.core.enums import EngineType, TemplateVersionStatus
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.services import SubmissionProfileService
from hse_doc_studio.core.value_objects import SignaturePlacement, SignatureSlot, SignaturesState
from pytest_lazy_fixtures import lf

from tests.factories import make_document, make_project


def _make_version(profiles: tuple[SubmissionProfile, ...]) -> TemplateVersion:
    return TemplateVersion(
        pack_id="test-pack",
        template_id="test-tmpl",
        version="1.0",
        status=TemplateVersionStatus.stable,
        released_at=date(2026, 1, 1),
        summary={"ru": "Test"},
        engine_config=EngineConfig(
            default=EngineType.xelatex,
            allowed=(EngineType.xelatex,),
            passes=1,
            flags="",
        ),
        required_tex_packages=(),
        documents=(),
        meta_fields={},
        signatures_config=SignaturesConfig(slots=()),
        pack_submission=PackSubmissionConfig(profiles=profiles),
        checks_config=ChecksVersionConfig(disabled_categories=(), disabled=(), severity_override={}),
        rules=(),
    )


@pytest.fixture
def svc() -> SubmissionProfileService:
    return SubmissionProfileService()


@pytest.fixture
def default_profile() -> SubmissionProfile:
    return SubmissionProfile(id="default", name={"ru": "Default"}, description={"ru": ""}, items=(), extra_items=())


@pytest.fixture
def version_with_default_profile(default_profile: SubmissionProfile) -> TemplateVersion:
    return _make_version((default_profile,))


@pytest.fixture
def version_without_profiles() -> TemplateVersion:
    return _make_version(())


@pytest.mark.parametrize(
    ("version", "profile_id", "expected"),
    [
        pytest.param(lf("version_with_default_profile"), "default", lf("default_profile"), id="existing_id"),
        pytest.param(lf("version_without_profiles"), "nonexistent", None, id="unknown_id"),
    ],
)
def test__get_profile__id_lookup__returns_expected(
    svc: SubmissionProfileService,
    version: TemplateVersion,
    profile_id: str,
    expected: SubmissionProfile | None,
) -> None:
    result = svc.get_profile(version, profile_id)

    assert result is expected


def test__build_item_list__doc_and_signatures_present__returns_item_with_signatures(
    svc: SubmissionProfileService,
) -> None:
    profile = SubmissionProfile(
        id="default",
        name={"ru": "Default"},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="tz", signatures=("supervisor",)),),
        extra_items=(),
    )
    project = make_project(documents=[make_document("tz")])
    sig_state = SignaturesState(
        slots={"supervisor": SignatureSlot(png_path="sig.png", natural_width_px=None, natural_height_px=None)},
        placements={
            "tz": {"supervisor": SignaturePlacement(enabled=True, page=1, x_mm=10.0, y_mm=20.0, width_mm=50.0)}
        },
    )

    result = svc.build_item_list(profile, project, _make_version((profile,)), sig_state)

    assert len(result) == 1
    assert result[0].doc_id == "tz"
    assert "supervisor" in result[0].signatures


def test__build_item_list__doc_not_in_project__raises_not_found(svc: SubmissionProfileService) -> None:
    profile = SubmissionProfile(
        id="default",
        name={"ru": "Default"},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="missing-doc", signatures=()),),
        extra_items=(),
    )

    # Неизвестный паку def id — по-прежнему ошибка (известные, но не
    # инстанцированные в проекте, молча пропускаются — team-семантика).
    with pytest.raises(NotFoundError, match="missing-doc"):
        svc.build_item_list(profile, make_project(documents=[]), _make_version((profile,)), SignaturesState.empty())


def test__build_item_list__signature_slot_missing__raises_value_error(svc: SubmissionProfileService) -> None:
    profile = SubmissionProfile(
        id="default",
        name={"ru": "Default"},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="tz", signatures=("supervisor",)),),
        extra_items=(),
    )
    project = make_project(documents=[make_document("tz")])
    # No placement/slot configured for "supervisor".
    sig_state = SignaturesState(slots={}, placements={"tz": {}})

    with pytest.raises(ValueError, match="supervisor"):
        svc.build_item_list(profile, project, _make_version((profile,)), sig_state)
