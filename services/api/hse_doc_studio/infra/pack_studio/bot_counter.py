"""Срез T22: лимит предложений через доступ бота считается по журналу аудита (`pack_studio.proposed`, `bot: true`).

Журнал только дописывается, поэтому счёт не обходится удалением пространства или ветки; отдельной таблицы не нужно.
"""

from __future__ import annotations

from datetime import datetime

from hse_doc_studio.core.identity.entities import AuditQuery
from hse_doc_studio.core.identity.protocols import IAuditReader
from hse_doc_studio.core.pack_studio.official import DAILY_LIMIT_MAX, PROPOSED_ACTION

_PAGE = 200


class AuditBotProposalCounter:
    def __init__(self, reader: IAuditReader) -> None:
        self._reader = reader

    async def count_since(self, user_id: str, since: datetime) -> int:
        count = 0
        before: int | None = None
        # Предел выше любого допустимого лимита: дальше считать незачем.
        while count <= DAILY_LIMIT_MAX:
            page = await self._reader.query(
                AuditQuery(actor_id=user_id, actions=(PROPOSED_ACTION,), since=since, before_id=before, limit=_PAGE)
            )
            count += sum(1 for view in page if view.entry.details.get("bot") is True)
            if len(page) < _PAGE:
                break
            before = page[-1].entry.id
        return count
