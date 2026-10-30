"""Очередь задач на Postgres: `FOR UPDATE SKIP LOCKED`, справедливая очередь и аренды.

Порядок и правила те же, что у `InMemoryJobQueue`: числа считают чистые функции планировщика,
а выбор лучшей задачи делает один запрос с теми же условиями. Время приходит из инжектируемых часов,
`now()` базы нигде не используется, поэтому контрактный набор двигает часы одинаково для обеих реализаций.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, case, func, literal, null, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass, JobState, JobStatus, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError, StaleAttemptError
from hse_doc_studio.core.jobs.queue import (
    EnqueueOutcome,
    EnqueueRequest,
    ExpiredOutcome,
    Heartbeat,
    QueuedJob,
    RunnerRef,
)
from hse_doc_studio.core.jobs.registry import build_job_kinds
from hse_doc_studio.core.jobs.routing import (
    KEPT_FALLBACK_REASONS,
    JobRoute,
    ProjectBuildRunners,
    RouteReason,
    RunnerScope,
)
from hse_doc_studio.core.jobs.scheduler import AFFINITY_WAIT, QueueQuota, assign_vtime, retry_available
from hse_doc_studio.infra.db.orm.jobs import FairShareRow, JobQueueStateRow, JobRow, JobRunnerPollRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

# Ключ advisory-блокировки, которая выстраивает выдачу в очередь, когда действуют лимиты: иначе два раннера
# одновременно увидят свободное место у пользователя и оба возьмут его задачи сверх лимита.
_CAPS_LOCK_KEY = 0x4A4F4253  # "JOBS"
# Виды, которые может взять личный раннер владельца проекта (без проверки подписи и ретрансляции).
_PERSONAL_KINDS = sorted(spec.kind.value for spec in build_job_kinds() if spec.policy.personal_runner_allowed)
_KEPT_REASONS = sorted(reason.value for reason in KEPT_FALLBACK_REASONS)


def _uuid_or_none(value: str | None) -> UUID | None:
    try:
        return UUID(value) if value is not None else None
    except ValueError:
        return None


def _utcnow() -> datetime:
    return datetime.now(UTC)


def job_from_row(row: JobRow) -> QueuedJob:
    return QueuedJob(
        id=row.id,
        kind=JobKind(row.kind),
        project_id=row.project_id,
        user_id=row.user_id,
        org_id=row.org_id,
        tags=frozenset(row.tags),
        priority_class=JobPriorityClass(row.priority_class),
        vtime=row.vtime,
        queued_at=row.queued_at,
        state=JobState(row.state),
        attempt=row.attempt,
        max_attempts=row.max_attempts,
        timeout_s=row.timeout_s,
        payload=row.payload,
        coalesce_key=row.coalesce_key,
        affinity_runner_id=row.affinity_runner_id,
        runner_id=row.runner_id,
        lease_until=row.lease_until,
        started_at=row.started_at,
        cancel_requested=row.cancel_requested,
        finished_at=row.finished_at,
        result=row.result,
        error_code=row.error_code,
        seq=row.seq,
        route=JobRoute(row.route),
        route_owner_id=row.route_owner_id,
        personal_until=row.personal_until,
        target_runner_id=row.target_runner_id,
        runner_scope=RunnerScope(row.runner_scope) if row.runner_scope is not None else None,
        route_reason=RouteReason(row.route_reason) if row.route_reason is not None else None,
        vcost=row.vcost,
        timeout_personal_s=row.timeout_personal_s,
    )


def _cap_expression(default: int | None, *levels: tuple[Any, Mapping[UUID, int]]) -> ColumnElement[int] | None:
    """Предел конкретной задачи: переопределения по владельцам, затем значение установки; `None` без лимитов."""
    parts: list[Any] = [case(dict(caps), value=column, else_=null()) for column, caps in levels if caps]
    if default is not None:
        parts.append(literal(default))
    if not parts:
        return None
    return func.coalesce(*parts) if len(parts) > 1 else parts[0]


class PostgresJobQueue:
    def __init__(self, sessions: SessionProvider, clock: Callable[[], datetime] = _utcnow) -> None:
        self._sessions = sessions
        self._clock = clock

    async def enqueue(self, request: EnqueueRequest) -> EnqueueOutcome:
        now = self._clock()
        async with self._sessions.use() as session:
            # Строка пользователя блокируется до конца транзакции: его метки выдаются строго по очереди.
            user_vtime: float | None = None
            if request.fair_share:
                await session.execute(pg_insert(FairShareRow).values(user_id=request.user_id).on_conflict_do_nothing())
                user_vtime = (
                    await session.execute(
                        select(FairShareRow.vtime).where(FairShareRow.user_id == request.user_id).with_for_update()
                    )
                ).scalar_one()
            global_vtime = (await session.execute(select(JobQueueStateRow.global_vtime))).scalar_one()
            superseded: list[JobRow] = []
            if request.coalesce_key is not None:
                superseded = list(
                    (
                        await session.execute(
                            update(JobRow)
                            .where(JobRow.state == JobState.queued.value, JobRow.coalesce_key == request.coalesce_key)
                            .values(
                                state=JobState.cancelled.value,
                                finished_at=now,
                                error_code=RunnerErrorCode.superseded.value,
                            )
                            .returning(JobRow)
                            .execution_options(populate_existing=True)
                        )
                    ).scalars()
                )
                # Идущая сборка того же документа уже не нужна: раннер узнает об этом в heartbeat.
                await session.execute(
                    update(JobRow)
                    .where(JobRow.state == JobState.running.value, JobRow.coalesce_key == request.coalesce_key)
                    .values(cancel_requested=True)
                )
            if request.fair_share:
                vtime = assign_vtime(user_vtime, global_vtime, request.cost, request.weight)
                vcost = request.cost / request.weight
                await session.execute(
                    update(FairShareRow).where(FairShareRow.user_id == request.user_id).values(vtime=vtime)
                )
            else:
                # Без справедливости (ретрансляция ИИ): задача встаёт на текущее время, метка человека не тратится.
                vtime, vcost = global_vtime, 0.0
            row = JobRow(
                id=request.job_id,
                kind=request.kind.value,
                state=JobState.queued.value,
                project_id=request.project_id,
                user_id=request.user_id,
                org_id=request.org_id,
                tags=sorted(request.tags),
                priority_class=int(request.priority_class),
                vtime=vtime,
                queued_at=now,
                attempt=0,
                max_attempts=request.max_attempts,
                timeout_s=request.timeout_s,
                payload=request.payload,
                coalesce_key=request.coalesce_key,
                affinity_runner_id=request.affinity_runner_id,
                cancel_requested=False,
                route=request.route.value,
                route_owner_id=request.route_owner_id,
                personal_until=request.personal_until,
                target_runner_id=request.target_runner_id,
                route_reason=request.route_reason.value if request.route_reason is not None else None,
                vcost=vcost,
                timeout_personal_s=request.timeout_personal_s,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return EnqueueOutcome(job=job_from_row(row), superseded=tuple(job_from_row(r) for r in superseded))

    async def claim(self, runner: RunnerRef, *, lease_s: float, quota: QueueQuota | None = None) -> QueuedJob | None:
        now = self._clock()
        limits = quota or QueueQuota()
        personal = runner.scope is RunnerScope.personal
        async with self._sessions.use() as session:
            await session.execute(
                pg_insert(JobRunnerPollRow)
                .values(runner_id=runner.id, last_seen_at=now, concurrency=runner.concurrency)
                .on_conflict_do_update(
                    index_elements=[JobRunnerPollRow.runner_id],
                    set_={"last_seen_at": now, "concurrency": runner.concurrency},
                )
            )
            if personal:
                # Личный раннер квот установки не тратит: блокировка квот ему не нужна.
                stmt = self._personal_candidate(runner)
            else:
                if not runner.accept_jobs:
                    return None
                if not limits.is_unlimited:
                    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CAPS_LOCK_KEY})
                stmt = self._best_candidate(runner, limits, now, lease_s)
            if stmt is None:
                return None
            row: JobRow | None = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            row.state = JobState.running.value
            row.attempt += 1
            row.runner_id = runner.id
            row.lease_until = now + timedelta(seconds=lease_s)
            row.started_at = now
            if personal:
                await self._take_personal(session, row)
            else:
                await self._take_shared(session, row)
            return job_from_row(row)

    @staticmethod
    async def _take_personal(session: AsyncSession, row: JobRow) -> None:
        row.runner_scope = RunnerScope.personal.value
        row.route_reason = (
            RouteReason.pinned.value if row.route == JobRoute.pinned.value else RouteReason.personal.value
        )
        if row.timeout_personal_s is not None:
            # Предел без квоты на время личной попытки; предел с квотой ждёт возврата в очередь.
            row.timeout_s, row.timeout_personal_s = row.timeout_personal_s, row.timeout_s
        await session.flush()
        if row.vcost:
            # Личный раннер не двигает глобальное время и возвращает метку справедливости.
            await session.execute(
                update(FairShareRow)
                .where(FairShareRow.user_id == row.user_id)
                .values(vtime=func.greatest(func.coalesce(FairShareRow.vtime, 0) - row.vcost, 0))
            )

    @staticmethod
    async def _take_shared(session: AsyncSession, row: JobRow) -> None:
        row.runner_scope = RunnerScope.shared.value
        if row.route == JobRoute.personal_first.value and row.route_reason not in _KEPT_REASONS:
            row.route_reason = RouteReason.fallback_timeout.value
        await session.flush()
        await session.execute(
            update(JobQueueStateRow).values(global_vtime=func.greatest(JobQueueStateRow.global_vtime, row.vtime))
        )

    async def expire_personal_wait(
        self,
        *,
        owner_id: str | None = None,
        project_id: UUID | None = None,
        reason: RouteReason = RouteReason.fallback_offline,
    ) -> int:
        now = self._clock()
        stmt = update(JobRow).where(
            JobRow.state == JobState.queued.value,
            JobRow.route == JobRoute.personal_first.value,
            JobRow.personal_until > now,
        )
        if owner_id is not None:
            stmt = stmt.where(JobRow.route_owner_id == owner_id)
        if project_id is not None:
            stmt = stmt.where(JobRow.project_id == project_id)
        async with self._sessions.use() as session:
            result = await session.execute(stmt.values(personal_until=now, route_reason=reason.value))
            return int(result.rowcount)  # type: ignore[attr-defined]

    async def personal_load(self, owner_id: str, runner_ids: frozenset[UUID], now: datetime) -> int:
        running = select(func.count()).where(
            JobRow.state == JobState.running.value,
            JobRow.runner_scope == RunnerScope.personal.value,
            JobRow.kind != JobKind.ai_relay.value,
            JobRow.runner_id.in_(sorted(runner_ids)),
        )
        waiting = select(func.count()).where(
            JobRow.state == JobState.queued.value,
            JobRow.route == JobRoute.personal_first.value,
            JobRow.route_owner_id == owner_id,
            JobRow.personal_until > now,
        )
        async with self._sessions.use() as session:
            busy = (await session.execute(running)).scalar_one() if runner_ids else 0
            return int(busy) + int((await session.execute(waiting)).scalar_one())

    async def cancel_pinned(self, *, runner_id: UUID | None, error_code: str) -> tuple[QueuedJob, ...]:
        stmt = update(JobRow).where(JobRow.state == JobState.queued.value, JobRow.route == JobRoute.pinned.value)
        if runner_id is not None:
            stmt = stmt.where(JobRow.target_runner_id == runner_id)
        stmt = (
            stmt.values(
                state=JobState.cancelled.value,
                finished_at=self._clock(),
                cancel_requested=True,
                error_code=error_code,
            )
            .returning(JobRow)
            .execution_options(populate_existing=True)
        )
        async with self._sessions.use() as session:
            return tuple(job_from_row(row) for row in (await session.execute(stmt)).scalars())

    async def heartbeat(self, job_id: UUID, attempt: int, *, lease_s: float) -> Heartbeat:
        async with self._sessions.use() as session:
            row = await self._current(session, job_id, attempt)
            row.lease_until = self._clock() + timedelta(seconds=lease_s)
            await session.flush()
            return Heartbeat(cancel=row.cancel_requested, lease_until=row.lease_until)

    async def complete(
        self,
        job_id: UUID,
        attempt: int,
        status: JobStatus,
        *,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> QueuedJob:
        async with self._sessions.use() as session:
            row = await self._current(session, job_id, attempt)
            if row.cancel_requested and status is JobStatus.succeeded:
                # Отмена сильнее успеха: выходы отброшены, как в локальном режиме.
                status, result, error_code = JobStatus.cancelled, None, None
            row.state = JobState.of_status(status).value
            row.finished_at = self._clock()
            row.lease_until = None
            row.result = result
            row.error_code = error_code
            await session.flush()
            return job_from_row(row)

    async def request_cancel(self, job_id: UUID) -> QueuedJob:
        async with self._sessions.use() as session:
            row = await self._locked(session, job_id)
            if row is None:
                raise QueuedJobNotFoundError(f"job {job_id} not found")
            if row.state == JobState.queued.value:
                row.state = JobState.cancelled.value
                row.finished_at = self._clock()
                row.cancel_requested = True
            elif row.state == JobState.running.value:
                row.cancel_requested = True
            await session.flush()
            return job_from_row(row)

    async def requeue_expired(self) -> tuple[ExpiredOutcome, ...]:
        now = self._clock()
        outcomes: list[ExpiredOutcome] = []
        async with self._sessions.use() as session:
            expired = (
                await session.execute(
                    select(JobRow)
                    .where(JobRow.state == JobState.running.value, JobRow.lease_until <= now)
                    .order_by(JobRow.seq)
                    .with_for_update(skip_locked=True)
                    .execution_options(populate_existing=True)
                )
            ).scalars()
            for row in expired:
                requeued = False
                if row.cancel_requested:
                    row.state = JobState.cancelled.value
                    row.finished_at = now
                elif retry_available(row.attempt, row.max_attempts):
                    if row.runner_scope == RunnerScope.personal.value:
                        # Личный раннер пропал: повтор где угодно, предел с квотой возвращается.
                        if row.route == JobRoute.personal_first.value:
                            row.personal_until = now
                        row.route_reason = RouteReason.fallback_lost.value
                        if row.timeout_personal_s is not None:
                            row.timeout_s, row.timeout_personal_s = row.timeout_personal_s, row.timeout_s
                    row.state = JobState.queued.value
                    row.runner_id = None
                    row.runner_scope = None
                    row.started_at = None
                    row.affinity_runner_id = None
                    requeued = True
                else:
                    row.state = JobState.failed.value
                    row.finished_at = now
                    row.error_code = RunnerErrorCode.runner_lost.value
                row.lease_until = None
                outcomes.append(ExpiredOutcome(job_from_row(row), requeued=requeued))
            await session.flush()
        return tuple(outcomes)

    async def get(self, job_id: UUID) -> QueuedJob | None:
        async with self._sessions.use() as session:
            row = (
                await session.execute(
                    select(JobRow).where(JobRow.id == job_id).execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            return job_from_row(row) if row is not None else None

    async def list(self, *, state: JobState | None = None, project_id: UUID | None = None) -> tuple[QueuedJob, ...]:
        stmt = select(JobRow).order_by(JobRow.seq).execution_options(populate_existing=True)
        if state is not None:
            stmt = stmt.where(JobRow.state == state.value)
        if project_id is not None:
            stmt = stmt.where(JobRow.project_id == project_id)
        async with self._sessions.use() as session:
            return tuple(job_from_row(row) for row in (await session.execute(stmt)).scalars())

    @staticmethod
    def _best_candidate(runner: RunnerRef, limits: QueueQuota, now: datetime, lease_s: float) -> Select[Any]:
        job = aliased(JobRow, name="j")
        running = aliased(JobRow, name="r")
        busy = aliased(JobRow, name="b")
        conditions = [
            job.state == JobState.queued.value,
            job.tags.contained_by(sorted(runner.tags)),
            job.kind != JobKind.ai_relay.value,
            or_(
                job.route == JobRoute.shared.value,
                and_(job.route == JobRoute.personal_first.value, job.personal_until <= now),
            ),
        ]
        user_cap = _cap_expression(
            limits.max_running_per_user,
            (job.user_id, limits.user_caps),
            (job.org_id, limits.org_user_caps),
        )
        if user_cap is not None:
            of_user = (
                select(func.count())
                .where(
                    running.state == JobState.running.value,
                    running.runner_scope == RunnerScope.shared.value,
                    running.user_id == job.user_id,
                )
                .scalar_subquery()
            )
            conditions.append(user_cap.is_(None) | (of_user < user_cap))
        org_cap = _cap_expression(limits.max_running_per_org, (job.org_id, limits.org_caps))
        if org_cap is not None:
            of_org = (
                select(func.count())
                .where(
                    running.state == JobState.running.value,
                    running.runner_scope == RunnerScope.shared.value,
                    running.org_id == job.org_id,
                )
                .scalar_subquery()
            )
            conditions.append(job.org_id.is_(None) | org_cap.is_(None) | (of_org < org_cap))
        # Закреплённый раннер жив (опрашивал в пределах аренды) и у него есть свободный слот.
        busy_count = (
            select(func.count())
            .where(busy.state == JobState.running.value, busy.runner_id == JobRunnerPollRow.runner_id)
            .scalar_subquery()
        )
        affine_available = (
            select(literal(1))
            .where(
                JobRunnerPollRow.runner_id == job.affinity_runner_id,
                JobRunnerPollRow.last_seen_at >= now - timedelta(seconds=lease_s),
                busy_count < JobRunnerPollRow.concurrency,
            )
            .exists()
        )
        conditions.append(
            (job.affinity_runner_id.is_(None))
            | (job.affinity_runner_id == runner.id)
            | (job.queued_at <= now - AFFINITY_WAIT)
            | ~affine_available
        )
        return (
            select(job)
            .where(*conditions)
            .order_by(job.priority_class, job.vtime, job.queued_at, job.seq)
            .limit(1)
            .with_for_update(skip_locked=True, of=job)
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def _personal_candidate(runner: RunnerRef) -> Select[Any] | None:
        """Задачи проектов хозяина раннера (проверка владельца и политики в момент выдачи) и его ретрансляции."""
        owner = runner.owner_id
        if owner is None:
            return None
        owner_uuid = _uuid_or_none(owner)
        job = aliased(JobRow, name="j")
        branches: list[ColumnElement[bool]] = []
        if runner.accept_jobs:
            author_allowed: ColumnElement[bool] = ProjectRow.build_runners == ProjectBuildRunners.owner.value
            if owner_uuid is not None:
                author_allowed = or_(job.user_id == owner_uuid, author_allowed)
            project_allows = (
                select(literal(1))
                .where(
                    ProjectRow.id == job.project_id,
                    ProjectRow.owner_user_id == owner,
                    ProjectRow.deleted_at.is_(None),
                    author_allowed,
                )
                .exists()
            )
            branches.append(
                and_(
                    job.route == JobRoute.personal_first.value,
                    job.route_owner_id == owner,
                    job.kind.in_(_PERSONAL_KINDS),
                    project_allows,
                )
            )
        if runner.accept_relay and owner_uuid is not None:
            branches.append(
                and_(
                    job.route == JobRoute.pinned.value,
                    job.target_runner_id == runner.id,
                    job.kind == JobKind.ai_relay.value,
                    job.user_id == owner_uuid,
                )
            )
        if not branches:
            return None
        return (
            select(job)
            .where(job.state == JobState.queued.value, job.tags.contained_by(sorted(runner.tags)), or_(*branches))
            .order_by(job.priority_class, job.vtime, job.queued_at, job.seq)
            .limit(1)
            .with_for_update(skip_locked=True, of=job)
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def _locked(session: AsyncSession, job_id: UUID) -> JobRow | None:
        return (
            await session.execute(
                select(JobRow).where(JobRow.id == job_id).with_for_update().execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    async def _current(self, session: AsyncSession, job_id: UUID, attempt: int) -> JobRow:
        row = await self._locked(session, job_id)
        if row is None:
            raise QueuedJobNotFoundError(f"job {job_id} not found")
        if row.state != JobState.running.value or row.attempt != attempt:
            raise StaleAttemptError(f"attempt {attempt} of job {job_id} is not current")
        return row
