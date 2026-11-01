"""Пробы самодиагностики. Возвращают факты; вердикт выносят правила ядра. Секреты в факты не попадают."""

from __future__ import annotations

import asyncio
import contextlib
import ssl
import time
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography import x509
from sqlalchemy import func, select, text

from hse_doc_studio.core.background import BackgroundTaskRunner
from hse_doc_studio.core.diagnostics.facts import (
    DbFacts,
    JobFacts,
    MigrationFacts,
    ObjectFacts,
    RunnerFacts,
    SchedulerFacts,
    SmtpFacts,
    TaskFact,
    TlsFacts,
)
from hse_doc_studio.core.jobs.autoscale import IQueueMetricsReader
from hse_doc_studio.core.jobs.routing import RunnerScope
from hse_doc_studio.core.storage import IObjectStore
from hse_doc_studio.infra.db.leader import BACKGROUND_LEADER_LOCK_KEY
from hse_doc_studio.infra.db.migrator import head_revision, known_revisions
from hse_doc_studio.infra.db.orm.backup import BackupRunRow
from hse_doc_studio.infra.db.orm.jobs import JobRow, RunnerRow
from hse_doc_studio.infra.db.session import SessionProvider

_PROBE_TLS_TIMEOUT_S = 8.0


def _short(exc: BaseException) -> str:
    return type(exc).__name__


class DatabaseProbe:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def measure(self) -> DbFacts:
        started = time.monotonic()
        try:
            async with self._sessions.use() as db:
                await db.execute(text("SELECT 1"))
                latency = (time.monotonic() - started) * 1000
                version = (await db.execute(text("SHOW server_version"))).scalar_one()
        except Exception as exc:
            return DbFacts(error=_short(exc))
        return DbFacts(latency_ms=latency, version=str(version).split(" ")[0])


class MigrationProbe:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def read(self) -> MigrationFacts:
        async with self._sessions.use() as db:
            current = (await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))).scalar_one_or_none()
        return MigrationFacts(current, head_revision(), current is None or current in known_revisions())


class ObjectProbe:
    """Круг записи и чтения пробного объекта в основном хранилище (бакет S3 или каталог)."""

    def __init__(self, store: IObjectStore, *, bucket: str | None) -> None:
        self._store = store
        self._bucket = bucket

    async def roundtrip(self) -> ObjectFacts:
        kind = "s3" if self._bucket else "fs"
        base = ObjectFacts(kind, self._bucket)
        started = time.monotonic()
        try:
            await self._store.check()
        except Exception:
            return ObjectFacts(kind, self._bucket, error_stage="check")
        key = f"diag-probe/{uuid4().hex}"
        payload = uuid4().bytes
        try:
            await self._store.put(key, payload, content_type="application/octet-stream")
        except Exception:
            return ObjectFacts(kind, self._bucket, error_stage="write")
        stage: str | None = None
        try:
            try:
                got = await self._store.get(key)
                stage = None if got == payload else "mismatch"
            except Exception:
                stage = "read"
        finally:
            try:
                await self._store.delete(key)
            except Exception:
                stage = stage or "delete"
        if stage is not None:
            return ObjectFacts(kind, self._bucket, error_stage=stage)
        return ObjectFacts(base.kind, base.bucket, roundtrip_ms=(time.monotonic() - started) * 1000)


class RunnerProbe:
    def __init__(self, sessions: SessionProvider, metrics: IQueueMetricsReader) -> None:
        self._sessions = sessions
        self._metrics = metrics

    async def read(self, now: datetime) -> RunnerFacts:
        stmt = select(func.count()).where(RunnerRow.owner_kind == "instance", RunnerRow.revoked_at.is_(None))
        async with self._sessions.use() as db:
            registered = int((await db.execute(stmt)).scalar_one())
        m = await self._metrics.read(now)
        return RunnerFacts(registered, m.runners_online, m.queued)


class JobProbe:
    def __init__(self, sessions: SessionProvider, metrics: IQueueMetricsReader) -> None:
        self._sessions = sessions
        self._metrics = metrics

    async def read(self, now: datetime) -> JobFacts:
        stmt = select(func.count(), func.min(JobRow.lease_until)).where(
            JobRow.state == "running", JobRow.runner_scope == RunnerScope.shared.value, JobRow.lease_until < now
        )
        async with self._sessions.use() as db:
            stuck, oldest = (await db.execute(stmt)).one()
        m = await self._metrics.read(now)
        overdue = max(0.0, (now - oldest).total_seconds()) if oldest is not None else 0.0
        return JobFacts(m.queued, m.oldest_wait_s, int(stuck), overdue)


def _not_after(der: bytes) -> datetime:
    cert = x509.load_der_x509_certificate(der)
    return cert.not_valid_after_utc


class TlsProbe:
    """Срок действия сертификата сервера по адресу. Проверка цепочки не нужна: интересен именно срок."""

    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock

    async def inspect(self, url: str | None) -> TlsFacts:
        if not url:
            return TlsFacts(configured=False)
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.scheme != "https" or not host:
            return TlsFacts(configured=True, https=False, host=host)
        port = parts.port or 443
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ctx, server_hostname=host), _PROBE_TLS_TIMEOUT_S
            )
        except Exception as exc:
            return TlsFacts(configured=True, host=host, error=_short(exc))
        try:
            ssl_obj = writer.get_extra_info("ssl_object")
            der = ssl_obj.getpeercert(binary_form=True) if ssl_obj is not None else None
            if not der:
                return TlsFacts(configured=True, host=host, error="no_certificate")
            days = (_not_after(der) - self._clock()).days
            return TlsFacts(configured=True, host=host, days_left=days)
        except Exception as exc:
            return TlsFacts(configured=True, host=host, error=_short(exc))
        finally:
            writer.close()


class BackupProbe:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def last_ok_at(self) -> datetime | None:
        stmt = select(func.max(BackupRunRow.finished_at)).where(BackupRunRow.status == "ok")
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).scalar_one_or_none()

    async def last_failed(self) -> bool:
        stmt = (
            select(BackupRunRow.status)
            .where(BackupRunRow.status != "running")
            .order_by(BackupRunRow.started_at.desc())
            .limit(1)
        )
        async with self._sessions.use() as db:
            status = (await db.execute(stmt)).scalar_one_or_none()
        return status in {"failed", "interrupted"}


class SmtpProbe:
    """Соединение с SMTP без отправки письма: подключение, STARTTLS и вход."""

    def __init__(self, params: Callable[[], object]) -> None:
        self._params = params

    async def check(self) -> SmtpFacts:
        import aiosmtplib  # noqa: PLC0415

        params = await self._params()  # type: ignore[misc]
        if params is None:
            return SmtpFacts(configured=False)
        started = time.monotonic()
        client = aiosmtplib.SMTP(
            hostname=params.host,
            port=params.port,
            use_tls=params.security == "tls",
            start_tls=False,
            timeout=params.timeout_s,
        )
        try:
            await client.connect()
            if params.security == "starttls":
                await client.starttls()
            if params.username:
                await client.login(params.username, params.password or "")
            await client.noop()
        except Exception as exc:
            return SmtpFacts(configured=True, error=_short(exc))
        finally:
            with contextlib.suppress(Exception):  # соединение могло не открыться
                await client.quit()
        return SmtpFacts(configured=True, latency_ms=(time.monotonic() - started) * 1000)


class SchedulerProbe:
    """Лидер ищется по advisory-локу в `pg_locks`, значит виден из любого экземпляра; задачи видны только лидеру."""

    def __init__(self, sessions: SessionProvider, runner: Callable[[], BackgroundTaskRunner | None]) -> None:
        self._sessions = sessions
        self._runner = runner

    async def read(self, now: datetime) -> SchedulerFacts:
        stmt = text(
            "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted "
            "AND classid = 0 AND objid = :key AND objsubid = 1)"
        )
        async with self._sessions.use() as db:
            present = bool((await db.execute(stmt, {"key": BACKGROUND_LEADER_LOCK_KEY})).scalar_one())
        runner = self._runner()
        here = runner is not None and runner.is_leader
        tasks: list[TaskFact] = []
        if runner is not None and here:
            stats = runner.stats()
            for name, task in runner.tasks().items():
                st = stats[name]
                last = datetime.fromtimestamp(st.last_run_at, tz=UTC) if st.last_run_at else None
                tasks.append(TaskFact(name, task.interval_s, st.runs, st.failures, last))
        return SchedulerFacts(present, here, tasks, now=now)
