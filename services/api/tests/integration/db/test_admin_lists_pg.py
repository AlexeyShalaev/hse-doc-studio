"""Серверные списки админки на Postgres с тысячами строк: страницы сходятся с эталоном, счётчики верны,
частые запросы идут по индексам, а не перебором таблицы."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from hse_doc_studio.core.identity.entities import (
    InviteQuery,
    InviteState,
    UserPickQuery,
    UserQuery,
    UserStatus,
)
from hse_doc_studio.core.listing import SortKey, Window
from hse_doc_studio.core.orgs.entities import GroupQuery, MemberQuery, OrgQuery, OrgRole, UserOrgQuery
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.auth import AuditLogRow, RegistrationInviteRow
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.orgs import GroupMemberRow, GroupRow, OrgMemberRow, OrgRow
from hse_doc_studio.infra.db.repositories.auth import SqlRegistrationInviteRepository
from hse_doc_studio.infra.db.repositories.identity import SqlUserDirectory
from hse_doc_studio.infra.db.repositories.orgs import SqlGroupRepository, SqlOrgRepository
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy import insert, text

pytestmark = pytest.mark.pg

T0 = datetime(2026, 1, 1, tzinfo=UTC)
PEOPLE = 3000
ORGS = 400
STATUSES = (UserStatus.active, UserStatus.active, UserStatus.active, UserStatus.disabled, UserStatus.pending_approval)
ROLES = (OrgRole.member, OrgRole.member, OrgRole.admin, OrgRole.owner)


def _person(i: int) -> dict[str, Any]:
    email = f"person{i:05d}@example.test"
    return {
        "id": f"u{i:05d}",
        "email": email,
        "email_normalized": email,
        # Имена повторяются: вторичный ключ id обязан держать порядок страниц.
        "name": f"Person {i % 700:03d}",
        "status": STATUSES[i % len(STATUSES)].value,
        "is_instance_admin": i % 1000 == 0,
        "created_at": T0 + timedelta(minutes=i % 1500),
        "last_login_at": None if i % 3 == 0 else T0 + timedelta(hours=i),
    }


@dataclass
class World:
    sessions: SessionProvider
    users: list[dict[str, Any]]
    directory: SqlUserDirectory
    orgs: SqlOrgRepository
    groups: SqlGroupRepository
    invites: SqlRegistrationInviteRepository

    async def explain(self, sql: str, *, force: bool) -> str:
        """План запроса. `force` запрещает перебор таблицы: для маленьких таблиц теста он дешевле, а проверить
        надо, что индекс подходит к форме запроса."""
        async with self.sessions.begin(), self.sessions.use() as session:
            if force:
                await session.execute(text("SET LOCAL enable_seqscan = off"))
                await session.execute(text("SET LOCAL enable_sort = off"))
            rows = (await session.execute(text(f"EXPLAIN {sql}"))).scalars().all()
        return "\n".join(rows)


@pytest_asyncio.fixture
async def world(pg_migrated_engine: Any) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = [_person(i) for i in range(PEOPLE)]
    orgs = [{"id": f"org{i:04d}", "slug": f"org-{i:04d}", "name": f"Org {i % 150:03d}"} for i in range(ORGS)]
    # Организация i: люди с номерами i, i + ORGS, ... (у ранних организаций участников больше), роль по номеру.
    members = [
        {
            "org_id": f"org{i % ORGS:04d}",
            "user_id": f"u{i:05d}",
            "role": ROLES[(i // ORGS) % len(ROLES)].value,
            "created_at": T0 + timedelta(minutes=i),
        }
        for i in range(PEOPLE)
    ]
    groups = [{"id": f"g{i:03d}", "org_id": "org0000", "name": f"Group {i:03d}"} for i in range(60)]
    group_members = [{"group_id": f"g{(i // ORGS) % 60:03d}", "user_id": f"u{i:05d}"} for i in range(0, PEOPLE, ORGS)]
    invites = [
        {
            "token_hash": f"h{i:05d}",
            "email": f"guest{i:05d}@example.test",
            "created_by": "u00000",
            "expires_at": T0 + timedelta(hours=i),
            "used_at": T0 if i % 7 == 0 else None,
            "id": f"inv{i:05d}",
            "org_id": "org0001" if i % 10 == 0 else None,
        }
        for i in range(2500)
    ]
    async with sessions.begin(), sessions.use() as db:
        await db.execute(insert(UserRow), users)
        await db.execute(insert(OrgRow), orgs)
        await db.execute(insert(OrgMemberRow), members)
        await db.execute(insert(GroupRow), groups)
        await db.execute(insert(GroupMemberRow), group_members)
        await db.execute(insert(RegistrationInviteRow), invites)
        await db.execute(
            insert(AuditLogRow),
            [
                {
                    # Редкая категория (invite.*) проверяет, что префикс действия идёт по индексу.
                    "action": "invite.create"
                    if i % 500 == 0
                    else ("auth.login", "admin.user_disabled", "org.member.add", "project.create")[i % 4],
                    "actor_id": f"u{i % PEOPLE:05d}",
                    "target": f"org{i % ORGS:04d}",
                    "details": {},
                }
                for i in range(30000)
            ],
        )
    async with pg_migrated_engine.connect() as conn:
        await conn.execute(text("ANALYZE"))
        await conn.commit()
    return World(
        sessions,
        users,
        SqlUserDirectory(sessions),
        SqlOrgRepository(sessions),
        SqlGroupRepository(sessions),
        SqlRegistrationInviteRepository(sessions),
    )


def _expected_users(world: World, query: UserQuery, key: str, *, descending: bool) -> list[str]:
    rows = [u for u in world.users if not query.statuses or UserStatus(u["status"]) in query.statuses]
    if query.q:
        rows = [u for u in rows if query.q.lower() in u["name"].lower() or query.q.lower() in u["email"]]
    rows.sort(key=lambda u: u["id"])
    rows.sort(key=lambda u: u[key], reverse=descending)
    return [u["id"] for u in rows]


async def test__users__pages_walk_the_whole_filtered_set_in_a_stable_order(world: World) -> None:
    query = UserQuery(statuses=(UserStatus.active, UserStatus.disabled), sort=SortKey("created_at", descending=True))
    expected = _expected_users(world, query, "created_at", descending=True)

    seen: list[str] = []
    for offset in range(0, len(expected) + 200, 200):
        found = await world.directory.search(UserQuery(**{**query.__dict__, "window": Window(200, offset)}))
        assert found.total == len(expected)
        seen += [x.user.id for x in found.items]

    assert seen == expected


async def test__users__search_sort_by_name_and_nulls_last(world: World) -> None:
    by_name = await world.directory.search(UserQuery(q="PERSON 01", sort=SortKey("name"), window=Window(200)))
    by_login = await world.directory.search(UserQuery(sort=SortKey("last_login_at"), window=Window(1, PEOPLE - 1)))
    admins = await world.directory.search(UserQuery(is_admin=True))
    in_org = await world.directory.search(UserQuery(org_slug="org-0003", sort=SortKey("email")))

    names = [x.user.name for x in by_name.items]
    assert names == sorted(names)
    assert all(n.startswith("Person 01") for n in names)
    assert by_name.total == sum(1 for u in world.users if u["name"].startswith("Person 01"))
    assert by_login.items[0].user.last_login_at is None
    # Новые первыми: u01000 создан на 1000-й минуте, u02000 на 500-й.
    assert [x.user.id for x in admins.items] == ["u01000", "u02000", "u00000"]
    assert [x.user.id for x in in_org.items] == [f"u{i:05d}" for i in range(3, PEOPLE, ORGS)]


async def test__users__facets_and_picker(world: World) -> None:
    facets = await world.directory.facets(None)
    picked = await world.directory.pick(UserPickQuery(q="person 00", limit=5, not_in_org_slug="org-0000"))
    outside_group = await world.directory.pick(UserPickQuery(q="u00000", not_in_group_id="g000"))

    assert facets.status[UserStatus.active] == sum(1 for u in world.users if u["status"] == "active")
    assert facets.status[UserStatus.pending_verification] == 0
    assert facets.admins == 3
    assert len(picked.items) == 5
    assert picked.has_more is True
    assert all(p.id != "u00000" for p in picked.items)
    assert outside_group.items == []


async def test__orgs__counts_only_for_the_page_and_sort_by_count(world: World) -> None:
    first = await world.orgs.page_all("u00000", OrgQuery(window=Window(20)))
    biggest = await world.orgs.page_all("u00000", OrgQuery(sort=SortKey("member_count", descending=True)))
    mine = await world.orgs.page_all("u00000", OrgQuery(mine=True))
    found = await world.orgs.page_all("u00000", OrgQuery(q="ORG-000"))

    assert (len(first.items), first.total) == (20, ORGS)
    names = [x.org.name for x in first.items]
    assert names == sorted(names)
    counts = [x.member_count for x in biggest.items]
    assert counts == sorted(counts, reverse=True)
    assert counts[0] == len(range(0, PEOPLE, ORGS))
    assert [x.org.slug for x in mine.items] == ["org-0000"]
    assert mine.items[0].my_role is OrgRole.member
    assert found.total == 10


async def test__members__role_filter_facets_and_user_orgs(world: World) -> None:
    owners = await world.orgs.page_members("org0000", MemberQuery(roles=(OrgRole.owner,), sort=SortKey("name")))
    by_role = await world.orgs.page_members("org0000", MemberQuery(sort=SortKey("role")))
    counts = await world.orgs.role_counts("org0000", None)
    theirs = await world.orgs.page_for_user("u00001", UserOrgQuery())

    assert {m.member.role for m in owners.items} == {OrgRole.owner}
    assert [m.member.role for m in by_role.items][0] is OrgRole.owner
    assert sum(counts.values()) == by_role.total
    assert counts[OrgRole.owner] == owners.total
    assert [(x.org.slug, x.role) for x in theirs.items] == [("org-0001", OrgRole.member)]
    assert await world.orgs.members_among("org0000", ["u00000", "u00001", "ghost"]) == {"u00000"}


async def test__groups__preview_and_count_without_loading_members(world: World) -> None:
    page = await world.groups.page_for_org("org0000", GroupQuery(sort=SortKey("member_count", descending=True)))

    assert page.total == 60
    top = page.items[0]
    assert top.member_count >= 1
    assert len(top.preview) == min(top.member_count, 5)


async def test__invites__state_in_sql_and_paging_past_two_hundred(world: World) -> None:
    now = T0 + timedelta(hours=1000)
    pending = await world.invites.page(InviteQuery(now=now, states=(InviteState.pending,), window=Window(200, 1000)))
    used = await world.invites.page(InviteQuery(now=now, states=(InviteState.used,)))
    in_org = await world.invites.page(InviteQuery(now=now, org_slug="org-0001", q="GUEST001"))

    assert pending.total == sum(1 for i in range(2500) if i % 7 and i > 1000)
    assert len(pending.items) == 200
    assert used.total == len(range(0, 2500, 7))
    assert [i.id for i in in_org.items] == [f"inv{n:05d}" for n in range(190, 99, -10)]


# Большие таблицы (люди, приглашения, журнал) планировщик сам ведёт по индексу; у маленьких перебор запрещён.
_SMALL = ("org_members", "group_members", "orgs ", "lower(name) LIKE")


@pytest.mark.parametrize(
    ("sql", "index"),
    [
        ("SELECT id FROM users ORDER BY created_at DESC, id LIMIT 50", "ix_users_created_at_id"),
        (
            "SELECT id FROM users WHERE status = 'active' ORDER BY created_at DESC LIMIT 50",
            "ix_users_status_created_at",
        ),
        ("SELECT id FROM users ORDER BY lower(name), id LIMIT 50", "ix_users_name_lower"),
        ("SELECT id FROM orgs ORDER BY lower(name), id LIMIT 50", "ix_orgs_name_lower"),
        (
            "SELECT user_id FROM org_members WHERE org_id = 'org0000' ORDER BY created_at LIMIT 50",
            "ix_org_members_org_created",
        ),
        (
            "SELECT count(*) FROM org_members WHERE org_id = 'org0000' AND role = 'owner'",
            "ix_org_members_org_role",
        ),
        (
            "SELECT user_id FROM group_members WHERE group_id = 'g000' ORDER BY created_at LIMIT 50",
            "ix_group_members_group_created",
        ),
        (
            "SELECT id FROM registration_invites ORDER BY expires_at DESC, id LIMIT 50",
            "ix_registration_invites_expires_id",
        ),
        ("SELECT id FROM audit_log WHERE actor_id = 'u1' ORDER BY id DESC LIMIT 50", "ix_audit_log_actor_id_desc"),
        ("SELECT id FROM audit_log WHERE target = 'org1' ORDER BY id DESC LIMIT 50", "ix_audit_log_target_id_desc"),
        (
            "SELECT id FROM audit_log WHERE action LIKE 'invite.%' ORDER BY id DESC LIMIT 50",
            "ix_audit_log_action_id_desc",
        ),
        ("SELECT id FROM users WHERE lower(name) LIKE '%person 01%'", "ix_trgm_users_name"),
    ],
)
async def test__explain__list_queries_use_their_index(world: World, sql: str, index: str) -> None:
    assert index in await world.explain(sql, force=any(table in sql for table in _SMALL))
