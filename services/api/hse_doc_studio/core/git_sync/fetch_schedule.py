"""Расписание фоновой выборки: когда проект пора опросить снова и что делать после отказа.

Чистая арифметика без ввода-вывода. Период берётся из настроек, к нему добавляется разброс на каждый проект
(чтобы десятки проектов на одном сервере не приходили в один момент), а после сбоя связи задержка
удваивается до часа. Неверный доступ повторами не лечится, поэтому после него опрос останавливается до
действия человека или смены доступа.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, SyncHealth, SyncState
from hse_doc_studio.core.git_sync.errors import GitErrorCode

# Разброс периода: +-10% от него, постоянный для проекта.
JITTER_SHARE = 0.1
MAX_BACKOFF_S = 3600
_MAX_BACKOFF_STEPS = 16

# Коды, после которых опрос по расписанию не повторяется: сервер отвечает, но человека не пускает.
_HALTING_CODES = frozenset(
    {
        GitErrorCode.auth_failed,
        GitErrorCode.sso_required,
        GitErrorCode.credentials_missing,
        GitErrorCode.host_key_unknown,
        GitErrorCode.host_key_changed,
    }
)
# Из них те, что проходят после замены токена или ключа.
_CREDENTIAL_CODES = frozenset({GitErrorCode.auth_failed, GitErrorCode.sso_required})

_HEALTH_BY_CODE: dict[GitErrorCode, SyncHealth] = {
    GitErrorCode.auth_failed: SyncHealth.unauthenticated,
    GitErrorCode.sso_required: SyncHealth.unauthenticated,
    GitErrorCode.credentials_missing: SyncHealth.unauthenticated,
    GitErrorCode.forbidden_write: SyncHealth.unauthenticated,
    GitErrorCode.host_key_changed: SyncHealth.host_key_changed,
    GitErrorCode.offline: SyncHealth.offline,
    GitErrorCode.timeout: SyncHealth.offline,
    GitErrorCode.not_found_or_no_access: SyncHealth.remote_missing,
    GitErrorCode.branch_missing: SyncHealth.branch_missing,
}


def health_for(code: GitErrorCode) -> SyncHealth:
    """Как отказ выборки отражается в здоровье подключения; всё незнакомое это просто `error`."""
    return _HEALTH_BY_CODE.get(code, SyncHealth.error)


def fetch_jitter(key: str) -> float:
    """Множитель периода в пределах 0.9..1.1, одинаковый при каждом вызове для одного ключа."""
    unit = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:4], "big") / 0xFFFFFFFF
    return 1 - JITTER_SHARE + 2 * JITTER_SHARE * unit


def retry_delay_s(interval_s: int, failures: int, key: str) -> float:
    """Через сколько секунд после последней попытки пробовать снова: период, удвоенный за каждый подряд сбой.

    Потолок час, но не меньше самого периода: пользователь, выбравший сутки, получает сутки.
    """
    steps = min(max(failures, 0), _MAX_BACKOFF_STEPS)
    delay = min(interval_s * 2**steps, max(interval_s, MAX_BACKOFF_S))
    return delay * fetch_jitter(key)


def next_attempt_at(last_attempt_at: datetime | None, interval_s: int, failures: int, key: str) -> datetime | None:
    """Момент следующей попытки; None, если проект ещё ни разу не опрашивали и пора сразу."""
    if last_attempt_at is None:
        return None
    return last_attempt_at + timedelta(seconds=retry_delay_s(interval_s, failures, key))


def halts_auto_fetch(state: SyncState) -> bool:
    """Последняя попытка закончилась отказом, который повторы не лечат."""
    if state.health in (SyncHealth.unauthenticated, SyncHealth.host_key_changed):
        return True
    return state.last_error is not None and state.last_error.code in _HALTING_CODES


def credential_replaced(state: SyncState, credential: GitCredential | None) -> bool:
    """Отказ был из-за доступа, а он с тех пор заменён (его статус снова не `auth_failed`): можно пробовать опять."""
    if state.last_error is None or state.last_error.code not in _CREDENTIAL_CODES or credential is None:
        return False
    return credential.status not in (CredentialStatus.auth_failed, CredentialStatus.unreadable)


class FetchBook:
    """Что помнит процесс о выборках: число сбоев подряд и замок на каждую папку.

    Один на процесс. Замок не даёт двум выборкам одного проекта идти разом (кнопка и расписание),
    сбои живут до перезапуска: после него проект просто опрашивается по обычному периоду.
    """

    def __init__(self) -> None:
        self._failures: dict[Path, int] = {}
        self._locks: dict[Path, asyncio.Lock] = {}

    def failures(self, folder: Path) -> int:
        return self._failures.get(_key(folder), 0)

    def succeeded(self, folder: Path) -> None:
        self._failures.pop(_key(folder), None)

    def failed(self, folder: Path) -> None:
        key = _key(folder)
        self._failures[key] = self._failures.get(key, 0) + 1

    def lock(self, folder: Path) -> asyncio.Lock:
        return self._locks.setdefault(_key(folder), asyncio.Lock())

    def forget(self, folder: Path) -> None:
        key = _key(folder)
        self._failures.pop(key, None)
        self._locks.pop(key, None)


def _key(folder: Path) -> Path:
    return folder.resolve()
