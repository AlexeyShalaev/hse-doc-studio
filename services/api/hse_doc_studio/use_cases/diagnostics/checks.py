"""Проверки реестра: факты от проб, вердикт от правил. Каждая проверка отвечает за один пункт `CHECKS`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from hse_doc_studio.core.backup.protocols import IBackupDestinationRepository
from hse_doc_studio.core.backup.settings import settings_from
from hse_doc_studio.core.diagnostics import rules
from hse_doc_studio.core.diagnostics.entities import CHECK_BY_ID, CheckId, CheckSpec, Verdict
from hse_doc_studio.core.diagnostics.facts import BackupFacts, DiskFacts
from hse_doc_studio.core.diagnostics.ports import (
    IBackupProbe,
    IDatabaseProbe,
    IJobProbe,
    IMigrationProbe,
    IObjectProbe,
    IRunnerProbe,
    ISchedulerProbe,
    ISmtpProbe,
    ITlsProbe,
)
from hse_doc_studio.core.diagnostics.thresholds import KEY_LAST_TICK, DiagThresholds
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.lifecycle.disk import StorageLevel, effective_thresholds
from hse_doc_studio.core.lifecycle.ports import ILifecycleRuns
from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine
from hse_doc_studio.use_cases.lifecycle.guard import StorageGuard


class _Base:
    check_id: CheckId

    @property
    def spec(self) -> CheckSpec:
        return CHECK_BY_ID[self.check_id.value]


class DatabaseCheck(_Base):
    check_id = CheckId.database

    def __init__(self, probe: IDatabaseProbe) -> None:
        self._probe = probe

    async def run(self, t: DiagThresholds, now: datetime) -> Verdict:
        return rules.judge_database(await self._probe.measure(), t)


class MigrationsCheck(_Base):
    check_id = CheckId.migrations

    def __init__(self, probe: IMigrationProbe) -> None:
        self._probe = probe

    async def run(self, t: DiagThresholds, now: datetime) -> Verdict:
        return rules.judge_migrations(await self._probe.read())


class ObjectStorageCheck(_Base):
    check_id = CheckId.object_storage

    def __init__(self, probe: IObjectProbe) -> None:
        self._probe = probe

    async def run(self, t: DiagThresholds, now: datetime) -> Verdict:
        return rules.judge_object_storage(await self._probe.roundtrip(), t)


class RunnersCheck(_Base):
    check_id = CheckId.runners

    def __init__(self, probe: IRunnerProbe) -> None:
        self._probe = probe

    async def run(self, t: DiagThresholds, now: datetime) -> Verdict:
        return rules.judge_runners(await self._probe.read(now))


class JobsCheck(_Base):
    check_id = CheckId.jobs

    def __init__(self, probe: IJobProbe) -> None:
        self._probe = probe

    async def run(self, t: DiagThresholds, now: datetime) -> Verdict:
        return rules.judge_jobs(await self._probe.read(now), t)


class DiskCheck(_Base):
    """Опирается на контроль места: те же тома и пороги (`storage.*`), что у `StorageGuard`, плюс политики хранения."""

    check_id = CheckId.disk

    def __init__(
        self,
        guard: StorageGuard,
        settings: IInstanceSettingsRepository,
        engine: LifecycleEngine,
        runs: ILifecycleRuns,
    ) -> None:
        self._guard = guard
        self._settings = settings
        self._engine = engine
        self._runs = runs

    async def run(self, t: DiagThresholds, now: datetime) -> Verdict:
        volumes = await self._guard.refresh()
        thresholds = effective_thresholds(await self._settings.get_all())
        # Худший том: сначала по уровню, затем по занятости.
        ranked = [(thresholds.level(v.used_ratio), v.used_ratio, v.name) for v in volumes if v.used_ratio is not None]
        level, name, percent = StorageLevel.ok, None, None
        if ranked:
            level, ratio, name = max(ranked, key=lambda item: (item[0], item[1]))
            percent = round(ratio * 100)
        sized = [(c.size.bytes, k) for k, c in self._engine.counters.items() if c.size is not None]
        biggest = max(sized)[1] if sized else None
        errors = sum(1 for r in (await self._runs.all()).values() if r.last_error)
        return rules.judge_disk(DiskFacts(level, name, percent, self._guard.safe_mode_active, biggest, errors))


class TlsCheck(_Base):
    def __init__(self, check_id: CheckId, probe: ITlsProbe, url: Callable[[], list[str]]) -> None:
        self.check_id = check_id
        self._probe = probe
        self._urls = url

    async def run(self, t: DiagThresholds, now: datetime) -> Verdict:
        urls = self._urls()
        if not urls:
            return rules.judge_tls(await self._probe.inspect(None), t)
        verdicts = [rules.judge_tls(await self._probe.inspect(u), t) for u in urls]
        return max(verdicts, key=lambda v: v.status)


class BackupsCheck(_Base):
    check_id = CheckId.backups

    def __init__(
        self,
        probe: IBackupProbe,
        settings: IInstanceSettingsRepository,
        destinations: IBackupDestinationRepository,
        *,
        feature_enabled: bool,
    ) -> None:
        self._probe = probe
        self._settings = settings
        self._destinations = destinations
        self._feature = feature_enabled

    async def run(self, t: DiagThresholds, now: datetime) -> Verdict:
        enabled = self._feature and settings_from(await self._settings.get_all()).enabled
        facts = BackupFacts(
            enabled=enabled,
            has_destination=await self._destinations.get_default() is not None,
            last_ok_at=await self._probe.last_ok_at(),
            last_failed=await self._probe.last_failed(),
            now=now,
        )
        return rules.judge_backups(facts, t)


class SmtpCheck(_Base):
    check_id = CheckId.smtp

    def __init__(self, probe: ISmtpProbe) -> None:
        self._probe = probe

    async def run(self, t: DiagThresholds, now: datetime) -> Verdict:
        return rules.judge_smtp(await self._probe.check())


class SchedulerCheck(_Base):
    check_id = CheckId.scheduler

    def __init__(self, probe: ISchedulerProbe, settings: IInstanceSettingsRepository, interval_s: float) -> None:
        self._probe = probe
        self._settings = settings
        self._interval = interval_s

    async def run(self, t: DiagThresholds, now: datetime) -> Verdict:
        facts = await self._probe.read(now)
        raw = (await self._settings.get_all()).get(KEY_LAST_TICK)
        tick = None
        if isinstance(raw, str):
            try:
                tick = datetime.fromisoformat(raw)
            except ValueError:
                tick = None
        return rules.judge_scheduler(replace(facts, last_tick_at=tick, tick_interval_s=self._interval, now=now))
