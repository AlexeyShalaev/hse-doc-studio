"""Postgres-репозитории реестра раннеров и токенов регистрации."""

from __future__ import annotations

import builtins
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Integer,
    and_,
    case,
    cast,
    false,
    func,
    or_,
    select,
    true,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.jobs.admin import (
    RUNNER_ONLINE_WITHIN,
    RUNNER_STALE_WITHIN,
    RUNNER_STATUS_ORDER,
    VERSION_PARTS,
    RegistrationTokenQuery,
    RegistrationTokenStatus,
    RunnerQuery,
    RunnerStatus,
    RunnerSummary,
)
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor
from hse_doc_studio.core.jobs.runners import (
    DeclaredAiEndpoint,
    RegistrationToken,
    RegistrationTokenPurpose,
    Runner,
    RunnerAnnouncement,
    RunnerHostKind,
    RunnerOwnerKind,
    RunnerPausedBy,
)
from hse_doc_studio.core.listing import Found, Picked, PickerItem
from hse_doc_studio.infra.db.orm.jobs import RunnerRegistrationTokenRow, RunnerRow
from hse_doc_studio.infra.db.search import matches_any, ordered
from hse_doc_studio.infra.db.session import SessionProvider


def _runner(row: RunnerRow) -> Runner:
    return Runner(
        id=row.id,
        name=row.name,
        token_hash=row.token_hash,
        tags=frozenset(row.tags),
        concurrency=row.concurrency,
        resource_class=row.resource_class,
        version=row.version,
        created_at=row.created_at,
        created_by=row.created_by,
        last_seen_at=row.last_seen_at,
        paused=row.paused,
        revoked_at=row.revoked_at,
        owner_kind=RunnerOwnerKind(row.owner_kind),
        owner_id=row.owner_id,
        host_kind=RunnerHostKind(row.host_kind),
        features=frozenset(row.features),
        ai_endpoints=_endpoints(row.ai_endpoints),
        ai_concurrency=row.ai_concurrency,
        last_seen_ip=row.last_seen_ip,
        offline_at=row.offline_at,
        renamed_at=row.renamed_at,
        paused_by=RunnerPausedBy(row.paused_by) if row.paused_by else None,
    )


def _endpoints(raw: list[Any]) -> tuple[DeclaredAiEndpoint, ...]:
    # Запись пишет только `/announce` после проверки схемой; чужие ключи и виды тихо пропускаются.
    found: list[DeclaredAiEndpoint] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        try:
            flavor = AiEndpointFlavor(item.get("flavor", AiEndpointFlavor.openai.value))
        except ValueError:
            continue
        found.append(DeclaredAiEndpoint(name=item["name"], flavor=flavor))
    return tuple(found)


def endpoints_json(endpoints: tuple[DeclaredAiEndpoint, ...]) -> list[Any]:
    return [{"name": e.name, "flavor": e.flavor.value} for e in endpoints]


def _token(row: RunnerRegistrationTokenRow) -> RegistrationToken:
    return RegistrationToken(
        id=row.id,
        token_hash=row.token_hash,
        created_by=row.created_by,
        created_at=row.created_at,
        expires_at=row.expires_at,
        max_uses=row.max_uses,
        uses=row.uses,
        label=row.label,
        revoked_at=row.revoked_at,
        owner_kind=RunnerOwnerKind(row.owner_kind),
        owner_id=row.owner_id,
        purpose=RegistrationTokenPurpose(row.purpose),
    )


class SqlRunnerRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, runner: Runner) -> None:
        async with self._sessions.use() as db:
            db.add(
                RunnerRow(
                    id=runner.id,
                    owner_kind=runner.owner_kind.value,
                    owner_id=runner.owner_id,
                    name=runner.name,
                    token_hash=runner.token_hash,
                    tags=sorted(runner.tags),
                    resource_class=runner.resource_class,
                    concurrency=runner.concurrency,
                    version=runner.version,
                    paused=runner.paused,
                    created_by=runner.created_by,
                    created_at=runner.created_at,
                    last_seen_at=runner.last_seen_at,
                    revoked_at=runner.revoked_at,
                    host_kind=runner.host_kind.value,
                    features=sorted(runner.features),
                    ai_endpoints=endpoints_json(runner.ai_endpoints),
                    ai_concurrency=runner.ai_concurrency,
                    last_seen_ip=runner.last_seen_ip,
                    offline_at=runner.offline_at,
                    renamed_at=runner.renamed_at,
                )
            )
            await db.flush()

    async def get(self, runner_id: str) -> Runner | None:
        async with self._sessions.use() as db:
            row = await db.get(RunnerRow, runner_id)
            return _runner(row) if row else None

    async def get_by_token_hash(self, token_hash: str) -> Runner | None:
        async with self._sessions.use() as db:
            row = (await db.execute(select(RunnerRow).where(RunnerRow.token_hash == token_hash))).scalar_one_or_none()
            return _runner(row) if row else None

    async def list(self) -> list[Runner]:
        async with self._sessions.use() as db:
            rows = await db.execute(select(RunnerRow).order_by(RunnerRow.created_at, RunnerRow.id))
            return [_runner(row) for row in rows.scalars()]

    async def _update(self, runner_id: str, values: dict[str, object], *, only_active: bool = False) -> bool:
        stmt = update(RunnerRow).where(RunnerRow.id == runner_id).values(**values)
        if only_active:
            stmt = stmt.where(RunnerRow.revoked_at.is_(None))
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount > 0  # type: ignore[attr-defined]

    async def set_token_hash(self, runner_id: str, token_hash: str) -> bool:
        return await self._update(runner_id, {"token_hash": token_hash}, only_active=True)

    async def set_paused(self, runner_id: str, paused: bool, by: RunnerPausedBy | None = None) -> bool:
        paused_by = by.value if paused and by is not None else None
        return await self._update(runner_id, {"paused": paused, "paused_by": paused_by}, only_active=True)

    async def revoke(self, runner_id: str, now: datetime) -> bool:
        return await self._update(runner_id, {"revoked_at": now})

    async def touch(self, runner_id: str, now: datetime, version: str | None = None) -> None:
        values: dict[str, object] = {"last_seen_at": now}
        if version is not None:
            values["version"] = version
        await self._update(runner_id, values)

    async def list_owned(self, owner_id: str) -> builtins.list[Runner]:
        stmt = (
            select(RunnerRow)
            .where(RunnerRow.owner_kind == RunnerOwnerKind.user.value, RunnerRow.owner_id == owner_id)
            .order_by(RunnerRow.created_at, RunnerRow.id)
        )
        async with self._sessions.use() as db:
            return [_runner(row) for row in (await db.execute(stmt)).scalars()]

    async def rename(self, runner_id: str, name: str, now: datetime) -> bool:
        return await self._update(runner_id, {"name": name, "renamed_at": now}, only_active=True)

    async def apply_announcement(
        self, runner_id: str, info: RunnerAnnouncement, now: datetime, ip: str | None
    ) -> Runner | None:
        values: dict[str, object] = {
            "version": info.version,
            "tags": sorted(info.tags),
            "concurrency": info.concurrency,
            "ai_concurrency": info.ai_concurrency,
            "host_kind": info.host_kind.value,
            "features": sorted(info.features),
            "ai_endpoints": endpoints_json(info.ai_endpoints),
            "last_seen_at": now,
            "last_seen_ip": ip,
            "offline_at": None,
        }
        async with self._sessions.use() as db:
            row = await db.get(RunnerRow, runner_id, with_for_update=True, populate_existing=True)
            if row is None or row.revoked_at is not None:
                return None
            for key, value in values.items():
                setattr(row, key, value)
            # Имя, заданное хозяином или админом в интерфейсе, `/announce` не перетирает.
            if info.name is not None and row.renamed_at is None:
                row.name = info.name
            await db.flush()
            return _runner(row)

    async def mark_offline(self, runner_id: str, now: datetime) -> None:
        await self._update(runner_id, {"offline_at": now})

    async def count_active_owned(self, owner_id: str) -> int:
        stmt = select(func.count()).where(
            RunnerRow.owner_kind == RunnerOwnerKind.user.value,
            RunnerRow.owner_id == owner_id,
            RunnerRow.revoked_at.is_(None),
        )
        async with self._sessions.use() as db:
            return int((await db.execute(stmt)).scalar_one())


class SqlRegistrationTokenRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, token: RegistrationToken) -> None:
        async with self._sessions.use() as db:
            db.add(RunnerRegistrationTokenRow(**_values(token)))
            await db.flush()

    async def get(self, token_id: str) -> RegistrationToken | None:
        async with self._sessions.use() as db:
            row = await db.get(RunnerRegistrationTokenRow, token_id)
            return _token(row) if row else None

    async def list(self) -> list[RegistrationToken]:
        async with self._sessions.use() as db:
            rows = await db.execute(
                select(RunnerRegistrationTokenRow).order_by(
                    RunnerRegistrationTokenRow.created_at.desc(), RunnerRegistrationTokenRow.id
                )
            )
            return [_token(row) for row in rows.scalars()]

    async def revoke(self, token_id: str, now: datetime) -> bool:
        stmt = (
            update(RunnerRegistrationTokenRow)
            .where(RunnerRegistrationTokenRow.id == token_id, RunnerRegistrationTokenRow.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount > 0  # type: ignore[attr-defined]

    async def consume(self, token_hash: str, now: datetime) -> RegistrationToken | None:
        row_t = RunnerRegistrationTokenRow
        stmt = (
            update(row_t)
            .where(
                row_t.token_hash == token_hash,
                row_t.revoked_at.is_(None),
                row_t.uses < row_t.max_uses,
                or_(row_t.expires_at.is_(None), row_t.expires_at > now),
            )
            .values(uses=row_t.uses + 1)
            .returning(row_t)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
            return _token(row) if row else None

    async def list_owned(self, owner_id: str) -> builtins.list[RegistrationToken]:
        row_t = RunnerRegistrationTokenRow
        stmt = (
            select(row_t)
            .where(row_t.owner_kind == RunnerOwnerKind.user.value, row_t.owner_id == owner_id)
            .order_by(row_t.created_at.desc(), row_t.id)
        )
        async with self._sessions.use() as db:
            return [_token(row) for row in (await db.execute(stmt)).scalars()]

    async def revoke_owned(self, owner_id: str, now: datetime) -> int:
        row_t = RunnerRegistrationTokenRow
        stmt = (
            update(row_t)
            .where(
                row_t.owner_kind == RunnerOwnerKind.user.value, row_t.owner_id == owner_id, row_t.revoked_at.is_(None)
            )
            .values(revoked_at=now)
        )
        async with self._sessions.use() as db:
            return int((await db.execute(stmt)).rowcount)  # type: ignore[attr-defined]

    async def upsert_bootstrap(self, token: RegistrationToken) -> None:
        async with self._sessions.use() as db:
            # Вставка без гонки между воркерами; смена хеша сбрасывает счётчик одним UPDATE.
            await db.execute(pg_insert(RunnerRegistrationTokenRow).values(_values(token)).on_conflict_do_nothing())
            await db.execute(
                update(RunnerRegistrationTokenRow)
                .where(
                    RunnerRegistrationTokenRow.id == token.id,
                    RunnerRegistrationTokenRow.token_hash != token.token_hash,
                )
                .values(token_hash=token.token_hash, uses=0, revoked_at=None, created_at=token.created_at)
            )


def _values(token: RegistrationToken) -> dict[str, object]:
    return dict(
        id=token.id,
        owner_kind=token.owner_kind.value,
        owner_id=token.owner_id,
        token_hash=token.token_hash,
        label=token.label,
        max_uses=token.max_uses,
        uses=token.uses,
        created_by=token.created_by,
        created_at=token.created_at,
        expires_at=token.expires_at,
        revoked_at=token.revoked_at,
        purpose=token.purpose.value,
    )


def _version_parts() -> list[ColumnElement[int]]:
    """Части версии числами, как `version_key`: ведущие цифры части, иначе ноль."""
    parts: list[ColumnElement[int]] = []
    for n in range(1, VERSION_PARTS + 1):
        digits = func.substring(func.split_part(RunnerRow.version, ".", n), "^[0-9]{1,9}")
        parts.append(func.coalesce(cast(digits, Integer), 0))
    return parts


def _runner_status(now: datetime) -> ColumnElement[str]:
    """Статус раннера в SQL с теми же порогами и тем же старшинством, что у `runner_status`."""
    r = RunnerRow
    return case(
        (r.revoked_at.is_not(None), RunnerStatus.revoked.value),
        (r.paused.is_(True), RunnerStatus.paused.value),
        (r.last_seen_at.is_(None), RunnerStatus.offline.value),
        (r.last_seen_at >= now - RUNNER_ONLINE_WITHIN, RunnerStatus.online.value),
        (r.last_seen_at >= now - RUNNER_STALE_WITHIN, RunnerStatus.stale.value),
        else_=RunnerStatus.offline.value,
    )


def _status_rank(status: ColumnElement[str]) -> ColumnElement[int]:
    return case({s.value: i for i, s in enumerate(RUNNER_STATUS_ORDER)}, value=status, else_=len(RUNNER_STATUS_ORDER))


def _token_status(status: RegistrationTokenStatus, now: datetime) -> ColumnElement[bool]:
    t = RunnerRegistrationTokenRow
    live = t.revoked_at.is_(None)
    left = t.uses < t.max_uses
    expired = and_(t.expires_at.is_not(None), t.expires_at <= now)
    match status:
        case RegistrationTokenStatus.revoked:
            return t.revoked_at.is_not(None)
        case RegistrationTokenStatus.exhausted:
            return and_(live, t.uses >= t.max_uses)
        case RegistrationTokenStatus.expired:
            return and_(live, left, expired)
        case RegistrationTokenStatus.active:
            return and_(live, left, or_(t.expires_at.is_(None), t.expires_at > now))


class SqlRunnerAdminReader:
    """Списки раннеров и токенов регистрации для админки; статус и «устарел» считаются в SQL от `now`."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def _newest(self) -> tuple[str, tuple[int, ...]] | None:
        parts = _version_parts()
        stmt = (
            select(RunnerRow.version, *parts)
            # Устарел ли раннер считается от флота установки: версии личных раннеров людей
            # не сбивают эту оценку.
            .where(RunnerRow.revoked_at.is_(None), RunnerRow.owner_kind == RunnerOwnerKind.instance.value)
            .order_by(*(p.desc() for p in parts), RunnerRow.id)
            .limit(1)
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).first()
        return None if row is None else (row[0], tuple(int(v) for v in row[1:]))

    @staticmethod
    def _outdated(newest: tuple[str, tuple[int, ...]] | None) -> ColumnElement[bool]:
        if newest is None:
            return false()
        return and_(RunnerRow.revoked_at.is_(None), tuple_(*_version_parts()) < tuple_(*newest[1]))

    async def list_runners(self, query: RunnerQuery, now: datetime) -> Found[Runner]:
        status = _runner_status(now)
        conditions: list[ColumnElement[bool]] = []
        if query.q:
            conditions.append(
                matches_any(query.q, [RunnerRow.name, RunnerRow.version, func.array_to_string(RunnerRow.tags, " ")])
            )
        if query.statuses:
            conditions.append(status.in_(sorted(s.value for s in query.statuses)))
        if query.tag:
            conditions.append(RunnerRow.tags.contains([query.tag]))
        if query.resource_class:
            conditions.append(RunnerRow.resource_class == query.resource_class)
        if query.outdated is not None:
            outdated = self._outdated(await self._newest())
            conditions.append(outdated if query.outdated else ~outdated)
        if query.owner_kind is not None:
            conditions.append(RunnerRow.owner_kind == query.owner_kind.value)
        keys: dict[str, list[Any]] = {
            "name": [func.lower(RunnerRow.name)],
            "status": [_status_rank(status), func.lower(RunnerRow.name)],
            "last_seen_at": [RunnerRow.last_seen_at],
            "created_at": [RunnerRow.created_at],
            "version": list(_version_parts()),
            "owner_kind": [RunnerRow.owner_kind, func.lower(RunnerRow.name)],
        }
        stmt = (
            select(RunnerRow)
            .where(*conditions)
            .order_by(*ordered(query.sort, keys, RunnerRow.id, nullable=frozenset({"last_seen_at"})))
            .limit(query.window.limit)
            .offset(query.window.offset)
        )
        async with self._sessions.use() as session:
            total = (await session.execute(select(func.count()).select_from(RunnerRow).where(*conditions))).scalar_one()
            rows = (await session.execute(stmt)).scalars().all()
        return Found(items=[_runner(row) for row in rows], total=int(total))

    async def summary(self, now: datetime) -> RunnerSummary:
        # Сводка только по раннерам установки: у личных раннеров людей своя сводка на экране.
        instance_only = RunnerRow.owner_kind == RunnerOwnerKind.instance.value
        status = _runner_status(now).label("status")
        newest = await self._newest()
        async with self._sessions.use() as session:
            counts = {
                str(s): int(n)
                for s, n in (
                    await session.execute(select(status, func.count()).where(instance_only).group_by(status))
                ).all()
            }
            outdated = (
                await session.execute(
                    select(func.count()).select_from(RunnerRow).where(self._outdated(newest), instance_only)
                )
            ).scalar_one()
        return RunnerSummary(
            online=counts.get(RunnerStatus.online.value, 0),
            paused=counts.get(RunnerStatus.paused.value, 0),
            stale=counts.get(RunnerStatus.stale.value, 0),
            offline=counts.get(RunnerStatus.offline.value, 0),
            revoked=counts.get(RunnerStatus.revoked.value, 0),
            outdated=int(outdated),
            newest_version=newest[0] if newest else None,
        )

    async def list_tokens(self, query: RegistrationTokenQuery, now: datetime) -> Found[RegistrationToken]:
        t = RunnerRegistrationTokenRow
        conditions: list[ColumnElement[bool]] = []
        if query.q:
            conditions.append(matches_any(query.q, [t.label]))
        if query.statuses:
            conditions.append(or_(*(_token_status(s, now) for s in sorted(query.statuses))))
        keys: dict[str, list[Any]] = {
            "created_at": [t.created_at],
            "expires_at": [t.expires_at],
            "label": [func.lower(t.label)],
        }
        stmt = (
            select(t)
            .where(*conditions)
            .order_by(*ordered(query.sort, keys, t.id, nullable=frozenset({"expires_at"})))
            .limit(query.window.limit)
            .offset(query.window.offset)
        )
        async with self._sessions.use() as session:
            total = (await session.execute(select(func.count()).select_from(t).where(*conditions))).scalar_one()
            rows = (await session.execute(stmt)).scalars().all()
        return Found(items=[_token(row) for row in rows], total=int(total))

    async def pick(self, q: str | None, limit: int, *, item_id: str | None = None) -> Picked[PickerItem]:
        stmt = select(RunnerRow.id, RunnerRow.name, RunnerRow.tags).where(
            matches_any(q, [RunnerRow.name]) if q else true(),
            RunnerRow.id == item_id if item_id is not None else true(),
        )
        stmt = stmt.order_by(func.lower(RunnerRow.name), RunnerRow.id).limit(limit + 1)
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).all()
        items = [
            PickerItem(kind="runner", id=row[0], name=row[1], detail=", ".join(sorted(row[2])) or None)
            for row in rows[:limit]
        ]
        return Picked(items=items, has_more=len(rows) > limit)
