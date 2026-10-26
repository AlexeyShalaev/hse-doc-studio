from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.catalog import (
    ChecksVersionConfig,
    DocumentDefinition,
    DocumentVariant,
    EngineConfig,
    ExtraSubmissionItem,
    PackSubmissionConfig,
    SignatureDefaultPlacement,
    SignaturesConfig,
    SignatureSlotDef,
    SubmissionDocItem,
    TemplateVersion,
)
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import (
    DetachedFormat,
    DetachedOrigin,
    DetachedVerdict,
    EngineType,
    Lang,
    ProjectKind,
    ProjectStaffing,
    SignMode,
    TemplateVersionStatus,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.jobs.codec import decode, encode
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.jobs.pack import ArchiveFormat, PackEntryKind, PackSubmissionPayload
from hse_doc_studio.core.signatures.ports import IPublicKeyExporter
from hse_doc_studio.core.value_objects import (
    Author,
    ChecksOverride,
    DetachedSignature,
    FrozenPdf,
    ProjectLock,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
    SignerInfo,
)
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.use_cases.submission.pack_planner import (
    REASON_ARCNAME_ESCAPES,
    REASON_EXTRA_SOURCE_ESCAPES,
    REASON_SOURCE_MISSING,
    PackPlan,
    PackPlanner,
)

from tests.factories import make_custom_file_override, make_document, make_project, make_template_version

_PDF = b"%PDF-1.4 compiled"
_FROZEN = b"%PDF-1.4 frozen"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MemoryProbe:
    """Проект в памяти: путь от корня -> байты."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files = dict(files or {})

    def is_file(self, path: str) -> bool:
        return path in self.files

    def size(self, path: str) -> int:
        return len(self.files[path])

    def sha256(self, path: str) -> str:
        return _sha(self.files[path])

    def read_text(self, path: str) -> str:
        try:
            return self.files[path].decode("utf-8")
        except KeyError:
            raise FileNotFoundError(path) from None

    def read_bytes(self, path: str) -> bytes:
        return self.files[path]

    def list_files(self, prefix: str = "") -> tuple[str, ...]:
        return tuple(sorted(p for p in self.files if p.startswith(prefix)))


class FakeExporter:
    def __init__(self, keys: dict[str, bytes] | None = None) -> None:
        self.keys = keys or {}
        self.calls: list[str] = []

    def export_public(self, fingerprint: str) -> bytes:
        self.calls.append(fingerprint)
        if fingerprint not in self.keys:
            raise RuntimeError("no such key")
        return self.keys[fingerprint]


def _def(
    doc_id: str,
    name: str | None = None,
    *,
    scope: str = "personal",
    variants: tuple[DocumentVariant, ...] = (),
) -> DocumentDefinition:
    return DocumentDefinition(
        id=doc_id,
        name={"ru": doc_id},
        code={"ru": doc_id},
        source_file=None if variants else f"{doc_id}/{doc_id}.tex",
        output_file=None if variants else f"{doc_id}/{doc_id}.pdf",
        output_name={} if variants else {"ru": name or f"{doc_id}.pdf", "en": f"{doc_id}-en.pdf"},
        gost_ref=None,
        required=True,
        checks=ChecksOverride(),
        variants=variants,
        scope=scope,
        supported_staffing=("solo", "team"),
    )


def _version(documents: tuple[DocumentDefinition, ...], slots: tuple[SignatureSlotDef, ...] = ()) -> TemplateVersion:
    base = make_template_version(documents=documents)
    return replace(
        base,
        signatures_config=SignaturesConfig(slots=slots),
        engine_config=EngineConfig(EngineType.xelatex, (EngineType.xelatex,), 2, ""),
        pack_submission=PackSubmissionConfig(profiles=()),
        checks_config=ChecksVersionConfig((), (), {}),
        status=TemplateVersionStatus.stable,
        released_at=date(2026, 1, 1),
    )


def _team_project(documents: list) -> Project:
    now = datetime.now(tz=timezone.utc)
    return Project(
        id=uuid4(),
        name="Система X",
        folder=Path("/tmp/x"),
        lock=ProjectLock(pack_id="p", template_id="t", version="1", engine=EngineType.xelatex),
        kind=ProjectKind.project,
        staffing=ProjectStaffing.team,
        lang=Lang.ru,
        authors=[
            Author(name="Шалаев Алексей", slug="shalaev", managed=True),
            Author(name="Иванов Иван", slug="ivanov", managed=True),
        ],
        meta={},
        supervisor=None,
        co_supervisor=None,
        documents=documents,
        created_at=now,
        updated_at=now,
        shared_enabled=True,
    )


def _empty() -> SignaturesState:
    return SignaturesState(slots={}, placements={})


def _items(*doc_ids: str, signatures: tuple[str, ...] = ()) -> list[SubmissionDocItem]:
    return [SubmissionDocItem(doc_id=d, signatures=signatures) for d in doc_ids]


def _plan(
    project: Project,
    version: TemplateVersion,
    probe: MemoryProbe,
    *,
    docs: list[SubmissionDocItem] | None = None,
    extras: list[ExtraSubmissionItem] | None = None,
    state: SignaturesState | None = None,
    lang: Lang = Lang.ru,
    rendered: dict[str, str] | None = None,
    decisions: dict[str, bool] | None = None,
    exporter: IPublicKeyExporter | None = None,
    archive_format: str = "zip",
) -> PackPlan:
    return PackPlanner().build(
        project,
        version,
        state or _empty(),
        docs or [],
        extras or [],
        lang,
        rendered,
        decisions,
        probe,
        exporter,
        "final-20260101T000000-abcd1234",
        "final",
        archive_format,
    )


def _arcnames(plan: PackPlan) -> list[str]:
    return [e.arcname for e in plan.payload.entries]


def test__pack_planner__doc_item_present__copy_entry_named_by_output_name() -> None:
    version = _version((_def("tz", "ТЗ.pdf"),))
    project = make_project(documents=[make_document("tz")])
    probe = MemoryProbe({"tz/tz.pdf": _PDF})

    plan = _plan(project, version, probe, docs=_items("tz"))

    [entry] = plan.payload.entries
    assert (entry.kind, entry.arcname, entry.source, entry.stamps) == (
        PackEntryKind.copy,
        "ТЗ.pdf",
        ManifestFile("tz/tz.pdf"),
        (),
    )
    assert plan.warnings == ()


def test__pack_planner__solo_variant_doc__arcname_from_chosen_variant() -> None:
    pptx = DocumentVariant(
        id="pptx",
        label={"ru": "PowerPoint"},
        source_file="pres/pres.pptx",
        output_file="pres/pres.pptx",
        output_name={"ru": "Презентация.pptx"},
        engine=None,
    )
    beamer = DocumentVariant(
        id="beamer",
        label={"ru": "Beamer"},
        source_file="pres/pres.tex",
        output_file="pres/pres.pdf",
        output_name={"ru": "Презентация.pdf"},
        engine=EngineType.xelatex,
    )
    version = _version((_def("pres", variants=(pptx, beamer)),))
    probe = MemoryProbe({"pres/pres.pptx": b"PK", "pres/pres.pdf": _PDF})

    pptx_plan = _plan(
        make_project(documents=[make_document("pres", chosen_variant="pptx")]),
        version,
        probe,
        docs=_items("pres"),
    )
    beamer_plan = _plan(
        make_project(documents=[make_document("pres", chosen_variant="beamer")]),
        version,
        probe,
        docs=_items("pres"),
    )

    [pptx_entry] = pptx_plan.payload.entries
    assert (pptx_entry.kind, pptx_entry.arcname, pptx_entry.source) == (
        PackEntryKind.copy,
        "Презентация.pptx",
        ManifestFile("pres/pres.pptx"),
    )
    [beamer_entry] = beamer_plan.payload.entries
    assert (beamer_entry.arcname, beamer_entry.source) == ("Презентация.pdf", ManifestFile("pres/pres.pdf"))
    assert pptx_plan.warnings == ()


def test__pack_planner__payload_header__lang_names_and_format() -> None:
    version = _version((_def("tz", "ТЗ.pdf"),))
    probe = MemoryProbe({"tz/tz.pdf": _PDF})
    project = make_project(documents=[make_document("tz")])

    plan = _plan(project, version, probe, docs=_items("tz"), lang=Lang.en, archive_format="targz")

    payload = plan.payload
    assert (payload.base_name, payload.profile_id, payload.lang) == ("final-20260101T000000-abcd1234", "final", Lang.en)
    assert (payload.archive_format, payload.keep_folder, payload.verify_manifest) == (ArchiveFormat.targz, True, False)
    assert _arcnames(plan) == ["tz-en.pdf"]


def test__pack_planner__unknown_archive_format__same_value_error() -> None:
    version = _version(())

    with pytest.raises(ValueError, match="Unknown archive format: 'bogus'"):
        _plan(make_project(), version, MemoryProbe(), archive_format="bogus")


def test__pack_planner__team_personal_doc__owner_suffix_and_base_path() -> None:
    version = _version((_def("tz", "ТЗ.pdf"),))
    project = _team_project([replace(make_document("tz--shalaev"), def_id="tz", owner="shalaev")])
    probe = MemoryProbe({"shalaev/tz/tz.pdf": _PDF})

    plan = _plan(project, version, probe, docs=_items("tz--shalaev"))

    [entry] = plan.payload.entries
    assert entry.arcname == "ТЗ — Шалаев.pdf"
    assert entry.source == ManifestFile("shalaev/tz/tz.pdf")


def test__pack_planner__team_shared_doc__path_under_shared() -> None:
    version = _version((_def("tz", "ТЗ.pdf", scope="shared"),))
    project = _team_project([make_document("tz")])
    probe = MemoryProbe({"shared/tz/tz.pdf": _PDF})

    plan = _plan(project, version, probe, docs=_items("tz"))

    [entry] = plan.payload.entries
    assert entry.arcname == "ТЗ.pdf"
    assert entry.source == ManifestFile("shared/tz/tz.pdf")


def test__pack_planner__custom_pdf__copy_entry_no_stamps() -> None:
    custom = make_custom_file_override("my-tz.pdf", "tz/_custom/my-tz.pdf", ".pdf")
    version = _version((_def("tz", "ТЗ.pdf"),))
    project = make_project(documents=[make_document("tz", custom_file=custom)])
    probe = MemoryProbe({"tz/_custom/my-tz.pdf": _PDF})

    plan = _plan(project, version, probe, docs=_items("tz"))

    [entry] = plan.payload.entries
    assert (entry.kind, entry.arcname, entry.stamps) == (PackEntryKind.copy, "ТЗ.pdf", ())
    assert entry.source == ManifestFile("tz/_custom/my-tz.pdf")


def test__pack_planner__custom_docx_with_sibling__pdf_entry() -> None:
    custom = make_custom_file_override("ТЗ.docx", "tz/_custom/ТЗ.docx", ".docx")
    version = _version((_def("tz", "ТЗ.pdf"),))
    project = make_project(documents=[make_document("tz", custom_file=custom)])
    probe = MemoryProbe({"tz/_custom/ТЗ.docx": b"docx", "tz/_custom/ТЗ.pdf": _PDF})

    plan = _plan(project, version, probe, docs=_items("tz"), decisions={"tz": True})

    [entry] = plan.payload.entries
    assert entry.arcname == "ТЗ.pdf"
    assert entry.source == ManifestFile("tz/_custom/ТЗ.pdf")


def test__pack_planner__custom_docx_remembered_decision__sibling_used_without_explicit_one() -> None:
    custom = make_custom_file_override("ТЗ.docx", "tz/_custom/ТЗ.docx", ".docx", convert_to_pdf_at_package=True)
    version = _version((_def("tz", "ТЗ.pdf"),))
    project = make_project(documents=[make_document("tz", custom_file=custom)])
    probe = MemoryProbe({"tz/_custom/ТЗ.docx": b"docx", "tz/_custom/ТЗ.pdf": _PDF})

    kept_plan = _plan(project, version, probe, docs=_items("tz"))
    declined_plan = _plan(project, version, probe, docs=_items("tz"), decisions={"tz": False})

    assert kept_plan.payload.entries[0].source == ManifestFile("tz/_custom/ТЗ.pdf")
    assert declined_plan.payload.entries[0].source == ManifestFile("tz/_custom/ТЗ.docx")
    assert declined_plan.payload.entries[0].arcname == "ТЗ.docx"


@pytest.mark.parametrize("decision", [True, False, None])
def test__pack_planner__custom_docx_without_sibling__raw_entry(decision: bool | None) -> None:
    custom = make_custom_file_override("ТЗ.docx", "tz/_custom/ТЗ.docx", ".docx")
    version = _version((_def("tz", "ТЗ.pdf"),))
    project = make_project(documents=[make_document("tz", custom_file=custom)])
    probe = MemoryProbe({"tz/_custom/ТЗ.docx": b"docx"})

    plan = _plan(project, version, probe, docs=_items("tz"), decisions=None if decision is None else {"tz": decision})

    [entry] = plan.payload.entries
    assert (entry.kind, entry.arcname) == (PackEntryKind.copy, "ТЗ.docx")
    assert entry.source == ManifestFile("tz/_custom/ТЗ.docx")


def test__pack_planner__custom_docx_with_placements__never_stamped() -> None:
    # Для слота есть размещение и PNG, но custom-файл остается docx: штамп на не-PDF не ставится.
    state, slot_def = _stamped_state()
    custom = make_custom_file_override("ТЗ.docx", "tz/_custom/ТЗ.docx", ".docx")
    version = _version((_def("tz", "ТЗ.pdf"),), slots=(slot_def,))
    project = make_project(documents=[make_document("tz", custom_file=custom)])
    probe = MemoryProbe({"tz/_custom/ТЗ.docx": b"docx", ".hse-studio/signatures/author.png": b"png"})

    plan = _plan(project, version, probe, docs=_items("tz", signatures=("author",)), state=state)

    [entry] = plan.payload.entries
    assert (entry.kind, entry.arcname, entry.stamps) == (PackEntryKind.copy, "ТЗ.docx", ())


def test__pack_planner__raw_extra__copy_entry_under_output_name() -> None:
    extra = ExtraSubmissionItem(source="readme.txt", output_name="README.txt", format=None)

    plan = _plan(make_project(), _version(()), MemoryProbe({"readme.txt": b"extra content"}), extras=[extra])

    [entry] = plan.payload.entries
    assert (entry.kind, entry.arcname, entry.source) == (PackEntryKind.copy, "README.txt", ManifestFile("readme.txt"))


def test__pack_planner__missing_source__dropped_with_warning() -> None:
    version = _version((_def("tz", "ТЗ.pdf"), _def("vkr", "ВКР.pdf")))
    project = make_project(documents=[make_document("tz"), make_document("vkr")])
    probe = MemoryProbe({"vkr/vkr.pdf": _PDF})

    plan = _plan(project, version, probe, docs=_items("tz", "vkr", "ghost"))

    assert _arcnames(plan) == ["ВКР.pdf"]
    reasons = [(w.arcname, w.reason) for w in plan.warnings]
    assert reasons == [("ТЗ.pdf", REASON_SOURCE_MISSING), ("ghost", "doc_not_found")]


def test__pack_planner__definition_without_output__dropped_with_warning() -> None:
    no_output = replace(_def("tz"), source_file=None, output_file=None)
    project = make_project(documents=[make_document("tz")])

    plan = _plan(project, _version((no_output,)), MemoryProbe(), docs=_items("tz"))

    assert plan.payload.entries == ()
    assert [(w.arcname, w.reason) for w in plan.warnings] == [("tz", "doc_not_resolvable")]


def test__pack_planner__definition_missing_in_pack__not_found_like_before() -> None:
    project = make_project(documents=[make_document("tz")])

    with pytest.raises(NotFoundError):
        _plan(project, _version(()), MemoryProbe(), docs=_items("tz"))


def _stamped_state() -> tuple[SignaturesState, SignatureSlotDef]:
    slot_def = SignatureSlotDef(
        id="author",
        label={"ru": "Автор", "en": "Author"},
        applies_to=("tz",),
        default_placement=SignatureDefaultPlacement(page=1, x_mm=10, y_mm=20, width_mm=30),
    )
    state = SignaturesState(
        slots={
            "author": SignatureSlot(
                png_path=".hse-studio/signatures/author.png", natural_width_px=200, natural_height_px=100
            )
        },
        placements={
            "tz": {
                "author": SignaturePlacement(
                    enabled=True, page=2, x_mm=10, y_mm=20, width_mm=30, sign_date="2026-05-12"
                )
            }
        },
    )
    return state, slot_def


def test__pack_planner__image_signature__stamp_entry_with_png_in_manifest() -> None:
    state, slot_def = _stamped_state()
    version = _version((_def("tz", "ТЗ.pdf"),), slots=(slot_def,))
    project = make_project(documents=[make_document("tz")])
    probe = MemoryProbe({"tz/tz.pdf": _PDF, ".hse-studio/signatures/author.png": b"png"})

    plan = _plan(project, version, probe, docs=_items("tz", signatures=("author",)), state=state)

    [entry] = plan.payload.entries
    assert (entry.kind, entry.arcname, entry.source) == (PackEntryKind.stamp_pdf, "ТЗ.pdf", ManifestFile("tz/tz.pdf"))
    [stamp] = entry.stamps
    assert stamp.png == ManifestFile(".hse-studio/signatures/author.png")
    assert (stamp.page, stamp.x_mm, stamp.y_mm, stamp.width_mm, stamp.aspect_ratio) == (2, 10, 20, 30, 0.5)
    assert stamp.date_text == "12.05.2026"
    assert set(plan.payload.manifest_files()) == {
        ManifestFile("tz/tz.pdf"),
        ManifestFile(".hse-studio/signatures/author.png"),
    }


def test__pack_planner__image_signature_png_missing__copy_entry_like_before() -> None:
    state, slot_def = _stamped_state()
    version = _version((_def("tz", "ТЗ.pdf"),), slots=(slot_def,))
    project = make_project(documents=[make_document("tz")])
    probe = MemoryProbe({"tz/tz.pdf": _PDF})

    plan = _plan(project, version, probe, docs=_items("tz", signatures=("author",)), state=state)

    [entry] = plan.payload.entries
    assert (entry.kind, entry.stamps) == (PackEntryKind.copy, ())


def test__pack_planner__slot_not_requested_by_profile__no_stamps() -> None:
    state, slot_def = _stamped_state()
    version = _version((_def("tz", "ТЗ.pdf"),), slots=(slot_def,))
    project = make_project(documents=[make_document("tz")])
    probe = MemoryProbe({"tz/tz.pdf": _PDF, ".hse-studio/signatures/author.png": b"png"})

    plan = _plan(project, version, probe, docs=_items("tz"), state=state)

    assert plan.payload.entries[0].kind is PackEntryKind.copy


def _detached_setup(
    *,
    frozen_source: bytes = _PDF,
    with_frozen_file: bool = True,
    with_sig_file: bool = True,
    signer_id: str = "A" * 40,
) -> tuple[Project, TemplateVersion, SignaturesState, MemoryProbe]:
    slot_def = SignatureSlotDef(
        id="advisor",
        label={"ru": "Научный руководитель", "en": "Supervisor"},
        applies_to=("tz",),
        default_placement=SignatureDefaultPlacement(page=1, x_mm=10, y_mm=20, width_mm=30),
    )
    state = SignaturesState(
        slots={
            "advisor": SignatureSlot(
                png_path=None,
                natural_width_px=None,
                natural_height_px=None,
                sign_mode=SignMode.detached_text,
                signer=SignerInfo(kind="openpgp", owner="Иван Иванов", cert_id="1234"),
            )
        },
        placements={"tz": {"advisor": SignaturePlacement(enabled=True, page=1, x_mm=10, y_mm=20, width_mm=30)}},
        frozen={
            "tz": FrozenPdf(
                path=".hse-studio/frozen/tz.pdf",
                sha256=_sha(_FROZEN),
                source_sha256=_sha(frozen_source),
                size=len(_FROZEN),
                frozen_at="2026-05-12T10:00:00Z",
            )
        },
        detached={
            "tz": {
                "advisor": DetachedSignature(
                    file=".hse-studio/signatures/tz.advisor.asc",
                    format=DetachedFormat.openpgp,
                    origin=DetachedOrigin.uploaded,
                    pdf_sha256=_sha(_FROZEN),
                    verdict=DetachedVerdict.valid,
                    signer="Иван Иванов",
                    signer_id=signer_id,
                    added_at="2026-05-12T11:00:00Z",
                )
            }
        },
    )
    files = {"tz/tz.pdf": _PDF}
    if with_frozen_file:
        files[".hse-studio/frozen/tz.pdf"] = _FROZEN
    if with_sig_file:
        files[".hse-studio/signatures/tz.advisor.asc"] = b"-----BEGIN PGP SIGNATURE-----"
    return (
        make_project(documents=[make_document("tz")]),
        _version((_def("tz", "ТЗ.pdf"),), slots=(slot_def,)),
        state,
        MemoryProbe(files),
    )


def test__pack_planner__detached__frozen_sigs_keys_readme_entries() -> None:
    project, version, state, probe = _detached_setup()
    exporter = FakeExporter({"A" * 40: b"-----BEGIN PGP PUBLIC KEY BLOCK-----"})

    plan = _plan(project, version, probe, docs=_items("tz", signatures=("advisor",)), state=state, exporter=exporter)

    entries = plan.payload.entries
    assert [(e.kind, e.arcname) for e in entries] == [
        (PackEntryKind.copy, "ТЗ.pdf"),
        (PackEntryKind.copy, "ТЗ.Научный_руководитель.asc"),
        (PackEntryKind.blob, "public-key.Иван_Иванов.asc"),
        (PackEntryKind.text, "ТЗ.README.txt"),
    ]
    frozen_entry, sig_entry, key_entry, readme_entry = entries
    assert frozen_entry.source == ManifestFile(".hse-studio/frozen/tz.pdf", sha256=_sha(_FROZEN), size=len(_FROZEN))
    assert sig_entry.source == ManifestFile(".hse-studio/signatures/tz.advisor.asc")
    assert key_entry.blob is not None
    assert key_entry.blob.to_bytes() == b"-----BEGIN PGP PUBLIC KEY BLOCK-----"
    assert readme_entry.text is not None
    assert _sha(_FROZEN) in readme_entry.text
    assert "ТЗ.Научный_руководитель.asc (подписант: Иван Иванов)" in readme_entry.text
    assert "public-key.Иван_Иванов.asc" in readme_entry.text
    assert exporter.calls == ["A" * 40]


def test__pack_planner__detached_in_subfolder__companions_next_to_pdf() -> None:
    project, version, state, probe = _detached_setup()
    version = replace(version, documents=(replace(version.documents[0], output_name={"ru": "Бумаги/ТЗ.pdf"}),))

    plan = _plan(project, version, probe, docs=_items("tz", signatures=("advisor",)), state=state)

    assert _arcnames(plan) == [
        "Бумаги/ТЗ.pdf",
        "Бумаги/ТЗ.Научный_руководитель.asc",
        "Бумаги/ТЗ.README.txt",
    ]


def test__pack_planner__detached_without_exporter_or_failing_key__no_key_entries() -> None:
    project, version, state, probe = _detached_setup()

    no_exporter = _plan(project, version, probe, docs=_items("tz", signatures=("advisor",)), state=state)
    failing = _plan(
        project, version, probe, docs=_items("tz", signatures=("advisor",)), state=state, exporter=FakeExporter()
    )

    for plan in (no_exporter, failing):
        assert [e.kind for e in plan.payload.entries] == [PackEntryKind.copy, PackEntryKind.copy, PackEntryKind.text]


def test__pack_planner__detached_english__readme_and_label_in_project_language() -> None:
    project, version, state, probe = _detached_setup()

    plan = _plan(project, version, probe, docs=_items("tz", signatures=("advisor",)), state=state, lang=Lang.en)

    assert _arcnames(plan) == ["tz-en.pdf", "tz-en.Supervisor.asc", "tz-en.README.txt"]
    readme = plan.payload.entries[-1].text
    assert readme is not None
    assert readme.startswith("Detached electronic signatures")


def test__pack_planner__frozen_rehash_mismatch__value_error_text_unchanged_before_any_write() -> None:
    project, version, state, probe = _detached_setup(frozen_source=b"%PDF-1.4 older build")

    expected = (
        "ТЗ.pdf: the document was rebuilt after the PDF was frozen for signing. "
        "Freeze it again and re-attach the signatures"
    )
    with pytest.raises(ValueError, match=f"^{re.escape(expected)}$"):
        _plan(project, version, probe, docs=_items("tz", signatures=("advisor",)), state=state)


def test__pack_planner__frozen_pdf_missing__value_error_text_unchanged() -> None:
    project, version, state, probe = _detached_setup(with_frozen_file=False)

    with pytest.raises(ValueError, match="^Frozen PDF is missing for ТЗ.pdf: freeze the document again$"):
        _plan(project, version, probe, docs=_items("tz", signatures=("advisor",)), state=state)


def test__pack_planner__signature_file_missing__value_error_text_unchanged() -> None:
    project, version, state, probe = _detached_setup(with_sig_file=False)

    with pytest.raises(ValueError, match="^Signature file is missing for ТЗ.pdf, slot advisor$"):
        _plan(project, version, probe, docs=_items("tz", signatures=("advisor",)), state=state)


def test__pack_planner__frozen_without_detached_signature_requested__plain_copy() -> None:
    project, version, state, probe = _detached_setup(frozen_source=b"stale")

    plan = _plan(project, version, probe, docs=_items("tz"), state=state)

    [entry] = plan.payload.entries
    assert (entry.kind, entry.source) == (PackEntryKind.copy, ManifestFile("tz/tz.pdf"))


def test__pack_planner__escaping_arcname_or_extra__dropped() -> None:
    version = _version((_def("evil", "../evil.pdf"), _def("deep", "a/../ok.pdf")))
    project = make_project(documents=[make_document("evil"), make_document("deep")])
    probe = MemoryProbe(
        {
            "evil/evil.pdf": _PDF,
            "deep/deep.pdf": _PDF,
            "readme.txt": b"x",
            "../secret.txt": b"top secret",
        }
    )
    extras = [
        ExtraSubmissionItem(source="readme.txt", output_name="../evil.txt", format=None),
        ExtraSubmissionItem(source="readme.txt", output_name="/abs.txt", format=None),
        ExtraSubmissionItem(source="../secret.txt", output_name="leaked.txt", format=None),
        ExtraSubmissionItem(source="/etc/passwd", output_name="leaked2.txt", format=None),
    ]

    plan = _plan(project, version, probe, docs=_items("evil", "deep"), extras=extras, rendered={"x": "y"})

    # `a/../ok.pdf` остается внутри папки пакета и сворачивается в `ok.pdf`, как и при записи на диск
    assert _arcnames(plan) == ["ok.pdf"]
    assert [w.reason for w in plan.warnings] == [
        REASON_ARCNAME_ESCAPES,
        REASON_ARCNAME_ESCAPES,
        REASON_ARCNAME_ESCAPES,
        REASON_EXTRA_SOURCE_ESCAPES,
        REASON_EXTRA_SOURCE_ESCAPES,
    ]


def test__pack_planner__rendered_extra_with_escaping_output_name__dropped() -> None:
    extra = ExtraSubmissionItem(source="forms/x.json", output_name="../x.md", format="markdown")

    plan = _plan(make_project(), _version(()), MemoryProbe(), extras=[extra], rendered={"forms/x.json": "text"})

    assert plan.payload.entries == ()
    assert [w.reason for w in plan.warnings] == [REASON_ARCNAME_ESCAPES]


def test__pack_planner__form_extra_rendered_and_markdown_dump_entries() -> None:
    answers = {"tool": "Claude", "used": True}
    probe = MemoryProbe(
        {
            ".hse-studio/forms/ai_declaration.json": json.dumps(answers).encode(),
            "notes/code.json": json.dumps({"link": "https://example.org"}).encode(),
            "link.txt": b"https://example.org",
            "broken.json": b"{not json",
        }
    )
    extras = [
        ExtraSubmissionItem(
            source=".hse-studio/forms/ai_declaration.json", output_name="Декларация ИИ", format="markdown"
        ),
        ExtraSubmissionItem(source="notes/code.json", output_name="Код.md", format="markdown"),
        ExtraSubmissionItem(source="link.txt", output_name="Ссылка на код.txt", format=None),
        ExtraSubmissionItem(source="broken.json", output_name="Сломан.md", format="markdown"),
        ExtraSubmissionItem(source="absent.txt", output_name="Нет.txt", format=None),
    ]

    plan = _plan(
        make_project(),
        _version(()),
        probe,
        extras=extras,
        rendered={".hse-studio/forms/ai_declaration.json": "# Декларация\n\nИИ не использовался\n"},
    )

    rendered, dump, raw = plan.payload.entries
    # Готовый текст главнее диска; `.md` дописывается, когда у output_name нет расширения.
    assert (rendered.kind, rendered.arcname, rendered.text) == (
        PackEntryKind.text,
        "Декларация ИИ.md",
        "# Декларация\n\nИИ не использовался\n",
    )
    assert (dump.kind, dump.arcname, dump.source) == (PackEntryKind.text, "Код.md", None)
    assert dump.text == "# Код.md\n\n**link**: https://example.org\n"
    assert (raw.kind, raw.arcname, raw.source) == (PackEntryKind.copy, "Ссылка на код.txt", ManifestFile("link.txt"))
    assert [(w.arcname, w.reason) for w in plan.warnings] == [
        ("Сломан.md", "extra_unreadable"),
        ("Нет.txt", "extra_source_missing"),
    ]


def test__pack_planner__rendered_extra__needs_no_source_file() -> None:
    extra = ExtraSubmissionItem(source="forms/ai.json", output_name="Декларация.md", format="markdown")

    plan = _plan(make_project(), _version(()), MemoryProbe(), extras=[extra], rendered={"forms/ai.json": "готово"})

    [entry] = plan.payload.entries
    assert (entry.kind, entry.arcname, entry.text) == (PackEntryKind.text, "Декларация.md", "готово")


def test__pack_planner__entry_order__documents_then_extras() -> None:
    version = _version((_def("tz", "ТЗ.pdf"), _def("vkr", "ВКР.pdf")))
    project = make_project(documents=[make_document("tz"), make_document("vkr")])
    probe = MemoryProbe({"tz/tz.pdf": _PDF, "vkr/vkr.pdf": _PDF, "a.txt": b"a"})
    extras = [ExtraSubmissionItem(source="a.txt", output_name="A.txt", format=None)]

    plan = _plan(project, version, probe, docs=_items("vkr", "tz"), extras=extras)

    assert _arcnames(plan) == ["ВКР.pdf", "ТЗ.pdf", "A.txt"]


def test__pack_planner__every_entry_source_is_manifest_relative() -> None:
    project, version, state, probe = _detached_setup()
    probe.files["a.txt"] = b"a"
    extras = [ExtraSubmissionItem(source="a.txt", output_name="A.txt", format=None)]

    plan = _plan(
        project,
        version,
        probe,
        docs=_items("tz", signatures=("advisor",)),
        extras=extras,
        state=state,
        exporter=FakeExporter({"A" * 40: b"key"}),
    )

    manifest = plan.payload.manifest_files()
    assert manifest
    for entry in plan.payload.entries:
        for file in entry.manifest_files():
            assert file in manifest
            assert not file.path.startswith("/")
            assert ".." not in file.path.split("/")
            assert probe.is_file(file.path)
    # Хеш проставлен только у замороженного PDF, остальные записи его не несут.
    assert [f.sha256 for f in manifest if f.sha256] == [_sha(_FROZEN)]


def test__pack_planner__payload__survives_job_codec_round_trip() -> None:
    project, version, state, probe = _detached_setup()

    plan = _plan(
        project,
        version,
        probe,
        docs=_items("tz", signatures=("advisor",)),
        state=state,
        exporter=FakeExporter({"A" * 40: b"key"}),
    )

    assert decode(PackSubmissionPayload, encode(plan.payload)) == plan.payload


def test__gpg_keyring__is_a_public_key_exporter(tmp_path: Path) -> None:
    exporter: IPublicKeyExporter = GpgKeyring(tmp_path / "gnupg", binary="gpg")

    assert callable(exporter.export_public)
