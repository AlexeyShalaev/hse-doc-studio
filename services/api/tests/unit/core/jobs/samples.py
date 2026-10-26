from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity, EngineType, Lang
from hse_doc_studio.core.jobs.entities import (
    CheckPlan,
    CompileJobPayload,
    CompileResult,
    JobResult,
    JobSpec,
    job_tags,
)
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.files import ArtifactRef, InlineBlob, ManifestFile, StampSpec
from hse_doc_studio.core.jobs.office import (
    OfficeConvertPayload,
    OfficeConvertReason,
    OfficeConvertResult,
    OfficeConvertStatus,
)
from hse_doc_studio.core.jobs.pack import (
    ArchiveFormat,
    PackEntry,
    PackEntryKind,
    PackResult,
    PackSkip,
    PackSubmissionPayload,
)
from hse_doc_studio.core.value_objects import CheckFix, CheckLocation, CheckResult

from tests.factories import make_check_rule

JOB_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = UUID("22222222-2222-4222-8222-222222222222")


def make_rule(rule_id: str = "gost/margins", *, applies_to: list[str] | str = "*") -> CheckRule:
    return make_check_rule(
        rule_id,
        applies_to,
        params={"pattern": r"\\geometry", "flags": ["i"], "min": 2.5, "strict": True, "extra": None},
        title={"ru": "Поля", "en": "Margins"},
    )


def make_compile_payload(*, needs_compile: bool = True, source_file: str = "tz/main.tex") -> CompileJobPayload:
    return CompileJobPayload(
        doc_id="tz",
        def_id="tz",
        source_file=source_file,
        engine=EngineType.xelatex,
        base_dir="",
        needs_compile=needs_compile,
        custom_mode=False,
        default_passes=5,
        check_plan=CheckPlan(
            rules_with_severity=(
                (make_rule(), CheckSeverity.err),
                (make_rule("gost/fonts", applies_to=["tz", "vkr"]), CheckSeverity.info),
            ),
            ignored_rule_ids=frozenset({"lt:TYPO", "gost/other"}),
            needs_languagetool=True,
        ),
    )


def make_compile_spec(*, local_root: object = None) -> JobSpec:
    return JobSpec(
        id=JOB_ID,
        kind=JobKind.compile,
        tags=frozenset({"tex"}),
        project_id=PROJECT_ID,
        actor=Actor.user("u1", "Иван", "ivan@example.com"),
        locale=Lang.en,
        payload=make_compile_payload(),
        local_root=local_root,  # type: ignore[arg-type]
    )


def make_compile_result() -> JobResult:
    return JobResult(
        status=JobStatus.succeeded,
        data=CompileResult(
            build_ok=True,
            check_results=(
                CheckResult(
                    rule_id="gost/margins",
                    severity=CheckSeverity.warn,
                    message="Поля меньше 2.5 см",
                    location=CheckLocation(file="tz/main.tex", line=12),
                    fix=CheckFix(file="tz/main.tex", search="a", replace="b", line=12, title="Исправить"),
                ),
                CheckResult(rule_id="lt:TYPO", severity=CheckSeverity.info, message="m"),
            ),
            pages=7,
            words=1200,
            chars=9000,
            finished_at=datetime(2026, 10, 26, 9, 30, 15, 123456, tzinfo=timezone.utc),
        ),
    )


def make_office_payload(*, image: str | None = "gotenberg/gotenberg:8") -> OfficeConvertPayload:
    return OfficeConvertPayload(
        source=ManifestFile(path="tz/_custom/ТЗ.docx", sha256="ab" * 32, size=1234),
        output_path="tz/_custom/ТЗ.pdf",
        image=image,
        convert_timeout_s=45.5,
        want_pages=True,
        reason=OfficeConvertReason.save_refresh,
    )


def make_office_spec(*, local_root: object = None) -> JobSpec:
    return JobSpec(
        id=JOB_ID,
        kind=JobKind.office_convert,
        tags=frozenset({"office"}),
        project_id=PROJECT_ID,
        actor=Actor.user("u1", "Иван", "ivan@example.com"),
        locale=Lang.ru,
        payload=make_office_payload(),
        local_root=local_root,  # type: ignore[arg-type]
    )


def make_office_result() -> JobResult:
    return JobResult(
        status=JobStatus.succeeded,
        data=OfficeConvertResult(
            status=OfficeConvertStatus.ok,
            output=ArtifactRef(path="tz/_custom/ТЗ.pdf", sha256="cd" * 32, size=4321),
            pages=12,
        ),
    )


def make_pack_payload(*, archive_format: ArchiveFormat = ArchiveFormat.zip) -> PackSubmissionPayload:
    stamp = StampSpec(
        page=2,
        x_mm=20.5,
        y_mm=240.0,
        width_mm=40.0,
        png=ManifestFile(path=".hse-studio/signatures/ivan.png", sha256="ef" * 32, size=900),
        aspect_ratio=0.4,
        text=None,
        details=(("Сертификат", "ООО Ромашка"), ("Владелец", "Иван Иванов")),
        subtitle="Квалифицированная",
        date_label="Дата подписания",
        date_text="12.05.2026",
    )
    return PackSubmissionPayload(
        base_name="cp1-ivanov-20261026-093015-1a2b3c4d",
        profile_id="checkpoint-1",
        lang=Lang.ru,
        archive_format=archive_format,
        keep_folder=True,
        verify_manifest=True,
        entries=(
            PackEntry(
                kind=PackEntryKind.stamp_pdf,
                arcname="Аннотация.pdf",
                source=ManifestFile(path="annotation/annotation.pdf", sha256="ab" * 32, size=1234),
                stamps=(stamp,),
            ),
            PackEntry(
                kind=PackEntryKind.copy,
                arcname="Презентация.pptx",
                source=ManifestFile(path="presentation/presentation.pptx", sha256="12" * 32, size=77),
            ),
            PackEntry(kind=PackEntryKind.text, arcname="README.txt", text="Состав пакета\n"),
            PackEntry(kind=PackEntryKind.blob, arcname="public-key.asc", blob=InlineBlob.from_bytes(b"\x00key\xff")),
        ),
    )


def make_pack_spec(*, local_root: object = None) -> JobSpec:
    payload = make_pack_payload()
    return JobSpec(
        id=JOB_ID,
        kind=JobKind.pack_submission,
        tags=job_tags(JobKind.pack_submission, payload),
        project_id=PROJECT_ID,
        actor=Actor.user("u1", "Иван", "ivan@example.com"),
        locale=Lang.ru,
        payload=payload,
        local_root=local_root,  # type: ignore[arg-type]
    )


def make_pack_result() -> JobResult:
    return JobResult(
        status=JobStatus.succeeded,
        data=PackResult(
            archive=ArtifactRef(path="submissions/cp1.zip", sha256="34" * 32, size=5555),
            folder=ArtifactRef(path="submissions/cp1", sha256="56" * 32, size=0),
            written=("Аннотация.pdf", "README.txt"),
            skipped=(PackSkip(arcname="Презентация.pptx", reason="missing_source", detail="no such file"),),
        ),
    )
