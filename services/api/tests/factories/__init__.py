from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from hse_doc_studio.core.catalog import (
    CheckRule,
    ChecksVersionConfig,
    DocumentDefinition,
    EngineConfig,
    PackSubmissionConfig,
    SignaturesConfig,
    TemplateVersion,
)
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import (
    CheckEngine,
    CheckSeverity,
    DocumentStatus,
    EngineType,
    Lang,
    ProjectKind,
    ProjectStaffing,
    TemplateVersionStatus,
)
from hse_doc_studio.core.value_objects import Author, ChecksOverride, CustomFileOverride, ProjectLock


def make_check_rule(
    rule_id: str = "r1",
    applies_to: list[str] | str = "*",
    category: str | None = None,
    severity: CheckSeverity = CheckSeverity.warn,
    engine: CheckEngine = CheckEngine.regex,
    params: dict[str, Any] | None = None,
    title: dict[str, str] | None = None,
) -> CheckRule:
    return CheckRule(
        id=rule_id,
        title=title or {"ru": "Test rule"},
        description={"ru": ""},
        category=category,
        applies_to=applies_to,
        default_severity=severity,
        engine=engine,
        params=params or {},
    )


def make_checks_version_config(
    disabled_categories: tuple[str, ...] = (),
    disabled: tuple[str, ...] = (),
    severity_override: dict[str, CheckSeverity] | None = None,
) -> ChecksVersionConfig:
    return ChecksVersionConfig(
        disabled_categories=disabled_categories,
        disabled=disabled,
        severity_override=severity_override or {},
    )


def make_document_definition(
    doc_id: str = "vkr",
    source_file: str | None = None,
    output_file: str | None = None,
    output_name: dict[str, str] | None = None,
    required: bool = True,
    variants: tuple = (),
) -> DocumentDefinition:
    return DocumentDefinition(
        id=doc_id,
        name={"ru": doc_id},
        code={"ru": doc_id.upper()},
        source_file=source_file or (f"{doc_id}/main.tex" if not variants else None),
        output_file=output_file or (f"{doc_id}/main.pdf" if not variants else None),
        output_name=output_name or {"ru": f"{doc_id.upper()}.pdf"},
        gost_ref=None,
        required=required,
        checks=ChecksOverride(),
        variants=variants,
    )


def make_template_version(
    pack_id: str = "hse-cs-se",
    template_id: str = "vkr",
    version: str = "1.0",
    documents: tuple = (),
    rules: tuple = (),
) -> TemplateVersion:
    return TemplateVersion(
        pack_id=pack_id,
        template_id=template_id,
        version=version,
        status=TemplateVersionStatus.stable,
        released_at=date(2026, 1, 1),
        summary={"ru": "Test version"},
        engine_config=EngineConfig(
            default=EngineType.xelatex,
            allowed=(EngineType.xelatex,),
            passes=2,
            flags="",
        ),
        required_tex_packages=(),
        documents=documents,
        meta_fields={},
        signatures_config=SignaturesConfig(slots=()),
        pack_submission=PackSubmissionConfig(profiles=()),
        checks_config=ChecksVersionConfig(disabled_categories=(), disabled=(), severity_override={}),
        rules=rules,
    )


def make_custom_file_override(
    original_filename: str = "file.docx",
    stored_path: str = "tz/_custom/file.docx",
    ext: str = ".docx",
    convert_to_pdf_at_package: bool | None = None,
) -> CustomFileOverride:
    return CustomFileOverride(
        original_filename=original_filename,
        stored_path=stored_path,
        ext=ext,
        uploaded_at="2026-07-20T12:00:00+00:00",
        convert_to_pdf_at_package=convert_to_pdf_at_package,
    )


def make_document(
    doc_id: str = "vkr",
    status: DocumentStatus = DocumentStatus.draft,
    chosen_variant: str | None = None,
    custom_file: CustomFileOverride | None = None,
) -> Document:
    return Document(
        id=doc_id,
        status=status,
        chosen_variant=chosen_variant,
        last_compile_id=None,
        checks_override=ChecksOverride(),
        custom_file=custom_file,
    )


def make_project(
    folder: Path | None = None,
    name: str = "Test Project",
    documents: list[Document] | None = None,
) -> Project:
    now = datetime.now(tz=timezone.utc)
    return Project(
        id=uuid4(),
        name=name,
        folder=folder or Path("/tmp/test-project"),
        lock=ProjectLock(
            pack_id="hse-cs-se",
            template_id="vkr",
            version="1.0",
            engine=EngineType.xelatex,
        ),
        kind=ProjectKind.research,
        staffing=ProjectStaffing.solo,
        lang=Lang.ru,
        authors=[Author(name="Test Author")],
        meta={},
        supervisor=None,
        co_supervisor=None,
        documents=documents or [],
        created_at=now,
        updated_at=now,
    )


def project_api_payload(folder: str) -> dict[str, Any]:
    return {
        "name": "Test VKR",
        "folder": folder,
        "pack_id": "hse-cs-se",
        "template_id": "vkr",
        "version": "2026.1",
        "engine": "xelatex",
        "kind": "research",
        "staffing": "solo",
        "lang": "ru",
        "authors": [{"name": "Ivan Ivanov", "group": None, "email": None}],
        "supervisor": None,
        "co_supervisor": None,
        "meta": {},
    }
