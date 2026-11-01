"""Назначения и запуски бэкапов в Postgres: умолчание, уникальность имени, один идущий запуск, секреты в реестре."""

from __future__ import annotations

import shutil
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.backup.entities import (
    BackupDestination,
    BackupRun,
    DestinationKind,
    DestinationSpec,
    RunStatus,
    RunTrigger,
    StoredDestination,
)
from hse_doc_studio.core.listing import Window
from hse_doc_studio.core.secrets import encrypted_columns
from hse_doc_studio.infra.db import orm  # noqa: F401
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.backup import (
    SqlAdminDirectory,
    SqlBackupDestinationRepository,
    SqlBackupRunRepository,
)
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)


def _stored(name: str, offset: int = 0, **spec: object) -> StoredDestination:
    destination = BackupDestination(
        id=str(uuid4()),
        spec=DestinationSpec(name=name, kind=DestinationKind.s3, bucket="hse-backups", **spec),  # type: ignore[arg-type]
        is_default=False,
        access_key_hint="…1234",
        secret_key_set=True,
        created_at=NOW + timedelta(seconds=offset),
        updated_at=NOW,
    )
    return StoredDestination(destination, "sealed-access", "sealed-secret")


def _run(destination_id: str | None, status: RunStatus = RunStatus.running, minutes: int = 0) -> BackupRun:
    return BackupRun(
        id=str(uuid4()),
        destination_id=destination_id,
        destination_name="d",
        trigger=RunTrigger.manual,
        status=status,
        stage="x",
        started_at=NOW + timedelta(minutes=minutes),
    )


@pytest.fixture
def sessions(pg_migrated_engine: AsyncEngine) -> SessionProvider:
    return SessionProvider(create_sessionmaker(pg_migrated_engine))


async def test__destinations__first_becomes_default_and_default_moves_on_delete(sessions: SessionProvider) -> None:
    repo = SqlBackupDestinationRepository(sessions)
    first, second = _stored("One", 0), _stored("Two", 1)
    await repo.add(first)
    await repo.add(second)
    default = await repo.get_default()
    assert default is not None
    assert default.destination.id == first.destination.id
    await repo.set_default(second.destination.id)
    default = await repo.get_default()
    assert default is not None
    assert default.destination.id == second.destination.id
    await repo.delete(second.destination.id)
    default = await repo.get_default()
    assert default is not None
    assert default.destination.id == first.destination.id


async def test__destinations__roundtrip_keeps_ciphertext_and_exposes_no_plaintext(sessions: SessionProvider) -> None:
    repo = SqlBackupDestinationRepository(sessions)
    stored = _stored("Main", prefix="studio", endpoint="http://minio:9000")
    await repo.add(stored)
    loaded = await repo.get(stored.destination.id)
    assert loaded is not None
    assert (loaded.access_key_enc, loaded.secret_key_enc) == ("sealed-access", "sealed-secret")
    assert loaded.destination.secret_key_set
    assert loaded.destination.spec.prefix == "studio"
    listed = await repo.list_all()
    assert [d.spec.name for d in listed] == ["Main"]
    assert "sealed" not in repr(listed)


async def test__destinations__name_unique_case_insensitive(sessions: SessionProvider) -> None:
    repo = SqlBackupDestinationRepository(sessions)
    one = _stored("Main")
    await repo.add(one)
    assert await repo.name_taken("main")
    assert not await repo.name_taken("main", except_id=one.destination.id)
    with pytest.raises(Exception, match="uq_backup_destinations_name"):
        await repo.add(_stored("MAIN"))


async def test__runs__only_one_running_and_finish_releases(sessions: SessionProvider) -> None:
    runs = SqlBackupRunRepository(sessions)
    first, second = _run(None), _run(None)
    assert await runs.start(first)
    assert not await runs.start(second)
    assert (await runs.running()) is not None
    finished = await runs.finish(
        first.id,
        status=RunStatus.ok,
        at=NOW + timedelta(seconds=5),
        size_bytes=123,
        backup_id="20261101T120000Z-aaaaaa",
        error=None,
        manifest_sha256="a" * 64,
    )
    assert finished.status is RunStatus.ok
    assert finished.duration_s == 5
    assert await runs.start(second)


async def test__runs__interrupt_page_alive_and_removed(sessions: SessionProvider) -> None:
    destinations = SqlBackupDestinationRepository(sessions)
    runs = SqlBackupRunRepository(sessions)
    stored = _stored("Main")
    await destinations.add(stored)
    dest = stored.destination.id
    done = _run(dest, minutes=0)
    await runs.start(done)
    await runs.finish(
        done.id,
        status=RunStatus.ok,
        at=NOW,
        size_bytes=1,
        backup_id="20261101T120000Z-aaaaaa",
        error=None,
        manifest_sha256=None,
    )
    stale = _run(dest, minutes=5)
    await runs.start(stale)
    assert await runs.interrupt_running(NOW + timedelta(hours=1)) == 1
    assert (await runs.get(stale.id)).status is RunStatus.interrupted  # type: ignore[union-attr]
    page = await runs.page(Window(limit=1, offset=0))
    assert page.total == 2
    assert page.items[0].id == stale.id
    assert [r.id for r in await runs.alive_for(dest)] == [done.id]
    await runs.mark_removed(done.id, NOW)
    assert await runs.alive_for(dest) == []
    last = await runs.last_finished()
    assert last is not None
    assert last.id == stale.id


async def test__runs__destination_delete_keeps_history(sessions: SessionProvider) -> None:
    destinations = SqlBackupDestinationRepository(sessions)
    runs = SqlBackupRunRepository(sessions)
    stored = _stored("Gone")
    await destinations.add(stored)
    run = _run(stored.destination.id)
    await runs.start(run)
    await destinations.delete(stored.destination.id)
    kept = await runs.get(run.id)
    assert kept is not None
    assert kept.destination_id is None
    assert kept.destination_name == "d"


async def test__admin_directory__only_active_admins(pg_migrated_engine: AsyncEngine, sessions: SessionProvider) -> None:
    async with pg_migrated_engine.begin() as conn:
        for uid, admin, status in (("a1", True, "active"), ("a2", True, "blocked"), ("u1", False, "active")):
            await conn.execute(
                text(
                    "INSERT INTO users (id, email, email_normalized, name, status, email_verified, "
                    "is_instance_admin, created_at) VALUES (:id, :e, :e, :n, :s, true, :a, now())"
                ),
                {"id": uid, "e": f"{uid}@x.org", "n": uid, "s": status, "a": admin},
            )
    assert await SqlAdminDirectory(sessions).active_admin_ids() == ["a1"]


async def test__notification_kind_backup_failed_is_accepted(pg_migrated_engine: AsyncEngine) -> None:
    async with pg_migrated_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, email_normalized, name, status, email_verified, "
                "is_instance_admin, created_at) VALUES ('a', 'a@x.org', 'a@x.org', 'a', 'active', true, true, now())"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO notifications (id, user_id, kind, payload, created_at) "
                "VALUES ('n1', 'a', 'backup_failed', '{}', now())"
            )
        )


def test__secret_columns_registered_for_reencrypt() -> None:
    labels = {column.label for column in encrypted_columns.all()}
    assert {"backup_destinations.access_key_enc", "backup_destinations.secret_key_enc"} <= labels


async def test__restore_database__into_migrated_database_with_partitioned_logs(
    pg_db_factory: Callable[[], Awaitable[AsyncEngine]],
) -> None:
    """Регресс: `pg_restore --clean` падал на унаследованных ограничениях секций журналов в мигрированной базе."""
    import io
    import subprocess
    from pathlib import Path

    from hse_doc_studio.infra.backup.producers import pg_env
    from hse_doc_studio.infra.backup.restore_target import RestoreTarget

    pg_dump, pg_restore = shutil.which("pg_dump"), shutil.which("pg_restore")
    if not (pg_dump and pg_restore):
        pytest.skip("нужны pg_dump и pg_restore")
    source, target = await pg_db_factory(), await pg_db_factory()
    async with source.begin() as conn:
        await conn.execute(text("INSERT INTO audit_log (action) VALUES ('x')"))
    dsn = source.url.render_as_string(hide_password=False)
    args, env = pg_env(dsn)
    dump = subprocess.run(  # noqa: S603
        [pg_dump, "--format=custom", "--no-owner", "--no-acl", *args], capture_output=True, env=env, check=False
    )
    if dump.returncode != 0:
        pytest.skip(f"pg_dump не снял базу (версия клиента?): {dump.stderr.decode()[-200:]}")
    restore_target = RestoreTarget(
        target,
        target.url.render_as_string(hide_password=False),
        Path("/nonexistent"),
        Path("/nonexistent"),
        None,  # type: ignore[arg-type]
        pg_restore_binary=pg_restore,
    )
    await restore_target.restore_database(io.BytesIO(dump.stdout))
    async with target.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM audit_log WHERE action = 'x'"))).scalar_one() == 1
