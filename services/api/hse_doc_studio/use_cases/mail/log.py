"""Журнал писем в админке (docs/design/mail-log.md, 6): страница, карточка с перерисованным письмом, сводка за сутки.

Читает только админ установки (L10); чтение в аудит не пишется. Имена людей и проектов строк журнал не хранит:
они подтягиваются одной выборкой на страницу (`IMailLogNames`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository, IMailLogRepository, IMailSender
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.lifecycle.policies import POLICY_BY_KEY, effective_days
from hse_doc_studio.core.listing import MAX_LIMIT, clamp_limit
from hse_doc_studio.core.mail.compose import RenderedMail
from hse_doc_studio.core.mail.journal import (
    MailLinkKind,
    MailLogCounts,
    MailLogEntry,
    MailLogQuery,
    rerender,
    rerendered,
)
from hse_doc_studio.core.mail.ports import IMailLogNames, MailPerson
from hse_doc_studio.use_cases.admin.users import require_admin

# Окно сводки (L14): полоса «за сутки» и счётчик меню.
SUMMARY_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class MailLogView:
    """Строка журнала с подписями: получатель и вызвавший как люди установки, название проекта.

    `project_name` None, если проекта уже нет; `to_user` и `actor` None, если человека нет или он удалён.
    """

    entry: MailLogEntry
    to_user: MailPerson | None
    actor: MailPerson | None
    project_name: str | None


@dataclass(frozen=True)
class MailLogViewPage:
    items: list[MailLogView]
    next_before_id: int | None
    total_estimate: int | None


@dataclass(frozen=True)
class MailLogDetail:
    view: MailLogView
    # None, если вида письма в этой версии больше нет.
    preview: RenderedMail | None
    link_hidden: bool
    note_hidden: bool
    rerendered: bool


@dataclass(frozen=True)
class MailLogSummary:
    smtp_configured: bool
    window: timedelta
    counts: MailLogCounts
    retention_days: int


async def _views(names: IMailLogNames, entries: Iterable[MailLogEntry]) -> list[MailLogView]:
    rows = list(entries)
    user_ids = {uid for e in rows for uid in (e.to_user_id, e.actor_user_id) if uid}
    project_ids = {e.project_id for e in rows if e.project_id}
    people = await names.people(user_ids) if user_ids else {}
    projects = await names.projects(project_ids) if project_ids else {}
    return [
        MailLogView(
            entry=e,
            to_user=people.get(e.to_user_id) if e.to_user_id else None,
            actor=people.get(e.actor_user_id) if e.actor_user_id else None,
            project_name=projects.get(e.project_id) if e.project_id else None,
        )
        for e in rows
    ]


class ListMailLogUC:
    def __init__(self, log: IMailLogRepository, names: IMailLogNames) -> None:
        self._log = log
        self._names = names

    async def execute(self, actor: Actor, query: MailLogQuery) -> MailLogViewPage:
        """Страница по ключу, новые сверху; размер в пределах 1..`MAX_LIMIT` и в обход HTTP."""
        require_admin(actor)
        page = await self._log.page(replace(query, limit=clamp_limit(query.limit, MAX_LIMIT)))
        return MailLogViewPage(
            items=await _views(self._names, page.items),
            next_before_id=page.next_before_id,
            total_estimate=page.total_estimate,
        )


class GetMailLogEntryUC:
    def __init__(self, log: IMailLogRepository, names: IMailLogNames) -> None:
        self._log = log
        self._names = names

    async def execute(self, actor: Actor, entry_id: int) -> MailLogDetail | None:
        """Карточка письма; None, если строки нет (удалена по сроку или не было). Просмотр не аудируется (L10)."""
        require_admin(actor)
        entry = await self._log.get(entry_id)
        if entry is None:
            return None
        (view,) = await _views(self._names, (entry,))
        return MailLogDetail(
            view=view,
            preview=rerender(entry),
            link_hidden=entry.params.link is MailLinkKind.token,
            note_hidden=entry.params.note_len > 0,
            rerendered=rerendered(entry),
        )


class MailLogSummaryUC:
    def __init__(
        self,
        log: IMailLogRepository,
        sender: IMailSender,
        settings: IInstanceSettingsRepository,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._log = log
        self._sender = sender
        self._settings = settings
        self._clock = clock

    async def execute(self, actor: Actor) -> MailLogSummary:
        """Итоги за последние сутки, последний сбой в них, настроена ли почта и срок хранения журнала."""
        require_admin(actor)
        policy = POLICY_BY_KEY["mail_log"]
        days = effective_days(policy, await self._settings.get_all())
        default_days = policy.bounds.default_days if policy.bounds is not None else 0
        since: datetime = self._clock() - SUMMARY_WINDOW
        return MailLogSummary(
            smtp_configured=self._sender.enabled,
            window=SUMMARY_WINDOW,
            counts=await self._log.summary(since),
            retention_days=days if days is not None else default_days,
        )
