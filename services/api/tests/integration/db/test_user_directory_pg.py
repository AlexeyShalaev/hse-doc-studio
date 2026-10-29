"""Список пользователей админки на Postgres: поиск без подстановок LIKE, фильтр по статусу, число проектов."""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from hse_doc_studio.core.identity.entities import UserStatus
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.identity import SqlUserDirectory, SqlUserRepository
from hse_doc_studio.infra.db.session import SessionProvider

from tests.contract.test_identity_contract import make_user

pytestmark = pytest.mark.pg


async def test__search__filters_pages_and_counts_live_projects(pg_migrated_engine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    directory = SqlUserDirectory(sessions)
    anna = make_user("dir-anna", "anna.dir@example.org")
    waiting = replace(make_user("dir-wait", "wait.dir@example.org"), status=UserStatus.pending_approval)
    await users.add(anna)
    await users.add(waiting)
    async with sessions.begin(), sessions.use() as db:
        for deleted in (False, True):
            db.add(
                ProjectRow(
                    id=uuid.uuid4(),
                    name="P",
                    owner_user_id=anna.id,
                    workspace_path="/p",
                    kind="research",
                    lang="ru",
                    deleted_at=None if not deleted else anna.created_at,
                )
            )

    found, total = await directory.search(q="ANNA.DIR", status=None, limit=10, offset=0)
    pending, _ = await directory.search(q="dir-", status=UserStatus.pending_approval, limit=10, offset=0)
    wildcard, wildcard_total = await directory.search(q="%", status=None, limit=10, offset=0)
    one = await directory.get(anna.id)

    assert [(x.user.id, x.project_count) for x in found] == [(anna.id, 1)]
    assert total == 1
    assert [x.user.id for x in pending] == [waiting.id]
    assert (wildcard, wildcard_total) == ([], 0)
    assert one is not None
    assert one.project_count == 1
    assert await directory.get("ghost") is None
