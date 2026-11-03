from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UpdateOptions:
    """Параметры процесса из окружения (`HSE_STUDIO__SERVER_UPDATE__*`), не из админки."""

    current_version: str
    executor_enabled: bool  # false: helm или исполнитель выключен, обновление ставит оператор
    executor: str = "compose"  # вид исполнителя из настройки: compose или kubernetes (kubernetes без снимка базы)
    check_interval_s: float = 6 * 3600.0
    retry_interval_s: float = 1800.0
    updater_stale_s: float = 90.0  # столько апдейтер может молчать и считаться живым
    queued_timeout_s: float = 600.0  # запуск ждёт апдейтер дольше и отменяется
    run_lost_s: float = 900.0  # апдейтер молчит посреди запуска дольше: запуск считается потерянным
    backup_wait_s: float = 2 * 3600.0

    @property
    def snapshotless(self) -> bool:
        """kubernetes: снимка базы и отката схемы нет, защита это бэкап и откат образа, пока схема не менялась."""
        return self.executor == "kubernetes"
