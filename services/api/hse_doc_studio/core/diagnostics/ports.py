"""Порты самодиагностики: проверка реестра, хранилище состояния и пробы фактов (реализации в infra)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from hse_doc_studio.core.diagnostics.entities import CheckSpec, Verdict
from hse_doc_studio.core.diagnostics.facts import (
    DbFacts,
    JobFacts,
    MigrationFacts,
    ObjectFacts,
    RunnerFacts,
    SchedulerFacts,
    SmtpFacts,
    TlsFacts,
)
from hse_doc_studio.core.diagnostics.state import CheckState
from hse_doc_studio.core.diagnostics.thresholds import DiagThresholds


class IDiagCheck(Protocol):
    @property
    def spec(self) -> CheckSpec: ...

    async def run(self, thresholds: DiagThresholds, now: datetime) -> Verdict: ...


class IDiagStore(Protocol):
    async def load(self) -> dict[str, CheckState]: ...

    async def save(self, state: CheckState) -> None: ...


class IDatabaseProbe(Protocol):
    async def measure(self) -> DbFacts: ...


class IMigrationProbe(Protocol):
    async def read(self) -> MigrationFacts: ...


class IObjectProbe(Protocol):
    async def roundtrip(self) -> ObjectFacts:
        """Бакет доступен, пробный объект записан, прочитан и удалён."""
        ...


class IRunnerProbe(Protocol):
    async def read(self, now: datetime) -> RunnerFacts: ...


class IJobProbe(Protocol):
    async def read(self, now: datetime) -> JobFacts: ...


class ITlsProbe(Protocol):
    async def inspect(self, url: str | None) -> TlsFacts:
        """Срок действия сертификата по адресу; `url=None` значит адрес не настроен."""
        ...


class IBackupProbe(Protocol):
    async def last_ok_at(self) -> datetime | None: ...

    async def last_failed(self) -> bool: ...


class ISmtpProbe(Protocol):
    async def check(self) -> SmtpFacts: ...


class ISchedulerProbe(Protocol):
    async def read(self, now: datetime) -> SchedulerFacts: ...
