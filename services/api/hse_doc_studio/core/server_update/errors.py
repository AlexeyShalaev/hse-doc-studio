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


class UpdateError(Exception):
    def __init__(self, code: UpdateErrorCode, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
