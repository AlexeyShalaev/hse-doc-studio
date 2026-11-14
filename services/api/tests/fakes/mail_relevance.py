"""Актуальность письма для повтора в памяти (docs/design/mail-log.md, 14.2): причина по id строки журнала."""

from __future__ import annotations

from hse_doc_studio.core.mail.journal import MailLogEntry, ResendBlock


class InMemoryMailRelevance:
    def __init__(self) -> None:
        # id строки журнала -> почему письмо уже неактуально; остальные актуальны.
        self.blocks: dict[int, ResendBlock] = {}
        self.checked: list[int] = []

    async def check(self, entry: MailLogEntry) -> ResendBlock | None:
        self.checked.append(entry.id or 0)
        return self.blocks.get(entry.id or 0)
