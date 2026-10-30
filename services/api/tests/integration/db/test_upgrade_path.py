"""Путь обновления и восстановления: данные прошлой версии переживают миграции, старый бэкап догоняется."""

from __future__ import annotations

import hashlib

import pytest
from alembic.script import ScriptDirectory
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.errors import DbAheadError
from hse_doc_studio.infra.storage.blobs import ObjectBlobStore
from hse_doc_studio.infra.storage.s3 import S3ObjectStore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [pytest.mark.pg, pytest.mark.s3]

_SEED = text("INSERT INTO instance_meta (key, value) VALUES ('install_id', 'abc'), ('k', 'v')")
_META = text("SELECT key, value FROM instance_meta ORDER BY key")


def _chain() -> list[str]:
    """Ревизии от самой старой к head."""
    scripts = ScriptDirectory.from_config(migrator._config())
    return [script.revision for script in reversed(list(scripts.walk_revisions()))]


async def _meta(engine: AsyncEngine) -> list[tuple[str, str]]:
    async with engine.connect() as conn:
        return [(row[0], row[1]) for row in (await conn.execute(_META)).all()]


async def test__upgrade__every_step_from_first_revision__keeps_data(pg_engine: AsyncEngine) -> None:
    chain = _chain()
    await migrator.upgrade(pg_engine, chain[0])
    async with pg_engine.begin() as conn:
        await conn.execute(_SEED)

    for revision in chain[1:]:
        await migrator.upgrade(pg_engine, revision)
        assert await _meta(pg_engine) == [("install_id", "abc"), ("k", "v")], revision

    assert await migrator.current_revision(pg_engine) == migrator.head_revision()
    assert await migrator.check_drift(pg_engine) == []


async def test__upgrade__previous_to_head__applies_over_populated_database(pg_engine: AsyncEngine) -> None:
    chain = _chain()
    await migrator.upgrade(pg_engine, chain[-2])
    async with pg_engine.begin() as conn:
        await conn.execute(_SEED)

    assert await migrator.migrate_if_needed(pg_engine) is True

    assert await migrator.current_revision(pg_engine) == chain[-1]
    assert await _meta(pg_engine) == [("install_id", "abc"), ("k", "v")]


async def test__rollback__one_step_back_and_forward__keeps_earlier_data(pg_engine: AsyncEngine) -> None:
    """Откат образа на прежнюю версию: схема на шаг назад, данные ранних таблиц целы, повторный апгрейд проходит."""
    await migrator.upgrade(pg_engine)
    async with pg_engine.begin() as conn:
        await conn.execute(_SEED)

    await migrator.downgrade(pg_engine, "-1")
    assert await migrator.current_revision(pg_engine) == _chain()[-2]
    assert await _meta(pg_engine) == [("install_id", "abc"), ("k", "v")]

    await migrator.upgrade(pg_engine)
    assert await migrator.current_revision(pg_engine) == migrator.head_revision()
    assert await migrator.check_drift(pg_engine) == []


async def test__restore__backup_older_than_code__is_caught_up_on_start(pg_db_factory) -> None:
    """Бэкап прошлого выпуска, поднятый новым образом, догоняется миграциями без потери данных."""
    backup = await pg_db_factory()
    await migrator.downgrade(backup, _chain()[-2])
    async with backup.begin() as conn:
        await conn.execute(_SEED)

    await migrator.ensure_db_current(backup, auto_migrate=True)

    assert await migrator.current_revision(backup) == migrator.head_revision()
    assert await _meta(backup) == [("install_id", "abc"), ("k", "v")]


async def test__restore__backup_newer_than_code__refuses_to_start(pg_engine: AsyncEngine) -> None:
    await migrator.upgrade(pg_engine)
    async with pg_engine.begin() as conn:
        await conn.execute(text("UPDATE alembic_version SET version_num = 'from_the_future'"))

    with pytest.raises(DbAheadError):
        await migrator.ensure_db_current(pg_engine, auto_migrate=True)


async def test__restore__registry_ahead_of_bucket__missing_blobs_are_found(
    pg_migrated_engine: AsyncEngine, s3_client, s3_bucket: str
) -> None:
    """БД восстановлена из более нового бэкапа, чем S3: сверка реестра с бакетом перечисляет пропавшие блобы."""
    store = S3ObjectStore(s3_client, s3_bucket, max_object_bytes=10 * 1024**2, multipart_threshold_bytes=5 * 1024**2)
    blobs = ObjectBlobStore(store)
    kept = await blobs.put(b"kept")
    lost_sha = hashlib.sha256(b"lost").hexdigest()
    async with pg_migrated_engine.begin() as conn:
        for sha, size in ((kept.sha256, 4), (lost_sha, 4)):
            await conn.execute(
                text("INSERT INTO blobs (sha256, size) VALUES (:sha, :size)"), {"sha": sha, "size": size}
            )

    async with pg_migrated_engine.connect() as conn:
        registered = {row[0] for row in (await conn.execute(text("SELECT sha256 FROM blobs"))).all()}
    present = await blobs.has_many(registered)

    assert registered - present == {lost_sha}
