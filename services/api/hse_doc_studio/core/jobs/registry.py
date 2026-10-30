from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from hse_doc_studio.core.jobs.base import JobPayload, JobResultData
from hse_doc_studio.core.jobs.entities import CompileJobPayload, CompileResult
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass
from hse_doc_studio.core.jobs.office import OfficeConvertPayload, OfficeConvertResult
from hse_doc_studio.core.jobs.pack import PackResult, PackSubmissionPayload
from hse_doc_studio.core.jobs.policy import JobKindPolicy
from hse_doc_studio.core.jobs.relay import AiRelayPayload, AiRelayResult
from hse_doc_studio.core.jobs.verify import VerifyDetachedPayload, VerifyDetachedResult


@dataclass(frozen=True)
class JobKindSpec:
    kind: JobKind
    payload_cls: type[JobPayload]
    result_cls: type[JobResultData]
    policy: JobKindPolicy


def build_job_kinds() -> tuple[JobKindSpec, ...]:
    # Список явный: слайс каждого семейства добавляет сюда одну строку.
    return (
        JobKindSpec(
            kind=JobKind.compile,
            payload_cls=CompileJobPayload,
            result_cls=CompileResult,
            policy=JobKindPolicy(
                streams_log=True,
                counts_as_active=True,
                blocks_folder_ops=True,
                priority_class=JobPriorityClass.interactive,
                retryable=True,
                max_attempts=2,
                default_timeout_s=600.0,
                personal_runner_allowed=True,
            ),
        ),
        JobKindSpec(
            kind=JobKind.office_convert,
            payload_cls=OfficeConvertPayload,
            result_cls=OfficeConvertResult,
            policy=JobKindPolicy(
                awaitable=True,
                detachable=True,
                idempotent=True,
                priority_class=JobPriorityClass.checks,
                retryable=True,
                max_attempts=2,
                default_timeout_s=180.0,
                personal_runner_allowed=True,
            ),
        ),
        JobKindSpec(
            kind=JobKind.verify_detached,
            payload_cls=VerifyDetachedPayload,
            result_cls=VerifyDetachedResult,
            policy=JobKindPolicy(
                awaitable=True,
                idempotent=True,
                priority_class=JobPriorityClass.checks,
                retryable=True,
                max_attempts=2,
                default_timeout_s=120.0,
            ),
        ),
        JobKindSpec(
            kind=JobKind.pack_submission,
            payload_cls=PackSubmissionPayload,
            result_cls=PackResult,
            # Один пакет за раз: так было неявно, и глобальный реестр шрифтов reportlab не гоняется.
            # Работа идет в потоке, цикл свободен, поэтому перенос проекта и самообновление
            # должны видеть идущую сборку: раньше их не пускала синхронность populate_dir.
            policy=JobKindPolicy(
                awaitable=True,
                embedded_concurrency=1,
                counts_as_active=True,
                blocks_folder_ops=True,
                priority_class=JobPriorityClass.batch,
                retryable=True,
                max_attempts=2,
                default_timeout_s=300.0,
                personal_runner_allowed=True,
            ),
        ),
        JobKindSpec(
            kind=JobKind.ai_relay,
            payload_cls=AiRelayPayload,
            result_cls=AiRelayResult,
            # Идёт только на один раннер хозяина (маршрут pinned), а не на личные раннеры владельца проекта;
            # повтор съел бы уже отданную часть ответа модели.
            policy=JobKindPolicy(
                priority_class=JobPriorityClass.interactive,
                retryable=False,
                max_attempts=1,
                default_timeout_s=900.0,
                personal_runner_allowed=False,
            ),
        ),
    )


@cache
def _kinds_by_name() -> dict[JobKind, JobKindSpec]:
    return {spec.kind: spec for spec in build_job_kinds()}


def job_kind_spec(kind: JobKind) -> JobKindSpec:
    try:
        return _kinds_by_name()[kind]
    except KeyError:
        raise ValueError(f"unregistered job kind: {kind}") from None
