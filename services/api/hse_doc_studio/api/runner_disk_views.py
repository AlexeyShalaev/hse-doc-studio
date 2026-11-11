"""Ответы «Диска» раннера (9.1) из результатов `RunnerDiskUC`: общие для админки и «Моих раннеров»."""

from __future__ import annotations

from fastapi import Request

from hse_doc_studio.api.schemas import runner_disk as rd
from hse_doc_studio.api.schemas.runner import CommandProgressBody, RunnerDiskReportBody
from hse_doc_studio.core.jobs.codec import encode
from hse_doc_studio.core.jobs.disk import DISK_MIN_RUNNER_VERSION, DiskCleanupPayload
from hse_doc_studio.use_cases.jobs.runner_disk import (
    DiskCommandView,
    PersonName,
    RunnerDiskBrief,
    RunnerDiskState,
    RunnerDiskSummary,
    RunnerDiskUC,
)

NO_STORE = {"Cache-Control": "no-store"}


async def runner_disk_uc(request: Request) -> RunnerDiskUC:
    return await request.state.dishka_container.get(RunnerDiskUC)


def _person(person: PersonName | None) -> rd.RunnerDiskPerson | None:
    return rd.RunnerDiskPerson(id=person.id, name=person.name) if person is not None else None


def disk_command(view: DiskCommandView) -> rd.RunnerDiskCommand:
    command = view.command
    payload = command.payload if isinstance(command.payload, DiskCleanupPayload) else None
    return rd.RunnerDiskCommand(
        id=str(command.id),
        kind=command.kind.value,
        state=command.state.value,
        targets=[target.value for target in payload.targets] if payload is not None else [],
        include_rollback=payload.include_rollback if payload is not None else False,
        created_at=command.created_at,
        finished_at=command.finished_at,
        created_by=_person(view.created_by),
        progress=CommandProgressBody.model_validate(encode(command.progress)) if command.progress is not None else None,
    )


def disk_view(state: RunnerDiskState) -> rd.RunnerDiskView:
    stored = state.stored
    return rd.RunnerDiskView(
        runner_id=state.runner.id,
        supported=state.supported,
        reason=None if state.supported else "outdated",
        min_version=DISK_MIN_RUNNER_VERSION,
        online=state.online,
        last_seen_at=state.runner.last_seen_at,
        report=RunnerDiskReportBody.model_validate(encode(stored.report)) if stored is not None else None,
        received_at=stored.received_at if stored is not None else None,
        stale=state.stale,
        command=disk_command(state.command) if state.command is not None else None,
        measuring=state.measuring,
        can_clean=state.can_clean,
        can_include_rollback=state.can_include_rollback,
        personal_owner=_person(state.personal_owner),
    )


def disk_brief(brief: RunnerDiskBrief | None) -> rd.RunnerDiskBrief | None:
    if brief is None:
        return None
    return rd.RunnerDiskBrief(
        supported=brief.supported, cleanable_bytes=brief.cleanable_bytes, measured_at=brief.measured_at
    )


def disk_summary(summary: RunnerDiskSummary) -> rd.RunnerDiskSummary:
    return rd.RunnerDiskSummary(
        reporting=summary.reporting,
        outdated=summary.outdated,
        min_version=DISK_MIN_RUNNER_VERSION,
        cleanable_bytes=summary.cleanable_bytes,
        top=[
            rd.RunnerDiskSummaryRunner(
                runner_id=row.runner_id, name=row.name, cleanable_bytes=row.cleanable_bytes, measured_at=row.measured_at
            )
            for row in summary.top
        ],
    )
