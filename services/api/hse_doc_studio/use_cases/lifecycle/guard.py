"""Контроль места: замеры томов и базы, предупреждения админам, безопасный режим при критической нехватке."""

from __future__ import annotations

import structlog

from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.lifecycle.disk import SafeMode, StorageLevel, effective_thresholds
from hse_doc_studio.core.lifecycle.ports import IAdminDirectory, IStorageProbe, VolumeUsage

logger = structlog.get_logger(__name__)

ALERT_CODES = {StorageLevel.warning: "storage_warning", StorageLevel.critical: "storage_critical"}


class StorageGuard:
    """Раз в интервал: меряет, считает уровень, предупреждает во «Входящих» и включает безопасный режим.

    Предупреждение уходит каждому админу не чаще раза в сутки на том и уровень (ключ дедупликации с датой): пока
    проблема есть, уведомление поднимается заново как непрочитанное, а не плодит строки. Безопасный режим снимается сам,
    когда место освободилось ниже критического порога.
    """

    def __init__(
        self,
        probe: IStorageProbe,
        settings: IInstanceSettingsRepository,
        notifier: INotifier,
        admins: IAdminDirectory,
        safe_mode: SafeMode,
        *,
        safe_mode_enabled: bool,
        clock: Clock = utc_now,
    ) -> None:
        self._probe = probe
        self._settings = settings
        self._notifier = notifier
        self._admins = admins
        self._safe = safe_mode
        self._safe_enabled = safe_mode_enabled
        self._clock = clock
        self._last: list[VolumeUsage] = []

    async def snapshot(self) -> list[VolumeUsage]:
        """Последний замер; пустой, пока проба ещё не отработала (тогда меряем сразу)."""
        if not self._last:
            self._last = await self._probe.volumes()
        return self._last

    @property
    def safe_mode_active(self) -> bool:
        return self._safe.active

    async def refresh(self) -> list[VolumeUsage]:
        """Свежий замер без предупреждений и без смены безопасного режима (его ведёт `tick`)."""
        self._last = await self._probe.volumes()
        return self._last

    @property
    def last(self) -> list[VolumeUsage]:
        return self._last

    async def tick(self) -> StorageLevel:
        volumes = await self._probe.volumes()
        self._last = volumes
        thresholds = effective_thresholds(await self._settings.get_all())
        worst = StorageLevel.ok
        worst_name = ""
        for volume in volumes:
            level = thresholds.level(volume.used_ratio)
            if level > worst:
                worst, worst_name = level, volume.name
            if level is not StorageLevel.ok:
                await self._alert(volume, level)
        critical = worst is StorageLevel.critical and self._safe_enabled
        if critical != self._safe.active:
            logger.warning("storage_safe_mode", active=critical, volume=worst_name)
        self._safe.set(critical, worst_name if critical else None)
        return worst

    async def _alert(self, volume: VolumeUsage, level: StorageLevel) -> None:
        ratio = volume.used_ratio
        percent = f"{ratio * 100:.0f}" if ratio is not None else "?"
        day = self._clock().date().isoformat()
        payload = NotificationPayload(outcome=ALERT_CODES[level], ref_id=volume.name, excerpt=percent)
        try:
            for admin_id in await self._admins.active_admin_ids():
                await self._notifier.notify(
                    admin_id,
                    NotificationKind.system_alert,
                    payload,
                    dedupe_key=f"storage:{volume.name}:{ALERT_CODES[level]}:{day}",
                )
        except Exception:
            logger.exception("storage_alert_failed", volume=volume.name)
