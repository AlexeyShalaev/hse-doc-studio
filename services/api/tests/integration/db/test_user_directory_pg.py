"""Список пользователей админки на Postgres: поиск без подстановок LIKE, фильтр по статусу, число проектов."""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from hse_doc_studio.core.identity.entities import UserQuery, UserStatus
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

    found = await directory.search(UserQuery(q="ANNA.DIR"))
    pending = await directory.search(UserQuery(q="dir-", statuses=(UserStatus.pending_approval,)))
    wildcard = await directory.search(UserQuery(q="%"))
    one = await directory.get(anna.id)

    assert [(x.user.id, x.project_count) for x in found.items] == [(anna.id, 1)]
    assert found.total == 1
    assert [x.user.id for x in pending.items] == [waiting.id]
    assert (wildcard.items, wildcard.total) == ([], 0)
    assert one is not None
    assert one.project_count == 1
    assert await directory.get("ghost") is None
