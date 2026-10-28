"""Postgres-репозитории реестра раннеров и токенов регистрации."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select, update

from hse_doc_studio.core.jobs.runners import RegistrationToken, Runner, RunnerOwnerKind
from hse_doc_studio.infra.db.orm.jobs import RunnerRegistrationTokenRow, RunnerRow
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
    )


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

    async def set_paused(self, runner_id: str, paused: bool) -> bool:
        return await self._update(runner_id, {"paused": paused}, only_active=True)

    async def revoke(self, runner_id: str, now: datetime) -> bool:
        return await self._update(runner_id, {"revoked_at": now})

    async def touch(self, runner_id: str, now: datetime, version: str | None = None) -> None:
        values: dict[str, object] = {"last_seen_at": now}
        if version is not None:
            values["version"] = version
        await self._update(runner_id, values)


class SqlRegistrationTokenRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, token: RegistrationToken) -> None:
        async with self._sessions.use() as db:
            db.add(_row(token))
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

    async def upsert_bootstrap(self, token: RegistrationToken) -> None:
        async with self._sessions.use() as db:
            row = await db.get(RunnerRegistrationTokenRow, token.id, with_for_update=True)
            if row is None:
                db.add(_row(token))
            elif row.token_hash != token.token_hash:
                row.token_hash = token.token_hash
                row.uses = 0
                row.revoked_at = None
                row.created_at = token.created_at
            await db.flush()


def _row(token: RegistrationToken) -> RunnerRegistrationTokenRow:
    return RunnerRegistrationTokenRow(
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
    )
