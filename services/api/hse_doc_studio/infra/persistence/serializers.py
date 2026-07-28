from __future__ import annotations

import contextlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from hse_doc_studio.core.agent.entities import TokenUsage
from hse_doc_studio.core.catalog import ExtraSubmissionItem, SubmissionDocItem
from hse_doc_studio.core.entities import (
    AgentRunRecord,
    ChangeLogEntry,
    ChatContentBlock,
    ChatMessage,
    ChatSession,
    ChatSummaryBlock,
    CompileRecord,
    Document,
    PackSubmissionRecord,
    Project,
)
from hse_doc_studio.core.enums import (
    AgentRunStatus,
    ChangeLogKind,
    ChatContentKind,
    ChatMessageRole,
    CheckSeverity,
    CompileStatus,
    DocumentStatus,
    EngineType,
    Lang,
    PersonRole,
    ProjectKind,
    ProjectStaffing,
    RequirementFormatKind,
    SignMode,
    ToolApprovalDecision,
)
from hse_doc_studio.core.value_objects import (
    Author,
    CheckFix,
    CheckLocation,
    CheckResult,
    ChecksOverride,
    CustomFileOverride,
    FormState,
    Person,
    ProjectLock,
    RequirementsFormat,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
)


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


def serialize_project(project: Project) -> dict[str, Any]:
    return {
        "id": str(project.id),
        "name": project.name,
        "lock": {
            "pack_id": project.lock.pack_id,
            "template_id": project.lock.template_id,
            "version": project.lock.version,
            "engine": project.lock.engine,
        },
        "kind": project.kind,
        "staffing": project.staffing,
        "lang": project.lang,
        "authors": [_serialize_author(a) for a in project.authors],
        "meta": project.meta,
        "supervisor": _serialize_person(project.supervisor),
        "co_supervisor": _serialize_person(project.co_supervisor),
        "academic_supervisor": _serialize_person(project.academic_supervisor),
        "documents": [_serialize_document(d) for d in project.documents],
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "shared_enabled": project.shared_enabled,
        "pinned": project.pinned,
        "archived": project.archived,
        "checks_override": _serialize_checks_override(project.checks_override),
        "requirements": _serialize_requirements_format(project.requirements_format),
    }


def deserialize_project(data: dict[str, Any], folder: Path) -> Project:
    # folder is the on-disk location of the project (parent of .hse-studio/),
    # NOT read from JSON — that makes moving the directory safe. Any persisted
    # "folder" field from older files is intentionally ignored.
    lock_data = data["lock"]
    return Project(
        id=UUID(data["id"]),
        name=data["name"],
        folder=folder,
        lock=ProjectLock(
            pack_id=lock_data["pack_id"],
            template_id=lock_data["template_id"],
            version=lock_data["version"],
            engine=EngineType(lock_data["engine"]),
        ),
        kind=ProjectKind(data["kind"]),
        staffing=ProjectStaffing(data["staffing"]),
        lang=Lang(data["lang"]),
        authors=[_deserialize_author(a) for a in data.get("authors", [])],
        meta=data.get("meta", {}),
        supervisor=_deserialize_person(data.get("supervisor")),
        co_supervisor=_deserialize_person(data.get("co_supervisor")),
        academic_supervisor=_deserialize_person(data.get("academic_supervisor")),
        documents=[_deserialize_document(d) for d in data.get("documents", [])],
        created_at=_parse_dt(data["created_at"]),
        updated_at=_parse_dt(data["updated_at"]),
        shared_enabled=data.get("shared_enabled", True),
        pinned=data.get("pinned", False),
        archived=data.get("archived", False),
        checks_override=_deserialize_checks_override(data.get("checks_override", {})),
        requirements_format=_deserialize_requirements_format(data.get("requirements")),
    )


def _serialize_author(author: Author) -> dict[str, Any]:
    return {
        "name": author.name,
        "group": author.group,
        "email": author.email,
        "slug": author.slug,
        "topic": author.topic,
        "managed": author.managed,
        "meta": author.meta,
    }


def _deserialize_author(data: dict[str, Any]) -> Author:
    return Author(
        name=data["name"],
        group=data.get("group"),
        email=data.get("email"),
        slug=data.get("slug"),
        topic=data.get("topic"),
        # Старые project.json (до team mode) не несут managed — автор считался
        # ведомым всегда.
        managed=bool(data.get("managed", True)),
        meta=dict(data.get("meta", {})),
    )


def _serialize_person(person: Person | None) -> dict[str, Any] | None:
    if person is None:
        return None
    return {
        "name": person.name,
        "role": person.role,
        "title": person.title,
        "degree": person.degree,
    }


def _deserialize_person(data: dict[str, Any] | None) -> Person | None:
    if data is None:
        return None
    return Person(
        name=data["name"],
        role=PersonRole(data["role"]),
        title=data.get("title"),
        degree=data.get("degree"),
    )


def _serialize_document(doc: Document) -> dict[str, Any]:
    return {
        "id": doc.id,
        "status": doc.status,
        "chosen_variant": doc.chosen_variant,
        "last_compile_id": str(doc.last_compile_id) if doc.last_compile_id else None,
        "checks_override": _serialize_checks_override(doc.checks_override),
        "def_id": doc.def_id,
        "owner": doc.owner,
        "custom_file": _serialize_custom_file(doc.custom_file),
    }


def _deserialize_document(data: dict[str, Any]) -> Document:
    return Document(
        id=data["id"],
        status=DocumentStatus(data["status"]),
        chosen_variant=data.get("chosen_variant"),
        last_compile_id=UUID(data["last_compile_id"]) if data.get("last_compile_id") else None,
        checks_override=_deserialize_checks_override(data.get("checks_override", {})),
        # Старые project.json не несут def_id — __post_init__ подставит id.
        def_id=data.get("def_id", ""),
        owner=data.get("owner"),
        custom_file=_deserialize_custom_file(data.get("custom_file")),
    )


def _serialize_checks_override(co: ChecksOverride) -> dict[str, Any]:
    return {
        "disabled_categories": list(co.disabled_categories),
        "disabled": list(co.disabled),
        "enabled": list(co.enabled),
        "severity_override": {k: str(v) for k, v in co.severity_override.items()},
    }


def _deserialize_checks_override(data: dict[str, Any]) -> ChecksOverride:
    return ChecksOverride(
        disabled_categories=tuple(data.get("disabled_categories", [])),
        disabled=tuple(data.get("disabled", [])),
        enabled=tuple(data.get("enabled", [])),
        severity_override={k: CheckSeverity(v) for k, v in data.get("severity_override", {}).items()},
    )


def _serialize_custom_file(custom_file: CustomFileOverride | None) -> dict[str, Any] | None:
    if custom_file is None:
        return None
    return {
        "original_filename": custom_file.original_filename,
        "stored_path": custom_file.stored_path,
        "ext": custom_file.ext,
        "uploaded_at": custom_file.uploaded_at,
        "convert_to_pdf_at_package": custom_file.convert_to_pdf_at_package,
    }


def _deserialize_custom_file(data: dict[str, Any] | None) -> CustomFileOverride | None:
    if not data:
        return None
    return CustomFileOverride(
        original_filename=data["original_filename"],
        stored_path=data["stored_path"],
        ext=data["ext"],
        uploaded_at=data["uploaded_at"],
        convert_to_pdf_at_package=data.get("convert_to_pdf_at_package"),
    )


def _serialize_requirements_format(fmt: RequirementsFormat | None) -> dict[str, Any] | None:
    if fmt is None:
        return None
    return {
        "format": str(fmt.kind),
        "id_pattern": fmt.id_pattern,
        "definition_docs": list(fmt.definition_docs),
        "def_pattern": fmt.def_pattern,
        "ref_pattern": fmt.ref_pattern,
    }


def _deserialize_requirements_format(data: dict[str, Any] | None) -> RequirementsFormat | None:
    if not data:
        return None
    return RequirementsFormat(
        kind=RequirementFormatKind(data.get("format", "macro")),
        id_pattern=data.get("id_pattern"),
        definition_docs=tuple(data.get("definition_docs", [])),
        def_pattern=data.get("def_pattern"),
        ref_pattern=data.get("ref_pattern"),
    )


# ---------------------------------------------------------------------------
# CompileRecord
# ---------------------------------------------------------------------------


def serialize_compile_record(record: CompileRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "doc_id": record.doc_id,
        "engine": record.engine,
        "status": record.status,
        "started_at": record.started_at.isoformat(),
        "finished_at": record.finished_at.isoformat() if record.finished_at else None,
        "log": record.log,
        "output_path": _serialize_project_relative_path(record.output_path, record.project_folder),
        "check_results": [_serialize_check_result(r) for r in record.check_results],
        "pages": record.pages,
        "words": record.words,
        "chars": record.chars,
    }


def deserialize_compile_record(data: dict[str, Any], project_folder: Path) -> CompileRecord:
    # project_folder is derived from the on-disk location of the record file,
    # NOT read from JSON. output_path is stored relative to project_folder when
    # it lies inside the project; absolute paths from older files still work.
    return CompileRecord(
        id=UUID(data["id"]),
        project_folder=project_folder,
        doc_id=data["doc_id"],
        engine=EngineType(data["engine"]),
        status=CompileStatus(data["status"]),
        started_at=_parse_dt(data["started_at"]),
        finished_at=_parse_dt(data["finished_at"]) if data.get("finished_at") else None,
        log=data.get("log", ""),
        output_path=_deserialize_project_relative_path(data.get("output_path"), project_folder),
        check_results=[_deserialize_check_result(r) for r in data.get("check_results", [])],
        pages=data.get("pages"),
        words=data.get("words"),
        chars=data.get("chars"),
    )


def _serialize_project_relative_path(path: Path | None, project_folder: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(project_folder))
    except ValueError:
        return str(path)


def _deserialize_project_relative_path(value: str | None, project_folder: Path) -> Path | None:
    if value is None:
        return None
    p = Path(value)
    return p if p.is_absolute() else project_folder / p


def _serialize_check_result(result: CheckResult) -> dict[str, Any]:
    return {
        "rule_id": result.rule_id,
        "severity": result.severity,
        "message": result.message,
        "location": _serialize_check_location(result.location),
        "fix": _serialize_check_fix(result.fix),
    }


def _deserialize_check_result(data: dict[str, Any]) -> CheckResult:
    return CheckResult(
        rule_id=data["rule_id"],
        severity=CheckSeverity(data["severity"]),
        message=data["message"],
        location=_deserialize_check_location(data.get("location")),
        fix=_deserialize_check_fix(data.get("fix")),
    )


def _serialize_check_fix(fix: CheckFix | None) -> dict[str, Any] | None:
    if fix is None:
        return None
    return {
        "file": fix.file,
        "search": fix.search,
        "replace": fix.replace,
        "line": fix.line,
        "title": fix.title,
    }


def _deserialize_check_fix(data: dict[str, Any] | None) -> CheckFix | None:
    if data is None:
        return None
    return CheckFix(
        file=data["file"],
        search=data["search"],
        replace=data["replace"],
        line=data.get("line"),
        title=data.get("title"),
    )


def _serialize_check_location(loc: CheckLocation | None) -> dict[str, Any] | None:
    if loc is None:
        return None
    return {"file": loc.file, "line": loc.line}


def _deserialize_check_location(data: dict[str, Any] | None) -> CheckLocation | None:
    if data is None:
        return None
    return CheckLocation(file=data["file"], line=data.get("line"))


# ---------------------------------------------------------------------------
# ChangeLogEntry
# ---------------------------------------------------------------------------


def serialize_changelog_entry(entry: ChangeLogEntry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "at": entry.at.isoformat(),
        "kind": entry.kind,
        "doc_id": entry.doc_id,
        "summary": entry.summary,
        "note": entry.note,
    }


def deserialize_changelog_entry(data: dict[str, Any]) -> ChangeLogEntry:
    return ChangeLogEntry(
        id=UUID(data["id"]),
        at=_parse_dt(data["at"]),
        kind=ChangeLogKind(data["kind"]),
        doc_id=data.get("doc_id"),
        summary=data["summary"],
        note=data.get("note"),
    )


# ---------------------------------------------------------------------------
# PackSubmissionRecord
# ---------------------------------------------------------------------------


def serialize_pack_submission_record(record: PackSubmissionRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "profile_id": record.profile_id,
        "created_at": record.created_at.isoformat(),
        "doc_items": [{"doc_id": item.doc_id, "signatures": list(item.signatures)} for item in record.doc_items],
        "extra_items": [
            {"source": item.source, "output_name": item.output_name, "format": item.format}
            for item in record.extra_items
        ],
        "output_path": _serialize_project_relative_path(record.output_path, record.project_folder),
        "output_dir": (
            _serialize_project_relative_path(record.output_dir, record.project_folder)
            if record.output_dir is not None
            else None
        ),
        "archive_format": record.archive_format,
    }


def deserialize_pack_submission_record(data: dict[str, Any], project_folder: Path) -> PackSubmissionRecord:
    output_path = _deserialize_project_relative_path(data.get("output_path"), project_folder)
    if output_path is None:
        raise ValueError("PackSubmissionRecord.output_path is required")
    output_dir = _deserialize_project_relative_path(data.get("output_dir"), project_folder)
    return PackSubmissionRecord(
        id=UUID(data["id"]),
        project_folder=project_folder,
        profile_id=data["profile_id"],
        created_at=_parse_dt(data["created_at"]),
        doc_items=[
            SubmissionDocItem(
                doc_id=item["doc_id"],
                signatures=tuple(item.get("signatures", [])),
            )
            for item in data.get("doc_items", [])
        ],
        extra_items=[
            ExtraSubmissionItem(
                source=item["source"],
                output_name=item["output_name"],
                format=item.get("format"),
            )
            for item in data.get("extra_items", [])
        ],
        output_path=output_path,
        output_dir=output_dir,
        archive_format=data.get("archive_format", "zip"),
    )


# ---------------------------------------------------------------------------
# SignaturesState
# ---------------------------------------------------------------------------


def serialize_signatures_state(state: SignaturesState) -> dict[str, Any]:
    return {
        "slots": {
            slot_id: {
                "png_path": slot.png_path,
                "natural_width_px": slot.natural_width_px,
                "natural_height_px": slot.natural_height_px,
                "signing_identity_id": slot.signing_identity_id,
                "sign_mode": slot.sign_mode.value,
                "sign_reason": slot.sign_reason,
            }
            for slot_id, slot in state.slots.items()
        },
        "placements": {
            doc_id: {
                slot_id: {
                    "enabled": placement.enabled,
                    "page": placement.page,
                    "x_mm": placement.x_mm,
                    "y_mm": placement.y_mm,
                    "width_mm": placement.width_mm,
                    "sign_date": placement.sign_date,
                }
                for slot_id, placement in slot_map.items()
            }
            for doc_id, slot_map in state.placements.items()
        },
    }


def deserialize_signatures_state(data: dict[str, Any]) -> SignaturesState:  # noqa: C901
    slots_raw = data.get("slots", {})
    placements_raw = data.get("placements", {})
    if not isinstance(slots_raw, dict) or not isinstance(placements_raw, dict):
        return SignaturesState.empty()
    slots: dict[str, SignatureSlot] = {}
    for slot_id, slot_data in slots_raw.items():
        if not isinstance(slot_data, dict):
            continue
        try:
            sign_mode = SignMode(slot_data.get("sign_mode", SignMode.image.value))
        except ValueError:
            sign_mode = SignMode.image
        slots[slot_id] = SignatureSlot(
            png_path=slot_data.get("png_path"),
            natural_width_px=slot_data.get("natural_width_px"),
            natural_height_px=slot_data.get("natural_height_px"),
            signing_identity_id=slot_data.get("signing_identity_id"),
            sign_mode=sign_mode,
            sign_reason=str(slot_data.get("sign_reason", "")),
        )
    placements: dict[str, dict[str, SignaturePlacement]] = {}
    for doc_id, slot_map in placements_raw.items():
        if not isinstance(slot_map, dict):
            continue
        doc_placements: dict[str, SignaturePlacement] = {}
        for slot_id, placement_data in slot_map.items():
            if not isinstance(placement_data, dict):
                continue
            sign_date = placement_data.get("sign_date")
            doc_placements[slot_id] = SignaturePlacement(
                enabled=bool(placement_data.get("enabled", False)),
                page=int(placement_data.get("page", 1)),
                x_mm=float(placement_data.get("x_mm", 0.0)),
                y_mm=float(placement_data.get("y_mm", 0.0)),
                width_mm=float(placement_data.get("width_mm", 50.0)),
                sign_date=str(sign_date) if sign_date else None,
            )
        placements[doc_id] = doc_placements
    return SignaturesState(slots=slots, placements=placements)


# ---------------------------------------------------------------------------
# FormState (generic pack-driven form answers)
# ---------------------------------------------------------------------------


def serialize_form_state(state: FormState) -> dict[str, Any]:
    return {
        "schema_version": state.schema_version,
        "completed": state.completed,
        "answers": state.answers,
    }


def deserialize_form_state(data: dict[str, Any]) -> FormState:
    raw_answers = data.get("answers", {})
    answers = raw_answers if isinstance(raw_answers, dict) else {}
    return FormState(
        schema_version=int(data.get("schema_version", 1)),
        completed=bool(data.get("completed", False)),
        answers=answers,
    )


def migrate_legacy_ai_usage(data: dict[str, Any]) -> FormState:  # noqa: C901 — one-off legacy mapping, flat by design
    """Lift a pre-engine `.hse-studio/ai-usage.json` blob into a FormState.

    The legacy shape stored a flat `entries: [{tool, usage_type, scope}]` list,
    and the old frontend smuggled extra structured state in via synthetic
    entries with magic `tool` values (`_meta_pct`, `_meta_details`) and prefixed
    tools (`tool:<id>`, `use:<id>`). This maps all of that onto the new keyed
    answers for the `ai_declaration` form so existing projects don't lose data
    on first open. The magic-prefix scheme is retired here, not carried forward.
    """
    answers: dict[str, Any] = {}
    table_rows: list[dict[str, str]] = []
    tools: list[str] = []
    uses: list[str] = []

    for entry in data.get("entries", []):
        if not isinstance(entry, dict):
            continue
        tool = str(entry.get("tool", ""))
        usage_type = str(entry.get("usage_type", ""))
        scope = entry.get("scope")
        if tool == "_meta_pct":
            with contextlib.suppress(TypeError, ValueError):
                answers["pct"] = int(float(usage_type or scope or 0))
        elif tool == "_meta_details":
            answers["details"] = usage_type or (scope or "")
        elif tool.startswith("tool:"):
            tools.append(tool[len("tool:") :])
        elif tool.startswith("use:"):
            uses.append(tool[len("use:") :])
        elif tool or usage_type or scope:
            table_rows.append({"tool": tool, "version": "", "kind": usage_type, "scope": str(scope or "")})

    if table_rows:
        answers["usage_table"] = table_rows
    if tools:
        answers["tools"] = tools
    if uses:
        answers["uses"] = uses
    # A legacy declaration with any tool data implies "used AI"; an empty one
    # with completed=True is the "did not use" branch.
    if table_rows or tools:
        answers.setdefault("used_ai", "yes")

    return FormState(
        schema_version=1,
        completed=bool(data.get("completed", False)),
        answers=answers,
    )


# ---------------------------------------------------------------------------
# AI agent chat (ChatSession / ChatMessage / AgentRunRecord / ChatSummaryBlock)
# ---------------------------------------------------------------------------


def _serialize_token_usage(usage: TokenUsage | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_input_tokens": usage.cache_read_input_tokens,
        "cache_creation_input_tokens": usage.cache_creation_input_tokens,
    }


def _deserialize_token_usage(data: dict[str, Any] | None) -> TokenUsage | None:
    if not data:
        return None
    return TokenUsage(
        input_tokens=int(data.get("input_tokens", 0)),
        output_tokens=int(data.get("output_tokens", 0)),
        cache_read_input_tokens=int(data.get("cache_read_input_tokens", 0)),
        cache_creation_input_tokens=int(data.get("cache_creation_input_tokens", 0)),
    )


def _serialize_content_block(block: ChatContentBlock) -> dict[str, Any]:
    return {
        "kind": str(block.kind),
        "text": block.text,
        "call_id": block.call_id,
        "tool_name": block.tool_name,
        "args": block.args,
        "result": block.result,
        "is_error": block.is_error,
    }


def _deserialize_content_block(data: dict[str, Any]) -> ChatContentBlock:
    raw_args = data.get("args", {})
    return ChatContentBlock(
        kind=ChatContentKind(data["kind"]),
        text=data.get("text"),
        call_id=data.get("call_id"),
        tool_name=data.get("tool_name"),
        args=raw_args if isinstance(raw_args, dict) else {},
        result=data.get("result"),
        is_error=bool(data.get("is_error", False)),
    )


def serialize_chat_session(session: ChatSession) -> dict[str, Any]:
    # project_folder is the on-disk location, NOT serialized (mirrors CompileRecord).
    return {
        "id": str(session.id),
        "title": session.title,
        "doc_id": session.doc_id,
        "project_id": str(session.project_id) if session.project_id else None,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "archived": session.archived,
        "default_provider_id": str(session.default_provider_id) if session.default_provider_id else None,
        "default_model": session.default_model,
        "persona": session.persona,
        "persona_instructions": session.persona_instructions,
        "message_count": session.message_count,
        "last_run_id": str(session.last_run_id) if session.last_run_id else None,
        "compacted_through_seq": session.compacted_through_seq,
        "summary_count": session.summary_count,
        "estimated_context_tokens": session.estimated_context_tokens,
    }


def deserialize_chat_session(data: dict[str, Any], project_folder: Path) -> ChatSession:
    return ChatSession(
        id=UUID(data["id"]),
        project_folder=project_folder,
        title=data.get("title", ""),
        doc_id=data.get("doc_id"),
        project_id=UUID(data["project_id"]) if data.get("project_id") else None,
        created_at=_parse_dt(data["created_at"]),
        updated_at=_parse_dt(data["updated_at"]),
        archived=bool(data.get("archived", False)),
        default_provider_id=UUID(data["default_provider_id"]) if data.get("default_provider_id") else None,
        default_model=data.get("default_model"),
        persona=data.get("persona"),
        persona_instructions=data.get("persona_instructions"),
        message_count=int(data.get("message_count", 0)),
        last_run_id=UUID(data["last_run_id"]) if data.get("last_run_id") else None,
        compacted_through_seq=int(data.get("compacted_through_seq", -1)),
        summary_count=int(data.get("summary_count", 0)),
        estimated_context_tokens=int(data.get("estimated_context_tokens", 0)),
    )


def serialize_chat_message(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "session_id": str(message.session_id),
        "run_id": str(message.run_id) if message.run_id else None,
        "seq": message.seq,
        "role": str(message.role),
        "blocks": [_serialize_content_block(b) for b in message.blocks],
        "created_at": message.created_at.isoformat(),
        "model": message.model,
        "provider_id": str(message.provider_id) if message.provider_id else None,
        "usage": _serialize_token_usage(message.usage),
        "approval": str(message.approval),
        "compacted": message.compacted,
    }


def deserialize_chat_message(data: dict[str, Any]) -> ChatMessage:
    return ChatMessage(
        id=UUID(data["id"]),
        session_id=UUID(data["session_id"]),
        run_id=UUID(data["run_id"]) if data.get("run_id") else None,
        seq=int(data["seq"]),
        role=ChatMessageRole(data["role"]),
        blocks=[_deserialize_content_block(b) for b in data.get("blocks", [])],
        created_at=_parse_dt(data["created_at"]),
        model=data.get("model"),
        provider_id=UUID(data["provider_id"]) if data.get("provider_id") else None,
        usage=_deserialize_token_usage(data.get("usage")),
        approval=ToolApprovalDecision(data.get("approval", "auto")),
        compacted=bool(data.get("compacted", False)),
    )


def serialize_agent_run(record: AgentRunRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "session_id": str(record.session_id),
        "status": str(record.status),
        "created_at": record.created_at.isoformat(),
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "finished_at": record.finished_at.isoformat() if record.finished_at else None,
        "trigger_seq": record.trigger_seq,
        "first_emitted_seq": record.first_emitted_seq,
        "last_emitted_seq": record.last_emitted_seq,
        "model": record.model,
        "provider_id": str(record.provider_id) if record.provider_id else None,
        "iterations": record.iterations,
        "usage": _serialize_token_usage(record.usage),
        "error": record.error,
        "diagnostics": record.diagnostics,
    }


def deserialize_agent_run(data: dict[str, Any], project_folder: Path) -> AgentRunRecord:
    return AgentRunRecord(
        id=UUID(data["id"]),
        session_id=UUID(data["session_id"]),
        project_folder=project_folder,
        status=AgentRunStatus(data["status"]),
        created_at=_parse_dt(data["created_at"]),
        started_at=_parse_dt(data["started_at"]) if data.get("started_at") else None,
        finished_at=_parse_dt(data["finished_at"]) if data.get("finished_at") else None,
        trigger_seq=int(data.get("trigger_seq", 0)),
        first_emitted_seq=data.get("first_emitted_seq"),
        last_emitted_seq=data.get("last_emitted_seq"),
        model=data.get("model"),
        provider_id=UUID(data["provider_id"]) if data.get("provider_id") else None,
        iterations=int(data.get("iterations", 0)),
        usage=_deserialize_token_usage(data.get("usage")),
        error=data.get("error"),
        diagnostics=data.get("diagnostics") or [],
    )


def serialize_chat_summary(summary: ChatSummaryBlock) -> dict[str, Any]:
    return {
        "id": str(summary.id),
        "session_id": str(summary.session_id),
        "covers_from_seq": summary.covers_from_seq,
        "covers_to_seq": summary.covers_to_seq,
        "created_at": summary.created_at.isoformat(),
        "text": summary.text,
        "model": summary.model,
        "token_estimate": summary.token_estimate,
    }


def deserialize_chat_summary(data: dict[str, Any]) -> ChatSummaryBlock:
    return ChatSummaryBlock(
        id=UUID(data["id"]),
        session_id=UUID(data["session_id"]),
        covers_from_seq=int(data["covers_from_seq"]),
        covers_to_seq=int(data["covers_to_seq"]),
        created_at=_parse_dt(data["created_at"]),
        text=data.get("text", ""),
        model=data.get("model"),
        token_estimate=data.get("token_estimate"),
    )
