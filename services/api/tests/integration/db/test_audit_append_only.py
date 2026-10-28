"""Журнал аудита только на дозапись на уровне базы, а не только по отсутствию методов в коде."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.pg

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


async def _insert_one(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO audit_log (action, details) VALUES ('login.ok', '{}')"))


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log", "TRUNCATE audit_log"],
    ids=["update", "delete", "truncate"],
)
async def test__audit_log__change_or_delete__rejected_even_for_owner(
    pg_migrated_engine: AsyncEngine, statement: str
) -> None:
    await _insert_one(pg_migrated_engine)
    with pytest.raises(DBAPIError, match="append-only"):
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text(statement))
    async with pg_migrated_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM audit_log"))).scalar_one() == 1


async def test__audit_log__public_has_no_privileges(pg_migrated_engine: AsyncEngine) -> None:
    query = (
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE table_name = 'audit_log' AND grantee = 'PUBLIC'"
    )
    async with pg_migrated_engine.connect() as conn:
        assert (await conn.execute(text(query))).all() == []


async def _denied(engine: AsyncEngine, role: str, statement: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"SET LOCAL ROLE {role}"))
        await conn.execute(text(statement))


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log", "TRUNCATE audit_log"],
    ids=["update", "delete", "truncate"],
)
async def test__audit_log__app_role_with_select_insert__is_denied(
    pg_migrated_engine: AsyncEngine, statement: str
) -> None:
    role = f"hse_probe_{uuid.uuid4().hex[:8]}"
    async with pg_migrated_engine.begin() as conn:
        await conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        await conn.execute(text(f"GRANT SELECT, INSERT ON audit_log TO {role}"))
        await conn.execute(text(f"GRANT USAGE ON SEQUENCE audit_log_id_seq TO {role}"))
    try:
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text(f"SET LOCAL ROLE {role}"))
            await conn.execute(text("INSERT INTO audit_log (action) VALUES ('ok')"))
        with pytest.raises(DBAPIError, match="permission denied"):
            await _denied(pg_migrated_engine, role, statement)
    finally:
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text(f"DROP OWNED BY {role}"))
            await conn.execute(text(f"DROP ROLE {role}"))


async def test__audit_purge__removes_old_events_only_through_the_function(pg_migrated_engine: AsyncEngine) -> None:
    async with pg_migrated_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO audit_log (action, at) VALUES ('old', now() - interval '400 days'), ('fresh', now())")
        )
        removed = (await conn.execute(text("SELECT audit_log_purge(now() - interval '365 days')"))).scalar_one()
    assert removed == 1
    async with pg_migrated_engine.connect() as conn:
        assert (await conn.execute(text("SELECT action FROM audit_log"))).scalars().all() == ["fresh"]
    with pytest.raises(DBAPIError, match="append-only"):
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text("DELETE FROM audit_log"))


async def test__audit_purge__flag_does_not_leak_out_of_the_function_transaction(
    pg_migrated_engine: AsyncEngine,
) -> None:
    await _insert_one(pg_migrated_engine)
    async with pg_migrated_engine.connect() as conn:
        await conn.execute(text("SELECT audit_log_purge(now() - interval '1 day')"))
        with pytest.raises(DBAPIError, match="append-only"):
            await conn.execute(text("DELETE FROM audit_log"))
    with pytest.raises(DBAPIError, match="append-only"):
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text("UPDATE audit_log SET action = 'x'"))


async def test__audit_purge__app_role_can_execute_it_but_not_delete(pg_migrated_engine: AsyncEngine) -> None:
    role = f"hse_probe_{uuid.uuid4().hex[:8]}"
    async with pg_migrated_engine.begin() as conn:
        await conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        await conn.execute(text(f"GRANT SELECT, INSERT ON audit_log TO {role}"))
        await conn.execute(text(f"GRANT EXECUTE ON FUNCTION audit_log_purge(timestamptz) TO {role}"))
        await conn.execute(text("INSERT INTO audit_log (action, at) VALUES ('old', now() - interval '2 days')"))
    try:
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text(f"SET LOCAL ROLE {role}"))
            removed = (await conn.execute(text("SELECT audit_log_purge(now() - interval '1 day')"))).scalar_one()
        assert removed == 1
        with pytest.raises(DBAPIError, match="permission denied"):
            await _denied(pg_migrated_engine, role, "DELETE FROM audit_log")
    finally:
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text(f"DROP OWNED BY {role}"))
            await conn.execute(text(f"DROP ROLE {role}"))


async def test__audit_purge__public_cannot_execute(pg_migrated_engine: AsyncEngine) -> None:
    role = f"hse_probe_{uuid.uuid4().hex[:8]}"
    async with pg_migrated_engine.begin() as conn:
        await conn.execute(text(f"CREATE ROLE {role} NOLOGIN"))
    try:
        with pytest.raises(DBAPIError, match="permission denied"):
            await _denied(pg_migrated_engine, role, "SELECT audit_log_purge(now())")
    finally:
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text(f"DROP ROLE {role}"))
