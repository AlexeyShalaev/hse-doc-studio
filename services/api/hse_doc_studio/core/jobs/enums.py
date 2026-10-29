from __future__ import annotations

from enum import IntEnum, StrEnum


class JobKind(StrEnum):
    # Остальные виды добавляют слайсы своих семейств, по одному на вид.
    compile = "compile"
    office_convert = "office.convert"
    verify_detached = "signature.verify_detached"
    pack_submission = "pack.submission"


class JobStatus(StrEnum):
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"


class JobErrorCategory(StrEnum):
    # Отображаются на ValueError / NotFoundError / недоступность / внутреннюю ошибку,
    # то есть на 400 / 404 / 409-503 / 500 в API.
    invalid_input = "invalid_input"
    not_found = "not_found"
    unavailable = "unavailable"
    internal = "internal"


class JobState(StrEnum):
    """Жизненный цикл записи очереди; `JobStatus` остаётся итогом результата и совпадает с терминальными значениями."""

    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"

    @property
    def is_terminal(self) -> bool:
        return self not in (JobState.queued, JobState.running)

    @classmethod
    def of_status(cls, status: JobStatus) -> JobState:
        return cls(status.value)


class JobPriorityClass(IntEnum):
    """Класс очереди: меньшее число берут раньше; внутри класса порядок решает справедливая очередь."""

    interactive = 0
    checks = 1
    batch = 2
    # Задел под поведение сверх квоты на этапе 6.
    low = 3


class RunnerErrorCode(StrEnum):
    """Закрытый список кодов ошибок протокола раннера и причин, по которым сборка не дошла до результата."""

    runner_lost = "runner_lost"
    superseded = "superseded"
    superseded_by = "superseded_by"
    no_runner = "no_runner"
    quota = "quota"
    stale_attempt = "stale_attempt"
    job_not_found = "job_not_found"
    job_not_running = "job_not_running"
    blob_forbidden = "blob_forbidden"
    blob_missing = "blob_missing"
    artifact_invalid = "artifact_invalid"
    runner_unauthorized = "runner_unauthorized"
    runner_disabled = "runner_disabled"
    job_token_invalid = "job_token_invalid"  # noqa: S105
    runner_protocol_unsupported = "runner_protocol_unsupported"
