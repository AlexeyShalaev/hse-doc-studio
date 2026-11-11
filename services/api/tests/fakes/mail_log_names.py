"""Имена для строк журнала писем в памяти: те же правила, что у `SqlMailLogNames`."""

from __future__ import annotations

from collections.abc import Collection

from hse_doc_studio.core.mail.ports import MailPerson


class InMemoryMailLogNames:
    def __init__(self) -> None:
        self.people_by_id: dict[str, MailPerson] = {}
        self.project_names: dict[str, str] = {}
        self.calls = 0

    def add_person(self, user_id: str, name: str, email: str | None) -> None:
        self.people_by_id[user_id] = MailPerson(id=user_id, name=name, email=email)

    async def people(self, user_ids: Collection[str]) -> dict[str, MailPerson]:
        self.calls += 1
        return {uid: self.people_by_id[uid] for uid in user_ids if uid in self.people_by_id}

    async def projects(self, project_ids: Collection[str]) -> dict[str, str]:
        self.calls += 1
        return {pid: self.project_names[pid] for pid in project_ids if pid in self.project_names}
