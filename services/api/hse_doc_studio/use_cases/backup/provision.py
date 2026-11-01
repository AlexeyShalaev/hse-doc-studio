"""Начальная настройка бэкапов из окружения (Helm, compose): назначение по умолчанию и расписание.

Применяется один раз: если в базе уже есть назначения, ничего не меняется, поэтому правки админа переживают рестарты.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from hse_doc_studio.core.backup.entities import BackupSettings, DestinationKind, DestinationSpec, EncryptionMode
from hse_doc_studio.core.backup.errors import BackupError
from hse_doc_studio.core.backup.protocols import IBackupDestinationRepository
from hse_doc_studio.core.backup.schedule import Schedule, ScheduleKind
from hse_doc_studio.use_cases.backup.destinations import CreateDestinationUC, DestinationInput
from hse_doc_studio.use_cases.backup.settings import UpdateBackupSettingsUC

logger = structlog.get_logger()


@dataclass(frozen=True)
class ProvisionPlan:
    destination: DestinationInput
    settings: BackupSettings
    passphrase: str | None = None


def build_plan(  # noqa: PLR0913
    *,
    kind: str,
    name: str,
    local_path: str,
    endpoint: str | None,
    region: str,
    bucket: str | None,
    prefix: str,
    path_style: bool,
    access_key: str | None,
    secret_key: str | None,
    schedule_enabled: bool,
    schedule_kind: str,
    interval_hours: int,
    cron: str,
    keep_last: int,
    keep_days: int,
    encryption_mode: str,
    passphrase: str | None,
    notify_admins: bool,
) -> ProvisionPlan:
    is_s3 = kind == DestinationKind.s3.value
    spec = DestinationSpec(
        name=name,
        kind=DestinationKind(kind),
        endpoint=(endpoint or None) if is_s3 else None,
        region=region,
        bucket=(bucket or None) if is_s3 else None,
        prefix=prefix if is_s3 else "",
        path_style=path_style,
        local_path=None if is_s3 else local_path,
    )
    return ProvisionPlan(
        destination=DestinationInput(
            spec, access_key=access_key or None, secret_key=secret_key or None, make_default=True
        ),
        settings=BackupSettings(
            enabled=schedule_enabled,
            schedule=Schedule(kind=ScheduleKind(schedule_kind), interval_hours=interval_hours, cron=cron),
            keep_last=keep_last,
            keep_days=keep_days,
            encryption_mode=EncryptionMode(encryption_mode),
            notify_admins=notify_admins,
        ),
        passphrase=passphrase or None,
    )


class ProvisionBackupUC:
    def __init__(
        self,
        destinations: IBackupDestinationRepository,
        create: CreateDestinationUC,
        settings: UpdateBackupSettingsUC,
    ) -> None:
        self._destinations = destinations
        self._create = create
        self._settings = settings

    async def execute(self, plan: ProvisionPlan) -> bool:
        """True, если настройка применена; ошибки конфигурации пишутся в журнал и не роняют api."""
        if await self._destinations.list_all():
            return False
        try:
            await self._create.create(None, plan.destination)
            await self._settings.apply(None, plan.settings, passphrase=plan.passphrase)
        except BackupError as exc:
            logger.warning("backup provisioning failed", code=exc.code.value, error=exc.message, field=exc.field)
            return False
        logger.info("backup provisioned", destination=plan.destination.spec.name)
        return True
