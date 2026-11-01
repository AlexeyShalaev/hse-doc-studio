"""Ошибки подсистемы бэкапов: коды стабильны, текст для человека русский и английский."""

from __future__ import annotations

from enum import StrEnum


class BackupErrorCode(StrEnum):
    invalid_input = "backup_invalid_input"
    not_found = "backup_not_found"
    conflict = "backup_conflict"
    destination_unreachable = "backup_destination_unreachable"
    already_running = "backup_already_running"
    no_destination = "backup_no_destination"
    secrets_unavailable = "backup_secrets_unavailable"
    integrity = "backup_integrity"
    unsupported = "backup_unsupported"
    unsafe_target = "backup_unsafe_target"


class BackupError(Exception):
    """Ожидаемый отказ; `field` называет поле формы, если ошибка в нём."""

    def __init__(self, code: BackupErrorCode, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
