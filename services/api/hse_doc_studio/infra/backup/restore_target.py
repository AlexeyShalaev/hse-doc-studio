"""Установка, в которую восстанавливают бэкап: проверки состояния и запись базы, файлов, объектов."""

from __future__ import annotations

import asyncio
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import BinaryIO

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from hse_doc_studio.api.config import Settings
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.protocols import TargetState
from hse_doc_studio.core.storage.ports import IObjectStore
from hse_doc_studio.infra.backup.pgtools import resolve_binary, server_major
from hse_doc_studio.infra.backup.producers import ARC_DATA, ARC_PROJECTS, pg_env
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.engine import APP_NAME as API_APP_NAME
from hse_doc_studio.infra.db.engine import async_dsn, create_engine

RESTORE_APP_NAME = "hse-doc-studio-restore"
_CHUNK = 1024 * 1024
_MOVED = ("projects", "users", "gnupg")


class RestoreTarget:
    def __init__(
        self,
        engine: AsyncEngine,
        dsn: str,
        data_dir: Path,
        projects_root: Path,
        store: IObjectStore,
        *,
        pg_restore_binary: str = "pg_restore",
        timeout_s: float = 6 * 3600.0,
        owns_engine: bool = False,
    ) -> None:
        self._owns_engine = owns_engine
        self._engine = engine
        self._dsn = dsn
        self._data_dir = data_dir
        self._projects_root = projects_root
        self._store = store
        self._binary = pg_restore_binary
        self._timeout = timeout_s

    async def close(self) -> None:
        if self._owns_engine:
            await self._engine.dispose()

    async def api_is_running(self) -> bool:
        """Есть ли другие соединения с этой базой: у остановленной установки их нет."""
        async with self._engine.connect() as conn:
            others = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                    )
                )
            ).scalar_one()
        return int(others) > 0

    async def drop_api_connections(self) -> int:
        """Обрывает оставшиеся соединения самого api (потоки и запросы, начатые до режима обслуживания).

        Чужие приложения не трогаются: их `api_is_running` по-прежнему считает помехой.
        """
        async with self._engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                        "AND application_name = :app"
                    ),
                    {"app": API_APP_NAME},
                )
            ).all()
        return len(rows)

    async def other_connections(self) -> list[str]:
        """Кто ещё подключён к базе: `приложение/состояние`, для сообщения об ошибке."""
        async with self._engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT coalesce(nullif(application_name, ''), '?'), coalesce(state, '?') "
                        "FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                    )
                )
            ).all()
        return [f"{app}/{state}" for app, state in rows]

    async def describe(self) -> TargetState:
        users = projects = 0
        async with self._engine.connect() as conn:
            if (await conn.execute(text("SELECT to_regclass('public.users')"))).scalar_one() is not None:
                users = int((await conn.execute(text("SELECT count(*) FROM users"))).scalar_one())
            if (await conn.execute(text("SELECT to_regclass('public.projects')"))).scalar_one() is not None:
                projects = int((await conn.execute(text("SELECT count(*) FROM projects"))).scalar_one())
        folders = await asyncio.to_thread(self._count_project_folders)
        objects = len(await self._store.list_objects(""))
        return TargetState(users=users, projects=max(projects, folders), objects=objects)

    def _count_project_folders(self) -> int:
        root = self._projects_root
        return sum(1 for entry in root.iterdir() if entry.is_dir()) if root.is_dir() else 0

    async def current_revision_known(self, revision: str | None) -> bool:
        if revision is None:
            return True
        known = {s.revision for s in ScriptDirectory.from_config(migrator._config()).walk_revisions()}  # noqa: SLF001
        return revision in known

    async def restore_database(self, source: BinaryIO) -> None:
        await asyncio.to_thread(self._pg_restore, source)

    def _pg_restore(self, source: BinaryIO) -> None:
        args, env = pg_env(self._dsn)
        command = [
            self._binary,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-acl",
            "--single-transaction",
            "--exit-on-error",
            *args,
        ]
        with tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=err, env=env)  # noqa: S603
            assert proc.stdin is not None  # noqa: S101
            try:
                try:
                    while chunk := source.read(_CHUNK):
                        proc.stdin.write(chunk)
                finally:
                    proc.stdin.close()
                code = proc.wait(timeout=self._timeout)
            except BaseException:
                proc.kill()
                proc.wait()
                raise
            if code != 0:
                err.seek(0)
                tail = err.read().decode(errors="replace").strip()[-800:]
                raise BackupError(BackupErrorCode.integrity, f"pg_restore exited with {code}: {tail}")

    async def restore_files(self, source: BinaryIO, *, move_existing: bool, stamp: str) -> int:
        return await asyncio.to_thread(self._extract, source, move_existing, stamp)

    def _extract(self, source: BinaryIO, move_existing: bool, stamp: str) -> int:
        roots = {ARC_DATA: self._data_dir, ARC_PROJECTS: self._projects_root}
        if move_existing:
            for name in _MOVED:
                path = self._data_dir / name
                if path.exists():
                    path.rename(path.with_name(f"{name}.before-restore-{stamp}"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        with tarfile.open(fileobj=source, mode="r|gz") as tar:
            for member in tar:
                head, _, rest = member.name.partition("/")
                dest = roots.get(head)
                if dest is None or not rest:
                    continue
                dest.mkdir(parents=True, exist_ok=True)
                tar.extract(member.replace(name=rest, deep=False), path=dest, filter="data")
                count += 1 if member.isfile() else 0
        return count

    async def restore_objects(self, source: BinaryIO) -> int:
        loop = asyncio.get_running_loop()
        return await asyncio.to_thread(self._put_all, source, loop)

    def _put_all(self, source: BinaryIO, loop: asyncio.AbstractEventLoop) -> int:
        count = 0
        with tarfile.open(fileobj=source, mode="r|gz") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                with tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024) as spool:
                    while chunk := handle.read(_CHUNK):
                        spool.write(chunk)
                    spool.seek(0)
                    asyncio.run_coroutine_threadsafe(self._store.put(member.name, spool), loop).result()  # type: ignore[arg-type]
                count += 1
        return count


class RestoreTargetFactory:
    """Цель для восстановления из работающего api: свой движок БД, пул самого api не участвует."""

    def __init__(self, cfg: Settings, store: IObjectStore) -> None:
        self._cfg = cfg
        self._store = store

    async def open(self) -> RestoreTarget:
        cfg = self._cfg
        data_dir = cfg.data_dir.expanduser()
        projects_root = (cfg.server.projects_root or data_dir / "projects").expanduser()
        engine = create_engine(cfg.db, application_name=RESTORE_APP_NAME)
        try:
            binary = resolve_binary(cfg.backups.pg_restore_binary, await server_major(engine))
        except BaseException:
            await engine.dispose()
            raise
        return RestoreTarget(
            engine,
            async_dsn(cfg.db.dsn),
            data_dir,
            projects_root,
            self._store,
            pg_restore_binary=binary,
            timeout_s=cfg.backups.dump_timeout_s,
            owns_engine=True,
        )
