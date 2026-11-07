from __future__ import annotations

from enum import StrEnum


class UpdateErrorCode(StrEnum):
    invalid_input = "invalid_input"
    not_found = "not_found"
    executor_unavailable = "executor_unavailable"  # helm или исполнитель отключён: ставят вручную
    updater_offline = "updater_offline"
    already_running = "already_running"
    nothing_to_update = "nothing_to_update"
    unknown_version = "unknown_version"
    no_previous_version = "no_previous_version"
    not_cancellable = "not_cancellable"
    unauthorized = "unauthorized"
    unsafe_version_jump = "unsafe_version_jump"
    risk_not_confirmed = "risk_not_confirmed"  # kubernetes без бэкапа: обновление только с явным подтверждением риска
    schema_incompatible = "schema_incompatible"  # целевая версия работает на другой схеме базы: откат не выполняется
    digest_missing = "digest_missing"  # у релиза нет дайджеста образа, а проверка образа включена
    updater_outdated = "updater_outdated"  # апдейтер старой версии не умеет откат на выбранную версию
    rollback_unsafe = "rollback_unsafe"  # kubernetes: обновление меняло схему, образ без отката базы не поднимется


class UpdateError(Exception):
    def __init__(self, code: UpdateErrorCode, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
