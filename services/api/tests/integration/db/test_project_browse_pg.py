"""Список проектов серверного режима на Postgres: тысячи проектов, видимость как у загрузчика прав,
фильтры, поиск и порядок в SQL, без чтения project.json."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.listing import SortKey, Window
from hse_doc_studio.core.projects.browse import ProjectBrowseQuery
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import OrgMemberRow, OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository
from hse_doc_studio.infra.db.repositories.project_browse import PostgresProjectBrowser
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.projects.acl_flags import AclFlagsCache
from sqlalchemy import insert, text

pytestmark = pytest.mark.pg

T0 = datetime(2026, 1, 1, tzinfo=UTC)
PROJECTS = 2400
ANNA = Actor.user("anna")


def _user(uid: str, name: str) -> dict[str, Any]:
    email = f"{uid}@example.test"
    return {"id": uid, "email": email, "email_normalized": email, "name": name, "status": "active", "created_at": T0}


@pytest.fixture
async def browser(pg_migrated_engine: Any) -> tuple[PostgresProjectBrowser, dict[str, list[UUID]], SessionProvider]:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = [_user("anna", "Анна"), _user("boris", "Борис Петров"), _user("carol", "Carol")]
    orgs = [{"id": "org_lab", "slug": "lab", "name": "Лаборатория"}, {"id": "org_x", "slug": "x", "name": "Чужая"}]
    rows: list[dict[str, Any]] = []
    grants: list[dict[str, Any]] = []
    kinds: dict[str, list[UUID]] = {"mine": [], "org": [], "shared": [], "hidden": []}
    for i in range(PROJECTS):
        pid = uuid4()
        bucket = ("mine", "org", "shared", "hidden")[i % 4]
        kinds[bucket].append(pid)
        rows.append(
            {
                "id": pid,
                "name": f"Проект {i:04d}",
                "owner_user_id": {"mine": "anna", "shared": "boris", "hidden": "carol"}.get(bucket),
                "owner_org_id": "org_lab" if bucket == "org" else None,
                "workspace_path": str(pid),
                "kind": "research",
                "lang": "ru",
                "team": i % 5 == 0,
                "org_visible": True,
                "updated_at": T0 + timedelta(minutes=i),
                "created_at": T0 + timedelta(minutes=PROJECTS - i),
                "archived_at": T0 if i % 10 == 0 else None,
                "pinned": i % 7 == 0,
                "supervisor_name": "Сидоров И. И." if i % 9 == 0 else None,
            }
        )
        if bucket == "shared":
            grants.append(
                {"project_id": pid, "principal_kind": "user", "principal_id": "anna", "role": Role.reader.value}
            )
    async with sessions.begin(), sessions.use() as db:
        await db.execute(insert(UserRow), users)
        await db.execute(insert(OrgRow), orgs)
        await db.execute(
            insert(OrgMemberRow),
            [
                {"org_id": "org_lab", "user_id": "anna", "role": "member"},
                {"org_id": "org_x", "user_id": "carol", "role": "owner"},
            ],
        )
        await db.execute(insert(ProjectRow), rows)
        await db.execute(insert(ProjectMemberRow), grants)
    async with pg_migrated_engine.connect() as conn:
        await conn.execute(text("ANALYZE"))
        await conn.commit()
    acl = PostgresProjectAclRepository(sessions, AclFlagsCache())
    return PostgresProjectBrowser(sessions, acl), kinds, sessions


async def test__browse__only_visible_projects_and_pages_cover_them_once(browser: Any) -> None:
    repo, kinds, _ = browser
    visible = set(kinds["mine"] + kinds["org"] + kinds["shared"])

    seen: list[UUID] = []
    for offset in range(0, PROJECTS, 200):
        page = await repo.page(ANNA, ProjectBrowseQuery(window=Window(200, offset)))
        assert page.total == len(visible)
        seen += [c.id for c in page.items]

    assert len(seen) == len(set(seen)) == len(visible)
    assert set(seen) == visible
    first = await repo.page(ANNA, ProjectBrowseQuery(window=Window(3)))
    stamps = [c.updated_at for c in first.items]
    assert stamps == sorted(stamps, reverse=True)


async def test__browse__owner_archived_pinned_and_org_filters(browser: Any) -> None:
    repo, kinds, _ = browser

    async def ids(**filters: Any) -> set[UUID]:
        page = await repo.page(ANNA, ProjectBrowseQuery(window=Window(200), **filters))
        assert page.total <= 200
        return {c.id for c in page.items}

    mine = await repo.page(ANNA, ProjectBrowseQuery(owner="me", window=Window(1)))
    org = await repo.page(ANNA, ProjectBrowseQuery(owner="org", window=Window(1)))
    shared = await repo.page(ANNA, ProjectBrowseQuery(owner="shared", window=Window(1)))
    assert (mine.total, org.total, shared.total) == (len(kinds["mine"]),) * 3
    assert shared.items[0].my_role is Role.reader
    assert (shared.items[0].owner.kind, shared.items[0].owner.name) == ("user", "Борис Петров")
    assert (org.items[0].owner.kind, org.items[0].owner.slug) == ("org", "lab")
    assert await ids(owner="me", archived=True, pinned=True) <= set(kinds["mine"])
    archived = await repo.page(ANNA, ProjectBrowseQuery(archived=True, window=Window(200)))
    assert all(c.archived for c in archived.items)
    pinned = await repo.page(ANNA, ProjectBrowseQuery(pinned=True, window=Window(200)))
    assert pinned.items
    assert all(c.pinned for c in pinned.items)
    in_org = await repo.page(ANNA, ProjectBrowseQuery(org_slug="lab", window=Window(1)))
    assert in_org.total == len(kinds["org"])
    assert (await repo.page(ANNA, ProjectBrowseQuery(org_slug="x"))).total == 0


async def test__browse__search_by_name_owner_and_supervisor_and_sort(browser: Any) -> None:
    repo, kinds, _ = browser

    by_name = await repo.page(ANNA, ProjectBrowseQuery(q="ПРОЕКТ 000", sort=SortKey("name")))
    by_owner = await repo.page(ANNA, ProjectBrowseQuery(q="петров", window=Window(1)))
    by_org = await repo.page(ANNA, ProjectBrowseQuery(q="лаборат", window=Window(1)))
    by_supervisor = await repo.page(ANNA, ProjectBrowseQuery(q="сидоров", window=Window(200)))
    literal = await repo.page(ANNA, ProjectBrowseQuery(q="%"))
    oldest_created = await repo.page(ANNA, ProjectBrowseQuery(sort=SortKey("created_at"), window=Window(1)))

    # Каждый четвёртый проект чужой и не виден.
    assert [c.name for c in by_name.items] == [f"Проект 000{i}" for i in range(10) if i % 4 != 3]
    assert by_owner.total == len(kinds["shared"])
    assert by_org.total == len(kinds["org"])
    assert by_supervisor.total > 0
    assert literal.total == 0
    assert oldest_created.items[0].name == "Проект 2398"


async def test__browse__stranger_sees_nothing(browser: Any) -> None:
    repo, _, _ = browser

    page = await repo.page(Actor.user("ghost"), ProjectBrowseQuery())

    assert (page.items, page.total) == ([], 0)


@pytest.mark.parametrize(
    ("sql", "index"),
    [
        (
            "SELECT id FROM projects WHERE owner_org_id = 'org_lab' ORDER BY updated_at DESC LIMIT 50",
            "ix_projects_owner_org_updated",
        ),
        ("SELECT id FROM projects ORDER BY lower(name), id LIMIT 50", "ix_projects_name_lower"),
    ],
)
async def test__explain__project_list_queries_use_their_index(browser: Any, sql: str, index: str) -> None:
    _, _, sessions = browser
    async with sessions.use() as session:
        plan = "\n".join((await session.execute(text(f"EXPLAIN {sql}"))).scalars().all())

    assert index in plan
