from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity, DetachedFormat, DetachedVerdict, EngineType, Lang
from hse_doc_studio.core.jobs.entities import CheckPlan, CompileJobPayload, CompileResult, JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.files import ArtifactRef, InlineBlob, ManifestFile
from hse_doc_studio.core.jobs.office import (
    OfficeConvertPayload,
    OfficeConvertReason,
    OfficeConvertResult,
    OfficeConvertStatus,
)
from hse_doc_studio.core.jobs.verify import (
    OpenPgpTrust,
    OpenPgpTrustMode,
    TrustBundle,
    VerifyDetachedPayload,
    VerifyDetachedResult,
)
from hse_doc_studio.core.signatures.verification import VerifiedSignature
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


def make_verify_payload(*, mode: OpenPgpTrustMode = OpenPgpTrustMode.runner_home) -> VerifyDetachedPayload:
    return VerifyDetachedPayload(
        pdf=ManifestFile(path="tz/Аннотация.pdf", sha256="ef" * 32, size=2048),
        signature=InlineBlob.from_bytes(b"\x30\x82signature\x00\xff"),
        trust=TrustBundle(
            roots=(InlineBlob.from_bytes(b"root-der"),),
            intermediates=(InlineBlob.from_bytes(b"inter-1"), InlineBlob.from_bytes(b"inter-2")),
            openpgp=OpenPgpTrust(
                mode=mode,
                keys=(InlineBlob.from_bytes(b"-----BEGIN PGP PUBLIC KEY BLOCK-----"),) if mode == "inline" else (),
                digest="ab12" if mode == "inline" else "",
            ),
        ),
    )


def make_verify_spec(*, local_root: object = None) -> JobSpec:
    return JobSpec(
        id=JOB_ID,
        kind=JobKind.verify_detached,
        tags=frozenset({"verify"}),
        project_id=PROJECT_ID,
        actor=Actor.user("u1", "Иван", "ivan@example.com"),
        locale=Lang.ru,
        payload=make_verify_payload(),
        local_root=local_root,  # type: ignore[arg-type]
    )


def make_verify_result() -> JobResult:
    return JobResult(
        status=JobStatus.succeeded,
        data=VerifyDetachedResult(
            signature=VerifiedSignature(
                format=DetachedFormat.cms,
                verdict=DetachedVerdict.valid,
                signer="Иванов Иван Иванович",
                signer_id="cd" * 32,
                issuer="Тестовый УЦ",
                algorithm="GOST R 34.10-2012 / Streebog-256",
                signed_at="2026-10-01T12:00:00+00:00",
                not_before="2020-01-01T00:00:00+00:00",
                not_after="2049-01-01T00:00:00+00:00",
                chain="untrusted_root",
                root_subject="Тестовый корень",
                root_fingerprint="12" * 32,
                extension=".p7s",
                notes=("chain_untrusted_root", "no_revocation_check"),
            )
        ),
    )
