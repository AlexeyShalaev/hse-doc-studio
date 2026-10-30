"""Postgres-репозитории реестра раннеров и токенов регистрации."""

from __future__ import annotations

import builtins
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.jobs.relay import AiEndpointFlavor
from hse_doc_studio.core.jobs.runners import (
    DeclaredAiEndpoint,
    RegistrationToken,
    RegistrationTokenPurpose,
    Runner,
    RunnerAnnouncement,
    RunnerHostKind,
    RunnerOwnerKind,
)
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
        host_kind=RunnerHostKind(row.host_kind),
        features=frozenset(row.features),
        ai_endpoints=_endpoints(row.ai_endpoints),
        ai_concurrency=row.ai_concurrency,
        last_seen_ip=row.last_seen_ip,
        offline_at=row.offline_at,
        renamed_at=row.renamed_at,
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

    async def set_paused(self, runner_id: str, paused: bool) -> bool:
        return await self._update(runner_id, {"paused": paused}, only_active=True)

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
