from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hse_doc_studio.core.diagnostics.acceptance import Acceptance
from hse_doc_studio.core.server_update.entities import ReleaseInfo, UpdateRun, UpdateSettings
from hse_doc_studio.core.server_update.versions import DowngradeTarget


@dataclass(frozen=True)
class UpdateStatus:
    settings: UpdateSettings
    current_version: str
    executor_enabled: bool
    updater_online: bool
    updater_seen_at: datetime | None
    updater_version: str | None
    releases: tuple[ReleaseInfo, ...]
    available: ReleaseInfo | None  # самый свежий релиз новее текущей версии
    auto_target: ReleaseInfo | None  # что политика поставит сама
    checked_at: datetime | None
    check_error: str | None
    in_window: bool
    next_window_at: datetime | None
    backup_destination_configured: bool
    active_run: UpdateRun | None
    last_run: UpdateRun | None
    rollback_version: str | None  # версия, на которую можно вернуться кнопкой
    rollback_needs_restore: bool  # возврат потребует восстановить базу из снимка (данные после обновления теряются)
    executor: str = "none"  # compose, kubernetes или none
    rollback_blocked: bool = False  # kubernetes: обновление меняло схему, откат образа без отката базы невозможен
    risk_confirmation_required: bool = False  # kubernetes: бэкап не пройдёт, ручной запуск требует accept_risk
    backups_accepted: Acceptance | None = None  # «бэкапы не делаю сознательно»: подтверждение риска не спрашиваем
    auto_update_enabled: bool = (
        False  # политика `auto`: пока false, сам ничего не ставится, проверка и уведомления идут
    )
    db_revision: str | None = None  # ревизия схемы базы сейчас (head работающего образа)
    updater_can_downgrade: bool = False  # апдейтер умеет откат на выбранную версию (сообщает в poll)
    downgrade_targets: tuple[DowngradeTarget, ...] = ()  # прежние релизы с вердиктом по схеме базы
