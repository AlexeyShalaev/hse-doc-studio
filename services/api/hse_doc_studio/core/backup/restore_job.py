"""Восстановление из админки: фазы, задание и его журнал (в памяти процесса, см. docs/design/backups.md, раздел 5)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.backup.entities import Manifest
from hse_doc_studio.core.backup.protocols import TargetState

LOG_MAX = 300


class RestorePhase(StrEnum):
    verifying = "verifying"  # предпросмотр: манифест, ключ, схема, sha256 и расшифровка каждой части
    verified = "verified"  # предпросмотр прошёл, ничего не записано, можно подтверждать
    applying = "applying"  # режим обслуживания включён, идёт запись
    done = "done"  # записано; процесс перезапускается
    failed = "failed"  # ошибка проверки или записи


@dataclass
class RestoreJob:
    id: str
    destination_id: str
    destination_name: str
    backup_id: str
    started_at: datetime
    phase: RestorePhase = RestorePhase.verifying
    manifest: Manifest | None = None
    target: TargetState | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error: str | None = None
    # Запись уже началась: база целиком (одна транзакция) или частично файлы и объекты; откат режима обслуживания
    # без разбора такой установки небезопасен.
    wrote: bool = False
    overwrite: bool = False
    restarting: bool = False
    log: deque[str] = field(default_factory=lambda: deque(maxlen=LOG_MAX))

    @property
    def requires_overwrite(self) -> bool:
        return self.target is not None and not self.target.empty

    def say(self, line: str) -> None:
        self.log.append(line)
