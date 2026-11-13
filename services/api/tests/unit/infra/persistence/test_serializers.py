from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.catalog import ExtraSubmissionItem, SubmissionDocItem
from hse_doc_studio.core.entities import (
    ChangeLogEntry,
    ChatSession,
    CompileRecord,
    Document,
    PackSubmissionRecord,
)
from hse_doc_studio.core.enums import (
    ChangeLogKind,
    CheckSeverity,
    CompileStatus,
    DetachedFormat,
    DetachedOrigin,
    DetachedVerdict,
    DocumentStatus,
    EngineType,
    PersonRole,
)
from hse_doc_studio.core.value_objects import (
    CheckLocation,
    CheckResult,
    ChecksOverride,
    CustomFileOverride,
    DetachedSignature,
    EmbeddedSignature,
    FrozenPdf,
    Person,
    PinnedPdf,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
    SkippedSlot,
)
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.persistence.serializers import (
    _parse_dt,
    deserialize_changelog_entry,
    deserialize_chat_session,
    deserialize_compile_record,
    deserialize_pack_submission_record,
    deserialize_project,
    deserialize_signatures_state,
    serialize_changelog_entry,
    serialize_chat_session,
    serialize_compile_record,
    serialize_pack_submission_record,
    serialize_project,
    serialize_signatures_state,
)

from tests.factories import make_document, make_project


@pytest.mark.unit
def test__serializers__project_roundtrip(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    data = serialize_project(project)
    restored = deserialize_project(data, folder=tmp_path)
    assert restored.id == project.id
    assert restored.name == project.name
    assert restored.folder == project.folder
    assert restored.lock.pack_id == project.lock.pack_id
    assert restored.kind == project.kind
    assert restored.lang == project.lang
    assert restored.pinned is False
    assert restored.archived is False


@pytest.mark.unit
def test__serializers__project_does_not_persist_folder(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    data = serialize_project(project)
    assert "folder" not in data


@pytest.mark.unit
def test__serializers__project_folder_taken_from_arg_not_json(tmp_path: Path) -> None:
    # Simulate an old file that still carries a stale "folder" key, plus the
    # caller passing a different (current) on-disk folder. The arg must win.
    project = make_project(folder=Path("/old/stale/path"))
    data = serialize_project(project)
    data["folder"] = "/old/stale/path"  # legacy field, must be ignored
    restored = deserialize_project(data, folder=tmp_path)
    assert restored.folder == tmp_path


@pytest.mark.unit
def test__serializers__project_with_supervisor_roundtrip(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    project.supervisor = Person(name="Prof. Ivanov", role=PersonRole.university, title="PhD")
    data = serialize_project(project)
    restored = deserialize_project(data, folder=tmp_path)
    assert restored.supervisor is not None
    assert restored.supervisor.name == "Prof. Ivanov"
    assert restored.supervisor.role == PersonRole.university
    assert restored.supervisor.title == "PhD"


@pytest.mark.unit
def test__serializers__project_no_supervisor_roundtrip(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path)
    assert project.supervisor is None
    data = serialize_project(project)
    restored = deserialize_project(data, folder=tmp_path)
    assert restored.supervisor is None
    assert restored.co_supervisor is None


@pytest.mark.unit
def test__serializers__project_with_documents_roundtrip(tmp_path: Path) -> None:
    project = make_project(
        folder=tmp_path,
        documents=[make_document("vkr"), make_document("pres", chosen_variant="beamer")],
    )
    data = serialize_project(project)
    restored = deserialize_project(data, folder=tmp_path)
    assert len(restored.documents) == 2
    assert restored.documents[0].id == "vkr"
    assert restored.documents[1].id == "pres"
    assert restored.documents[1].chosen_variant == "beamer"


@pytest.mark.unit
def test__serializers__project_checks_override_roundtrip(tmp_path: Path) -> None:
    project = make_project(
        folder=tmp_path,
        documents=[
            Document(
                id="vkr",
                status=DocumentStatus.draft,
                chosen_variant=None,
                last_compile_id=None,
                checks_override=ChecksOverride(
                    disabled_categories=("formatting",),
                    disabled=("r1",),
                    enabled=("r2",),
                    severity_override={"r3": CheckSeverity.err},
                ),
            )
        ],
    )
    data = serialize_project(project)
    restored = deserialize_project(data, folder=tmp_path)
    co = restored.documents[0].checks_override
    assert "formatting" in co.disabled_categories
    assert "r1" in co.disabled
    assert "r2" in co.enabled
    assert co.severity_override["r3"] == CheckSeverity.err


@pytest.mark.unit
def test__serializers__document_custom_file_roundtrip(tmp_path: Path) -> None:
    custom_file = CustomFileOverride(
        original_filename="ТЗ.docx",
        stored_path="tz/_custom/ТЗ.docx",
        ext=".docx",
        uploaded_at="2026-07-20T12:00:00+00:00",
        convert_to_pdf_at_package=True,
    )
    project = make_project(
        folder=tmp_path,
        documents=[
            Document(
                id="tz",
                status=DocumentStatus.draft,
                chosen_variant=None,
                last_compile_id=None,
                checks_override=ChecksOverride(),
                custom_file=custom_file,
            )
        ],
    )
    data = serialize_project(project)
    restored = deserialize_project(data, folder=tmp_path)
    restored_custom = restored.documents[0].custom_file
    assert restored_custom is not None
    assert restored_custom.original_filename == "ТЗ.docx"
    assert restored_custom.stored_path == "tz/_custom/ТЗ.docx"
    assert restored_custom.ext == ".docx"
    assert restored_custom.uploaded_at == "2026-07-20T12:00:00+00:00"
    assert restored_custom.convert_to_pdf_at_package is True


@pytest.mark.unit
def test__serializers__document_without_custom_file_key__defaults_to_none(tmp_path: Path) -> None:
    # Old project.json files never had a "custom_file" key at all.
    project = make_project(folder=tmp_path, documents=[make_document("vkr")])
    data = serialize_project(project)
    del data["documents"][0]["custom_file"]
    restored = deserialize_project(data, folder=tmp_path)
    assert restored.documents[0].custom_file is None


@pytest.mark.unit
def test__serializers__compile_record_roundtrip(tmp_path: Path) -> None:
    now = datetime.now(tz=timezone.utc)
    record = CompileRecord(
        id=uuid4(),
        project_folder=tmp_path,
        doc_id="vkr",
        engine=EngineType.xelatex,
        status=CompileStatus.success,
        started_at=now,
        finished_at=now,
        log="compilation log",
        output_path=tmp_path / "vkr" / "main.pdf",
        check_results=[
            CheckResult(
                rule_id="r1",
                severity=CheckSeverity.warn,
                message="test warning",
                location=CheckLocation(file="main.tex", line=10),
            )
        ],
        pages=5,
    )
    data = serialize_compile_record(record)
    restored = deserialize_compile_record(data, project_folder=tmp_path)
    assert restored.id == record.id
    assert restored.project_folder == tmp_path
    assert restored.doc_id == "vkr"
    assert restored.status == CompileStatus.success
    assert restored.output_path == tmp_path / "vkr" / "main.pdf"
    assert len(restored.check_results) == 1
    assert restored.check_results[0].rule_id == "r1"
    assert restored.check_results[0].location is not None
    assert restored.check_results[0].location.line == 10
    assert restored.pages == 5


@pytest.mark.unit
def test__serializers__compile_record_output_path_stored_as_relative(tmp_path: Path) -> None:
    now = datetime.now(tz=timezone.utc)
    record = CompileRecord(
        id=uuid4(),
        project_folder=tmp_path,
        doc_id="vkr",
        engine=EngineType.xelatex,
        status=CompileStatus.success,
        started_at=now,
        finished_at=now,
        log="",
        output_path=tmp_path / "vkr" / "main.pdf",
        check_results=[],
        pages=1,
    )
    data = serialize_compile_record(record)
    # Stored value is project-relative, NOT absolute. That's what makes moving
    # the project folder safe — the deserializer re-resolves against the new
    # on-disk location.
    assert data["output_path"] == str(Path("vkr") / "main.pdf")
    assert "project_folder" not in data


@pytest.mark.unit
def test__serializers__compile_record_null_fields_roundtrip(tmp_path: Path) -> None:
    now = datetime.now(tz=timezone.utc)
    record = CompileRecord(
        id=uuid4(),
        project_folder=tmp_path,
        doc_id="vkr",
        engine=EngineType.xelatex,
        status=CompileStatus.running,
        started_at=now,
        finished_at=None,
        log="",
        output_path=None,
        check_results=[],
        pages=None,
    )
    data = serialize_compile_record(record)
    restored = deserialize_compile_record(data, project_folder=tmp_path)
    assert restored.finished_at is None
    assert restored.output_path is None
    assert restored.pages is None


@pytest.mark.unit
def test__serializers__changelog_entry_roundtrip() -> None:
    now = datetime.now(tz=timezone.utc)
    entry = ChangeLogEntry(
        id=uuid4(),
        at=now,
        kind=ChangeLogKind.compile_ok,
        doc_id="vkr",
        summary="Compilation succeeded",
        note="All good",
    )
    data = serialize_changelog_entry(entry)
    restored = deserialize_changelog_entry(data)
    assert restored.id == entry.id
    assert restored.kind == ChangeLogKind.compile_ok
    assert restored.doc_id == "vkr"
    assert restored.summary == "Compilation succeeded"
    assert restored.note == "All good"


@pytest.mark.unit
def test__serializers__changelog_entry_no_doc_id_roundtrip() -> None:
    now = datetime.now(tz=timezone.utc)
    entry = ChangeLogEntry(
        id=uuid4(),
        at=now,
        kind=ChangeLogKind.manual_note,
        doc_id=None,
        summary="General note",
        note=None,
    )
    data = serialize_changelog_entry(entry)
    restored = deserialize_changelog_entry(data)
    assert restored.doc_id is None
    assert restored.note is None


@pytest.mark.unit
def test__serializers__pack_submission_record_roundtrip(tmp_path: Path) -> None:
    now = datetime.now(tz=timezone.utc)
    record = PackSubmissionRecord(
        id=uuid4(),
        project_folder=tmp_path,
        profile_id="prof1",
        created_at=now,
        doc_items=[SubmissionDocItem(doc_id="vkr", signatures=("slot1", "slot2"))],
        extra_items=[ExtraSubmissionItem(source="readme.txt", output_name="README.txt", format=None)],
        output_path=tmp_path / "submissions" / "submission.zip",
    )
    data = serialize_pack_submission_record(record)
    assert "project_folder" not in data
    assert data["output_path"] == str(Path("submissions") / "submission.zip")
    restored = deserialize_pack_submission_record(data, project_folder=tmp_path)
    assert restored.id == record.id
    assert restored.project_folder == tmp_path
    assert restored.profile_id == "prof1"
    assert restored.output_path == tmp_path / "submissions" / "submission.zip"
    assert len(restored.doc_items) == 1
    assert restored.doc_items[0].doc_id == "vkr"
    assert "slot1" in restored.doc_items[0].signatures
    assert "slot2" in restored.doc_items[0].signatures
    assert len(restored.extra_items) == 1
    assert restored.extra_items[0].output_name == "README.txt"


@pytest.mark.unit
def test__serializers__signatures_state_roundtrip() -> None:
    state = SignaturesState(
        slots={
            "student": SignatureSlot(png_path="/tmp/sig.png", natural_width_px=300, natural_height_px=120),
            "supervisor": SignatureSlot(png_path=None, natural_width_px=None, natural_height_px=None),
        },
        placements={
            "vkr": {
                "student": SignaturePlacement(enabled=True, page=1, x_mm=10.0, y_mm=20.0, width_mm=50.0),
                "supervisor": SignaturePlacement(enabled=False, page=1, x_mm=0.0, y_mm=0.0, width_mm=50.0),
            }
        },
    )
    data = serialize_signatures_state(state)
    restored = deserialize_signatures_state(data)

    assert restored.slots["student"].png_path == "/tmp/sig.png"
    assert restored.slots["student"].natural_width_px == 300
    assert restored.slots["supervisor"].png_path is None

    placement = restored.placements["vkr"]["student"]
    assert placement.enabled is True
    assert placement.x_mm == 10.0
    assert placement.width_mm == 50.0
    assert restored.placements["vkr"]["supervisor"].enabled is False


@pytest.mark.unit
def test__serializers__signatures_state__detached_roundtrip_and_legacy_files() -> None:
    frozen = FrozenPdf(path=".hse-studio/frozen/a.pdf", sha256="a" * 64, source_sha256="b" * 64, size=10, frozen_at="t")
    sig = DetachedSignature(
        file=".hse-studio/detached/a/s.asc",
        format=DetachedFormat.openpgp,
        origin=DetachedOrigin.studio,
        pdf_sha256="a" * 64,
        verdict=DetachedVerdict.valid,
        signer="Иван",
        signer_id="F" * 40,
        added_at="t",
        notes=("key_expired",),
    )
    state = SignaturesState(slots={}, placements={}, frozen={"a": frozen}, detached={"a": {"s": sig}})

    restored = deserialize_signatures_state(serialize_signatures_state(state))

    assert restored.frozen == {"a": frozen}
    assert restored.detached == {"a": {"s": sig}}
    # signatures.json written before detached signatures existed still loads.
    legacy = deserialize_signatures_state({"slots": {}, "placements": {}})
    assert legacy.frozen == {}
    assert legacy.detached == {}
    # A corrupt detached entry is skipped, not fatal.
    broken = serialize_signatures_state(state)
    broken["detached"]["a"]["s"]["verdict"] = "nonsense"
    assert deserialize_signatures_state(broken).detached == {}


def test__serializers__signatures_state__embedded_and_signed_file_roundtrip() -> None:
    frozen = FrozenPdf(
        path=".hse-studio/frozen/a.pdf",
        sha256="a" * 64,
        source_sha256="b" * 64,
        size=10,
        frozen_at="t",
        signed_path=".hse-studio/frozen/a.signed.pdf",
        signed_sha256="c" * 64,
        signed_size=30,
    )
    embedded = EmbeddedSignature(
        field_name="Sig_s",
        base_sha256="a" * 64,
        revision_size=30,
        revision_sha256="c" * 64,
        verdict=DetachedVerdict.valid,
        signer="Иван",
        signer_id="d" * 64,
        added_at="t",
        notes=("chain_untrusted_root",),
    )
    state = SignaturesState(slots={}, placements={}, frozen={"a": frozen}, embedded={"a": {"s": embedded}})

    restored = deserialize_signatures_state(serialize_signatures_state(state))

    assert restored.frozen == {"a": frozen}
    assert restored.embedded == {"a": {"s": embedded}}
    assert deserialize_signatures_state({"slots": {}, "placements": {}}).embedded == {}


def test__serializers__signatures_state__withheld_roundtrip_sorted_and_always_written() -> None:
    state = SignaturesState(
        slots={},
        placements={},
        withheld={"b": frozenset({"supervisor", "author"}), "a": frozenset({"academic_supervisor"}), "c": frozenset()},
    )

    data = serialize_signatures_state(state)
    restored = deserialize_signatures_state(data)

    assert data["withheld"] == {"a": ["academic_supervisor"], "b": ["author", "supervisor"]}
    assert restored.withheld == {"a": frozenset({"academic_supervisor"}), "b": frozenset({"author", "supervisor"})}
    assert restored.is_withheld("b", "author")
    assert not restored.is_withheld("a", "author")
    assert serialize_signatures_state(SignaturesState.empty())["withheld"] == {}


def test__serializers__signatures_state__withheld_legacy_and_broken_entries() -> None:
    # signatures.json written before signing routes existed still loads.
    assert deserialize_signatures_state({"slots": {}, "placements": {}}).withheld == {}
    # A broken entry is skipped, the rest of the state is read.
    broken = {
        "slots": {},
        "placements": {},
        "withheld": {"a": "author", "b": [1, "", None, "supervisor"], "c": [], "d": {"x": 1}},
    }
    assert deserialize_signatures_state(broken).withheld == {"b": frozenset({"supervisor"})}
    assert deserialize_signatures_state({"slots": {}, "placements": {}, "withheld": ["a"]}).withheld == {}


def test__serializers__signatures_state__pinned_roundtrip_and_always_written() -> None:
    pinned = PinnedPdf(
        path=".hse-studio/frozen/a.source.pdf",
        sha256="ab" * 32,
        size=1234,
        pinned_at="2026-11-10T14:32:00+00:00",
        route_id="00000000-0000-4000-8000-000000000001",
        round=2,
    )
    state = SignaturesState(slots={}, placements={}, pinned={"a": pinned})

    data = serialize_signatures_state(state)

    assert data["pinned"] == {
        "a": {
            "path": ".hse-studio/frozen/a.source.pdf",
            "sha256": "ab" * 32,
            "size": 1234,
            "pinned_at": "2026-11-10T14:32:00+00:00",
            "route_id": "00000000-0000-4000-8000-000000000001",
            "round": 2,
        }
    }
    assert deserialize_signatures_state(data).pinned == {"a": pinned}
    # Пустой пишется тоже: иначе слияние со старым файлом вернуло бы снятую версию на подписи.
    assert serialize_signatures_state(SignaturesState.empty())["pinned"] == {}


def test__serializers__signatures_state__pinned_legacy_and_broken_entries() -> None:
    # signatures.json, записанный до версии на подписи, читается.
    assert deserialize_signatures_state({"slots": {}, "placements": {}}).pinned == {}
    broken = {
        "slots": {},
        "placements": {},
        "pinned": {
            "no_sha": {"path": "p", "size": 1, "pinned_at": "t"},
            "bad_size": {"path": "p", "sha256": "s", "size": "big", "pinned_at": "t"},
            "not_a_dict": "p",
            "minimal": {"path": "p", "sha256": "s", "size": 1, "pinned_at": "t"},
        },
    }
    assert deserialize_signatures_state(broken).pinned == {"minimal": PinnedPdf("p", "s", 1, "t")}
    assert deserialize_signatures_state({"slots": {}, "placements": {}, "pinned": ["a"]}).pinned == {}


@pytest.mark.unit
def test__serializers__chat_session_persona_roundtrip(tmp_path: Path) -> None:
    now = datetime.now(tz=timezone.utc)
    session = ChatSession(
        id=uuid4(),
        project_folder=tmp_path,
        title="Чат",
        doc_id=None,
        created_at=now,
        updated_at=now,
        persona="custom",
        persona_instructions="Будь нормоконтролёром",
    )
    data = serialize_chat_session(session)
    assert "project_folder" not in data
    restored = deserialize_chat_session(data, project_folder=tmp_path)
    assert restored.persona == "custom"
    assert restored.persona_instructions == "Будь нормоконтролёром"


@pytest.mark.unit
def test__serializers__chat_session_persona_defaults_none(tmp_path: Path) -> None:
    # Old session.json files have no persona keys → deserialize to None.
    now = datetime.now(tz=timezone.utc)
    session = ChatSession(id=uuid4(), project_folder=tmp_path, title="Чат", doc_id=None, created_at=now, updated_at=now)
    data = serialize_chat_session(session)
    del data["persona"]
    del data["persona_instructions"]
    restored = deserialize_chat_session(data, project_folder=tmp_path)
    assert restored.persona is None
    assert restored.persona_instructions is None


@pytest.mark.unit
def test__serializers__parse_dt_naive_datetime_gets_utc() -> None:
    dt = _parse_dt("2026-01-01T12:00:00")
    assert dt.tzinfo is not None
    assert dt.year == 2026
    assert dt.month == 1


@pytest.mark.unit
def test__serializers__parse_dt_aware_datetime_preserved() -> None:
    dt = _parse_dt("2026-06-15T10:30:00+00:00")
    assert dt.tzinfo is not None
    assert dt.year == 2026
    assert dt.month == 6


def test__serializers__signatures_state__optional_and_skipped_roundtrip_and_always_written() -> None:
    skip = SkippedSlot(
        profile_id="topic-approval", route_id="r1", round=2, at="2026-11-13T10:00:00+00:00", keep_mark=True
    )
    state = SignaturesState(
        slots={},
        placements={},
        optional={"b": {"p": frozenset({"supervisor", "author"}), "q": frozenset()}, "c": {}},
        skipped={"b": {"academic_supervisor": skip}, "c": {}},
    )

    data = serialize_signatures_state(state)
    restored = deserialize_signatures_state(data)

    assert data["optional"] == {"b": {"p": ["author", "supervisor"]}}
    assert data["skipped"] == {
        "b": {
            "academic_supervisor": {
                "profile_id": "topic-approval",
                "route_id": "r1",
                "round": 2,
                "at": "2026-11-13T10:00:00+00:00",
                "keep_mark": True,
            }
        }
    }
    assert restored.optional == {"b": {"p": frozenset({"author", "supervisor"})}}
    assert restored.skipped == {"b": {"academic_supervisor": skip}}
    assert restored.is_optional("b", "p", "author")
    assert not restored.is_optional("b", "q", "author")
    assert restored.skip_of("b", "academic_supervisor") == skip
    assert restored.skip_of("b", "academic_supervisor", "other-point") is None
    empty = serialize_signatures_state(SignaturesState.empty())
    assert (empty["optional"], empty["skipped"]) == ({}, {})


def test__serializers__signatures_state__optional_and_skipped_legacy_and_broken_entries() -> None:
    assert deserialize_signatures_state({"slots": {}, "placements": {}}).optional == {}
    assert deserialize_signatures_state({"slots": {}, "placements": {}}).skipped == {}
    broken = {
        "slots": {},
        "placements": {},
        "optional": {"a": ["author"], "b": {"p": [1, "", "supervisor"], "q": "author"}, "c": {"p": []}},
        "skipped": {
            "a": ["x"],
            "b": {
                "ok": {"profile_id": "p", "at": "2026-11-13T10:00:00+00:00"},
                "no_at": {"profile_id": "p"},
                "no_profile": {"profile_id": "", "at": "2026-11-13T10:00:00+00:00"},
                "bad_round": {"profile_id": "p", "at": "x", "round": "two"},
                "not_dict": "p",
            },
        },
    }

    restored = deserialize_signatures_state(broken)

    assert restored.optional == {"b": {"p": frozenset({"supervisor"})}}
    assert restored.skipped == {
        "b": {"ok": SkippedSlot(profile_id="p", route_id="", round=0, at="2026-11-13T10:00:00+00:00")}
    }


def test__signatures_state__mark_hidden__withheld_and_skipped_without_kept_mark() -> None:
    skip = SkippedSlot(profile_id="p", route_id="r", round=1, at="t")
    state = SignaturesState(
        slots={},
        placements={},
        withheld={"a": frozenset({"author"})},
        skipped={"a": {"supervisor": skip, "academic_supervisor": SkippedSlot("p", "r", 1, "t", keep_mark=True)}},
    )

    assert state.mark_hidden("a", "author")
    assert state.mark_hidden("a", "supervisor")
    assert not state.mark_hidden("a", "academic_supervisor")
    assert not state.mark_hidden("b", "supervisor")


@pytest.mark.unit
def test__serializers__project_deadlines__roundtrip_sorted_and_always_written(tmp_path: Path) -> None:
    """Сроки точек (signing-route.md, 16.3): момент с поясом, ключ это id точки; пустой словарь тоже пишется."""
    msk = timezone(timedelta(hours=3))
    deadlines = {
        "topic-approval": datetime(2026, 11, 15, 23, 59, tzinfo=msk),
        "final": datetime(2027, 6, 1, 20, 59, tzinfo=timezone.utc),
    }
    project = replace(make_project(folder=tmp_path), deadlines=deadlines)

    data = serialize_project(project)
    restored = deserialize_project(data, folder=tmp_path)

    assert data["deadlines"] == {"final": "2027-06-01T20:59:00+00:00", "topic-approval": "2026-11-15T23:59:00+03:00"}
    assert list(data["deadlines"]) == ["final", "topic-approval"]
    assert restored.deadlines == deadlines
    assert serialize_project(make_project(folder=tmp_path))["deadlines"] == {}


@pytest.mark.unit
def test__serializers__project_deadlines__legacy_and_broken_entries(tmp_path: Path) -> None:
    data = serialize_project(make_project(folder=tmp_path))
    data.pop("deadlines")
    assert deserialize_project(data, folder=tmp_path).deadlines == {}

    data["deadlines"] = {"a": "2026-11-15T23:59:00+03:00", "naive": "2026-11-15T23:59:00", "bad": "завтра", "n": 5}
    assert list(deserialize_project(data, folder=tmp_path).deadlines) == ["a"]
    data["deadlines"] = ["2026-11-15T23:59:00+03:00"]
    assert deserialize_project(data, folder=tmp_path).deadlines == {}


@pytest.mark.unit
def test__project_repository__removed_deadline__does_not_come_back_from_the_old_file(tmp_path: Path) -> None:
    """Сохранение неизвестных полей сливает `deadlines` по ключам нового словаря: снятый срок не воскресает."""
    msk = timezone(timedelta(hours=3))
    repo = JsonProjectRepository()
    project = replace(
        make_project(folder=tmp_path),
        deadlines={"a": datetime(2026, 11, 15, 23, 59, tzinfo=msk), "b": datetime(2027, 1, 20, 23, 59, tzinfo=msk)},
    )
    repo.save(project)

    repo.save(replace(project, deadlines={"b": project.deadlines["b"]}))

    restored = repo.get(tmp_path)
    assert restored is not None
    assert restored.deadlines == {"b": project.deadlines["b"]}
