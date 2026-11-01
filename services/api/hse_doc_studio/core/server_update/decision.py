"""Решение планировщика: молчать, сообщить админам или ставить обновление. Чистая функция без часов и сети."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.server_update.entities import ReleaseInfo, UpdatePolicy, UpdateSettings
from hse_doc_studio.core.server_update.versions import newest_release, pick_target
from hse_doc_studio.core.server_update.window import in_window


class Action(StrEnum):
    none = "none"
    notify = "notify"
    start = "start"


class Reason(StrEnum):
    policy_off = "policy_off"
    up_to_date = "up_to_date"
    already_notified = "already_notified"
    notify_only = "notify_only"
    bump_too_large = "bump_too_large"
    no_executor = "no_executor"
    run_active = "run_active"
    previously_failed = "previously_failed"
    updater_offline = "updater_offline"
    outside_window = "outside_window"
    in_window = "in_window"


@dataclass(frozen=True)
class DecisionInput:
    settings: UpdateSettings
    current: str
    releases: tuple[ReleaseInfo, ...]
    now: datetime
    executor_ready: bool  # исполнитель включён настройкой (compose), не helm
    updater_online: bool
    run_active: bool
    failed_versions: frozenset[str] = frozenset()  # версии, на которых обновление уже откатывалось или падало
    notified_version: str | None = None


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: Reason
    target: ReleaseInfo | None = None


def decide(data: DecisionInput) -> Decision:  # noqa: C901, PLR0911 — каждая причина молчания возвращается отдельно
    """Порядок проверок от дешёвых к зависящим от окружения. Уведомление об одной версии уходит один раз."""
    s = data.settings
    if s.policy is UpdatePolicy.off:
        return Decision(Action.none, Reason.policy_off)
    newest = newest_release(data.current, data.releases)
    if newest is None:
        return Decision(Action.none, Reason.up_to_date)

    def tell(reason: Reason) -> Decision:
        if data.notified_version == newest.version:
            return Decision(Action.none, Reason.already_notified, newest)
        return Decision(Action.notify, reason, newest)

    if s.policy is UpdatePolicy.notify:
        return tell(Reason.notify_only)
    target = pick_target(data.current, data.releases, s.max_bump)
    if target is None:
        return tell(Reason.bump_too_large)
    if not data.executor_ready:
        return tell(Reason.no_executor)
    if data.run_active:
        return Decision(Action.none, Reason.run_active, target)
    if target.version in data.failed_versions:
        # Версия уже откатывалась: повторять то же самое каждый тик бессмысленно, ждём следующий релиз.
        return Decision(Action.none, Reason.previously_failed, target)
    if not data.updater_online:
        return Decision(Action.none, Reason.updater_offline, target)
    if not in_window(data.now, s.window_days, s.window_start_min, s.window_minutes):
        return Decision(Action.none, Reason.outside_window, target)
    return Decision(Action.start, Reason.in_window, target)
