"""Чаты проекта, приехавшие в архиве: читаются форматом локальной Студии и пишутся в репозиторий сервера."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

from hse_doc_studio.core.repositories import IChatRepository
from hse_doc_studio.infra.persistence.chat import JsonChatRepository

_CHATS = Path(".hse-studio") / "chats"


class LocalChatHistory:
    """Все идентификаторы чатов выдаются заново: повторный импорт того же архива не должен упереться в занятые id."""

    def __init__(self) -> None:
        self._source = JsonChatRepository()

    def has_chats(self, folder: Path) -> bool:
        return (folder / _CHATS).is_dir()

    def discard_chats(self, folder: Path) -> None:
        shutil.rmtree(folder / _CHATS, ignore_errors=True)

    async def transfer_chats(self, folder: Path, project_id: UUID, target: IChatRepository) -> int:
        sessions = await self._source.list_sessions(folder)
        for session in sessions:
            run_ids: dict[UUID, UUID] = {}
            new_id = uuid4()
            await target.save_session(
                replace(
                    session,
                    id=new_id,
                    project_id=project_id,
                    message_count=0,
                    last_run_id=None,
                )
            )
            for message in await self._source.list_messages(folder, session.id):
                run_id = None if message.run_id is None else run_ids.setdefault(message.run_id, uuid4())
                await target.append_message(folder, replace(message, id=uuid4(), session_id=new_id, run_id=run_id))
            for summary in await self._source.list_summaries(folder, session.id):
                await target.append_summary(folder, replace(summary, id=uuid4(), session_id=new_id))
            for run in await self._source.list_runs(folder, session.id):
                await target.save_run(replace(run, id=run_ids.setdefault(run.id, uuid4()), session_id=new_id))
            # Счётчик реплик ведёт append_message, остальные поля (в том числе время правки) возвращаем как были.
            last_run = None if session.last_run_id is None else run_ids.get(session.last_run_id)
            await target.save_session(replace(session, id=new_id, project_id=project_id, last_run_id=last_run))
        return len(sessions)
