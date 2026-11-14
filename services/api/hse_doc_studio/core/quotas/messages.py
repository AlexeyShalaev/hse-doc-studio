"""Текст отказа по квоте на языке интерфейса: что исчерпано, сколько, до какого предела и когда сбросится.

Момент сброса по Москве тем же правилом, что в письмах (`format_moment`, пояс `DISPLAY_ZONE`).
"""

from __future__ import annotations

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.mail.compose import format_moment
from hse_doc_studio.core.quotas.errors import QuotaExceededError
from hse_doc_studio.core.quotas.kinds import QuotaKind, QuotaScope

_WHAT: dict[QuotaKind, tuple[str, str]] = {
    QuotaKind.storage: ("место на сервере", "storage on the server"),
    QuotaKind.builds: ("число сборок за месяц", "builds this month"),
    QuotaKind.ai_tokens_day: ("токены ИИ за сутки", "AI tokens for the day"),
    QuotaKind.ai_tokens_month: ("токены ИИ за месяц", "AI tokens for the month"),
    QuotaKind.members: ("число участников проекта", "project members"),
}
_WHO: dict[QuotaScope, tuple[str, str]] = {
    QuotaScope.user: ("Ваш лимит", "Your limit"),
    QuotaScope.org: ("Лимит организации", "Organization limit"),
}


def _number(kind: QuotaKind, value: int, *, en: bool) -> str:
    if kind is not QuotaKind.storage:
        return f"{value:,}".replace(",", " " if not en else ",")
    units = ("B", "KB", "MB", "GB", "TB") if en else ("Б", "КБ", "МБ", "ГБ", "ТБ")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:  # noqa: PLR2004
            text = f"{size:.0f}" if size >= 10 or size == int(size) else f"{size:.1f}"  # noqa: PLR2004
            return f"{text} {unit}"
        size /= 1024
    return str(value)


def describe_quota_exceeded(exc: QuotaExceededError) -> str:
    what_ru, what_en = _WHAT[exc.kind]
    who_ru, who_en = _WHO[exc.scope]
    used_ru, limit_ru = _number(exc.kind, exc.used, en=False), _number(exc.kind, exc.limit, en=False)
    used_en, limit_en = _number(exc.kind, exc.used, en=True), _number(exc.kind, exc.limit, en=True)
    resets = exc.resets_at
    until_ru = f" Сбросится {format_moment(Lang.ru, resets)}." if resets is not None else ""
    until_en = f" Resets {format_moment(Lang.en, resets)}." if resets is not None else ""
    return localized_error(
        f"{who_ru} исчерпан: {what_ru}, {used_ru} из {limit_ru}.{until_ru}",
        f"{who_en} is used up: {what_en}, {used_en} of {limit_en}.{until_en}",
    )
