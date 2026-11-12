from __future__ import annotations

from dataclasses import replace
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
from hse_doc_studio.core.enums import (
    DetachedFormat,
    DetachedOrigin,
    DetachedVerdict,
    EngineType,
    SignMode,
    TemplateVersionStatus,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.services import SubmissionProfileService
from hse_doc_studio.core.submission_errors import PackError, PackErrorCode
from hse_doc_studio.core.value_objects import (
    DetachedSignature,
    FrozenPdf,
    PinnedPdf,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
    SkippedSlot,
)
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

    with pytest.raises(PackError, match="supervisor") as caught:
        svc.build_item_list(profile, project, _make_version((profile,)), sig_state)

    assert (caught.value.code, caught.value.doc_id) == (PackErrorCode.slot_not_signed, "tz")


# Фиксация другой версии, чем версия на подписи (ручная до отправки), подписи над ней готовыми не считает (12.8.1).

_OLD_BUILD = "1" * 64
_SENT = "2" * 64
_B = "3" * 64


def _detached_state(*, pinned_sha: str | None) -> SignaturesState:
    state = SignaturesState(
        slots={
            "supervisor": SignatureSlot(
                png_path=None, natural_width_px=None, natural_height_px=None, sign_mode=SignMode.detached_text
            )
        },
        placements={
            "tz": {"supervisor": SignaturePlacement(enabled=True, page=1, x_mm=10.0, y_mm=20.0, width_mm=50.0)}
        },
        frozen={
            "tz": FrozenPdf(
                path=".hse-studio/frozen/tz.pdf",
                sha256=_B,
                source_sha256=_OLD_BUILD,
                size=1,
                frozen_at="2026-11-01T10:00:00Z",
            )
        },
        detached={
            "tz": {
                "supervisor": DetachedSignature(
                    file=".hse-studio/detached/tz/supervisor.asc",
                    format=DetachedFormat.openpgp,
                    origin=DetachedOrigin.uploaded,
                    pdf_sha256=_B,
                    verdict=DetachedVerdict.valid,
                    signer="Петров П. П.",
                    signer_id="A" * 40,
                    added_at="2026-11-01T11:00:00Z",
                )
            }
        },
    )
    if pinned_sha is None:
        return state
    pinned = PinnedPdf(
        path=".hse-studio/frozen/tz.source.pdf",
        sha256=pinned_sha,
        size=1,
        pinned_at="2026-11-10T14:32:00+00:00",
        route_id="00000000-0000-4000-8000-000000000001",
        round=1,
    )
    return replace(state, pinned={"tz": pinned})


def _supervisor_profile() -> SubmissionProfile:
    return SubmissionProfile(
        id="default",
        name={"ru": "Default"},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="tz", signatures=("supervisor",)),),
        extra_items=(),
    )


@pytest.mark.parametrize("pinned_sha", [None, _OLD_BUILD], ids=["no_version", "version_frozen"])
def test__build_item_list__signature_over_the_signing_source__signed(
    svc: SubmissionProfileService, pinned_sha: str | None
) -> None:
    profile = _supervisor_profile()
    project = make_project(documents=[make_document("tz")])

    result = svc.build_item_list(profile, project, _make_version((profile,)), _detached_state(pinned_sha=pinned_sha))

    assert result[0].signatures == ("supervisor",)


def test__build_item_list__manual_freeze_before_route__not_signed_with_route_hint(
    svc: SubmissionProfileService,
) -> None:
    profile = _supervisor_profile()
    project = make_project(documents=[make_document("tz")])

    with pytest.raises(PackError) as caught:
        svc.build_item_list(profile, project, _make_version((profile,)), _detached_state(pinned_sha=_SENT))

    error = caught.value
    assert (error.code, error.doc_id) == (PackErrorCode.slot_not_signed, "tz")
    # Подсказка говорит про фиксацию маршрутом, а не «зафиксируйте заново».
    assert error.params["hint"] == "Ждёт фиксации новой версии"


def test__build_item_list__skipped_and_optional_unsigned__do_not_block(svc: SubmissionProfileService) -> None:
    """Пропущенная на точке и необязательная неподписанная подписи готовности не блокируют (signing-route.md, 13.11)."""
    profile = SubmissionProfile(
        id="topic-approval",
        name={"ru": "Заявка"},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="tz", signatures=("supervisor", "academic_supervisor", "co_supervisor")),),
        extra_items=(),
    )
    project = make_project(documents=[make_document("tz")])
    sig_state = SignaturesState(
        slots={"supervisor": SignatureSlot(png_path="sig.png", natural_width_px=None, natural_height_px=None)},
        placements={
            "tz": {"supervisor": SignaturePlacement(enabled=True, page=1, x_mm=10.0, y_mm=20.0, width_mm=50.0)}
        },
        skipped={
            "tz": {"academic_supervisor": SkippedSlot(profile_id="topic-approval", route_id="r", round=1, at="t")}
        },
        optional={"tz": {"topic-approval": frozenset({"co_supervisor"})}},
    )

    [item] = svc.build_item_list(profile, project, _make_version((profile,)), sig_state)

    assert (item.signatures, item.optional_unsigned) == (("supervisor",), ("co_supervisor",))


def test__build_item_list__skipped_or_optional_on_another_point__still_blocks(svc: SubmissionProfileService) -> None:
    profile = SubmissionProfile(
        id="topic-approval",
        name={"ru": "Заявка"},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="tz", signatures=("academic_supervisor",)),),
        extra_items=(),
    )
    project = make_project(documents=[make_document("tz")])
    skipped = SignaturesState(
        slots={},
        placements={},
        skipped={"tz": {"academic_supervisor": SkippedSlot(profile_id="defence", route_id="r", round=1, at="t")}},
    )
    optional = SignaturesState(
        slots={}, placements={}, optional={"tz": {"defence": frozenset({"academic_supervisor"})}}
    )

    for state in (skipped, optional):
        with pytest.raises(ValueError, match="academic_supervisor"):
            svc.build_item_list(profile, project, _make_version((profile,)), state)
