"""Осознанное принятие предупреждений: какие проверки можно принять, запись о принятии и когда она действует.

Принять можно только предупреждение (`warn`) с причиной из `ACCEPTABLE`: это то, что владелец установки вправе решить
сам («бэкапов не делаю», «публичных раннеров нет»). Сбои и всё, что касается целостности данных и работы сервера
(база, миграции, диск, очередь, срок сертификата, лидер фоновых задач), принять нельзя: их можно только исправить.
Записи лежат в `instance_settings` одним ключом и переживают исправление причины: пока предупреждения нет, молчат.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from hse_doc_studio.core.diagnostics.entities import CheckResult, DiagStatus
from hse_doc_studio.core.diagnostics.thresholds import KEY_PREFIX

KEY_ACCEPTED = KEY_PREFIX + "accepted"
REASON_MAX = 200
# Проверка бэкапов: к ней привязано подтверждение риска при ручном обновлении.
BACKUPS_CHECK = "backups"

# Проверка -> причины её предупреждения, которые можно принять.
ACCEPTABLE: dict[str, frozenset[str]] = {
    "runners": frozenset({"no_runners", "no_online_runner"}),
    "object_storage": frozenset({"object_not_public"}),
    "backups": frozenset({"backups_disabled", "backups_no_destination"}),
    "smtp": frozenset({"smtp_unreachable"}),
    "tls_public": frozenset({"tls_unreachable"}),
    "tls_s3": frozenset({"tls_unreachable"}),
}


@dataclass(frozen=True)
class Acceptance:
    check_id: str
    reason: str
    by_id: str
    by_name: str
    at: datetime
    until: datetime | None = None

    def live(self, now: datetime) -> bool:
        return self.until is None or now < self.until


def is_acceptable(check_id: str, status: DiagStatus, reason: str) -> bool:
    """Предупреждение можно принять: статус `warn` и причина из разрешённых для этой проверки."""
    return status is DiagStatus.warn and reason in ACCEPTABLE.get(check_id, frozenset())


def applies(acc: Acceptance, result: CheckResult, now: datetime) -> bool:
    """Принятие сейчас гасит предупреждение: срок не вышел, а проверка в принимаемом состоянии."""
    return acc.live(now) and is_acceptable(result.check_id, result.status, result.reason)


def _time(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def acceptances_from(values: Mapping[str, object]) -> dict[str, Acceptance]:
    """Записи из настроек; испорченная запись пропускается, чтобы не ронять страницу."""
    raw = values.get(KEY_ACCEPTED)
    found: dict[str, Acceptance] = {}
    if not isinstance(raw, dict):
        return found
    for check_id, item in raw.items():
        if not isinstance(check_id, str) or check_id not in ACCEPTABLE or not isinstance(item, dict):
            continue
        at = _time(item.get("at"))
        reason, by_id = item.get("reason"), item.get("by")
        if at is None or not isinstance(reason, str) or not isinstance(by_id, str):
            continue
        name = item.get("by_name")
        found[check_id] = Acceptance(
            check_id, reason, by_id, name if isinstance(name, str) else by_id, at, _time(item.get("until"))
        )
    return found


def acceptances_to(items: Mapping[str, Acceptance]) -> dict[str, dict[str, str | None]]:
    return {
        cid: {
            "reason": a.reason,
            "by": a.by_id,
            "by_name": a.by_name,
            "at": a.at.isoformat(),
            "until": a.until.isoformat() if a.until else None,
        }
        for cid, a in sorted(items.items())
    }


def live_acceptance(values: Mapping[str, object], check_id: str, now: datetime) -> Acceptance | None:
    """Запись, у которой не вышел срок, независимо от текущего состояния проверки (для связки с обновлениями)."""
    acc = acceptances_from(values).get(check_id)
    return acc if acc is not None and acc.live(now) else None
