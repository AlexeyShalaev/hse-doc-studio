from __future__ import annotations

from datetime import datetime, timezone
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
    DocumentStatus,
    EngineType,
    PersonRole,
)
from hse_doc_studio.core.value_objects import (
    CheckLocation,
    CheckResult,
    ChecksOverride,
    CustomFileOverride,
    Person,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
)
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
