"""Списки админки эксплуатации на Postgres через настоящие маршруты: окно, поиск, фильтры, порядок и права.

Данных несколько тысяч строк: так видно, что страница, `total` и курсор считаются в базе, а не на клиенте.
Планы запросов проверяются в test_admin_ops_lists_plan_pg.py.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.api.schemas.admin import decode_cursor
from hse_doc_studio.core.access.entities import Actor, ActorKind, ActorSource
from hse_doc_studio.core.identity.entities import ActorCredentials
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.jobs.quotas import org_key
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.ai_providers import AIProviderRow
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.jobs import JobRow, RunnerRegistrationTokenRow, RunnerRow
from hse_doc_studio.infra.db.orm.orgs import OrgRow
from hse_doc_studio.infra.db.orm.project_usage import ProjectUsageRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.ai_providers import PostgresAIProviderRepository
from hse_doc_studio.infra.db.repositories.jobs_admin import SqlAdminProjectPicker, SqlJobAdminReader
from hse_doc_studio.infra.db.repositories.runners import (
    SqlRegistrationTokenRepository,
    SqlRunnerAdminReader,
    SqlRunnerRepository,
)
from hse_doc_studio.infra.db.repositories.storage_usage import SqlStorageUsageReader
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.use_cases.admin.ops_ai_providers import ListInstanceAiProvidersUC
from hse_doc_studio.use_cases.admin.ops_queue import ListQueueUC, PickProjectsUC
from hse_doc_studio.use_cases.admin.ops_runners import (
    ListRegistrationTokensUC,
    ListRunnersUC,
    PickRunnersUC,
    RunnerSummaryUC,
)
from hse_doc_studio.use_cases.admin.ops_storage import ListStorageOwnersUC
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.ops import NoopUow, ReversingCipher

pytestmark = pytest.mark.pg

NOW = datetime.now(UTC)
ADMIN = Actor(kind=ActorKind.user, id="f" * 32, is_instance_admin=True, source=ActorSource.session)
STUDENT = Actor(kind=ActorKind.user, id="e" * 32, source=ActorSource.session)

USERS = 300
ORGS = 12
PROJECTS = 1500
RUNNERS = 400
TOKENS = 1500
JOBS = 5000
STATES = ("queued", "running", "succeeded", "failed", "cancelled", "timed_out")
KINDS = ("compile", "office.convert", "signature.verify_detached", "pack.submission")
VERSIONS = ("0.2.0", "0.10.1", "0.9.9", "0.10.0")


class _Resolver:
    def __init__(self) -> None:
        self.actor: Actor | None = ADMIN

    async def resolve(self, _credentials: ActorCredentials) -> Actor | None:
        return self.actor


@dataclass
class World:
    client: AsyncClient
    resolver: _Resolver
    users: list[str]
    orgs: list[str]
    projects: list[UUID]
    runners: list[str]
    jobs: list[dict[str, Any]]

    async def get(self, path: str, **params: Any) -> Any:
        response = await self.client.get(path, params=params)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        return response.json()


def _user_id(i: int) -> str:
    return UUID(int=i + 1).hex


def _runner_status(i: int) -> tuple[datetime | None, bool, datetime | None]:
    """last_seen_at, paused, revoked_at по номеру: online, stale, offline, paused, revoked, никогда не виден.

    Статус раннера считается от текущего времени, поэтому отметки берутся в момент посева, а не NOW
    модуля: в полном прогоне модуль импортируется на сбор задолго до теста, и «онлайн» успевал устареть.
    """
    now = datetime.now(UTC)
    match i % 6:
        case 0:
            return now - timedelta(seconds=5), False, None
        case 1:
            return now - timedelta(minutes=3), False, None
        case 2:
            return now - timedelta(hours=2), False, None
        case 3:
            return now - timedelta(seconds=5), True, None
        case 4:
            return now - timedelta(seconds=5), False, now - timedelta(days=1)
        case _:
            return None, False, None


async def _seed(engine: AsyncEngine) -> dict[str, Any]:
    users = [_user_id(i) for i in range(USERS)]
    orgs = [f"org_{UUID(int=1000 + i).hex}" for i in range(ORGS)]
    projects = [UUID(int=10_000 + i) for i in range(PROJECTS)]
    runners = [UUID(int=20_000 + i).hex for i in range(RUNNERS)]
    jobs: list[dict[str, Any]] = []
    for i in range(JOBS):
        project = i % PROJECTS
        owner_org = orgs[project % ORGS] if project % 3 == 0 else None
        jobs.append(
            {
                "id": UUID(int=30_000 + i),
                "kind": KINDS[i % len(KINDS)],
                "state": STATES[i % len(STATES)],
                "project_id": projects[project],
                "user_id": UUID(users[i % USERS]),
                "org_id": org_key(owner_org) if owner_org else None,
                "tags": ["tex"],
                "priority_class": 1,
                "vtime": 0.0,
                "queued_at": NOW - timedelta(minutes=JOBS - i),
                "max_attempts": 3,
                "timeout_s": 600.0,
                "payload": {},
                "runner_id": UUID(runners[i % RUNNERS]) if i % 2 else None,
            }
        )
    async with engine.begin() as conn:
        await conn.execute(
            insert(UserRow),
            [
                {
                    "id": uid,
                    "email": f"person{i}@example.org",
                    "email_normalized": f"person{i}@example.org",
                    "name": "Анна Петрова" if i == 7 else f"Человек {i:04d}",
                    "status": "active",
                    "created_at": NOW,
                }
                for i, uid in enumerate(users)
            ],
        )
        await conn.execute(
            insert(OrgRow),
            [{"id": oid, "slug": f"dept-{i}", "name": f"Кафедра {i:02d}"} for i, oid in enumerate(orgs)],
        )
        await conn.execute(
            insert(ProjectRow),
            [
                {
                    "id": pid,
                    "name": "Диплом 100%_ready" if i == 42 else f"Проект {i:05d}",
                    "owner_user_id": None if i % 3 == 0 else users[i % USERS],
                    "owner_org_id": orgs[i % ORGS] if i % 3 == 0 else None,
                    "workspace_path": f"p/{i}",
                    "kind": "thesis",
                    "lang": "ru",
                    "deleted_at": NOW if i % 50 == 49 else None,
                }
                for i, pid in enumerate(projects)
            ],
        )
        await conn.execute(
            insert(ProjectUsageRow),
            [
                {"project_id": pid, "bytes_tree": 1000 * (i + 1), "bytes_git": 10, "bytes_s3": 0, "measured_at": NOW}
                for i, pid in enumerate(projects)
                if i % 2 == 0
            ],
        )
        runner_rows = []
        for i, rid in enumerate(runners):
            seen, paused, revoked = _runner_status(i)
            runner_rows.append(
                {
                    "id": rid,
                    "name": f"runner-{i:04d}" if i != 11 else "gpu_box",
                    "token_hash": f"{i:064d}",
                    "tags": ["office", "verify"] if i % 4 == 0 else ["tex"],
                    "resource_class": "large" if i % 10 == 0 else "standard",
                    "concurrency": 2,
                    "version": VERSIONS[i % len(VERSIONS)],
                    "paused": paused,
                    "created_at": NOW - timedelta(minutes=i),
                    "last_seen_at": seen,
                    "revoked_at": revoked,
                }
            )
        await conn.execute(insert(RunnerRow), runner_rows)
        await conn.execute(
            insert(RunnerRegistrationTokenRow),
            [
                {
                    "id": f"rt_{i:05d}",
                    "token_hash": f"t{i:063d}",
                    "label": "Сервер в 305" if i == 3 else f"token {i:05d}",
                    "max_uses": 2,
                    # Каждый четвёртый отозван, затем исчерпан, истёк и действует.
                    "uses": 2 if i % 4 == 1 else 0,
                    "created_at": NOW - timedelta(minutes=i),
                    "expires_at": NOW - timedelta(hours=1) if i % 4 == 2 else NOW + timedelta(days=1),
                    "revoked_at": NOW if i % 4 == 0 else None,
                }
                for i in range(TOKENS)
            ],
        )
        await conn.execute(insert(JobRow), jobs)
        await conn.execute(
            insert(AIProviderRow),
            [
                {
                    "id": UUID(int=40_000 + i),
                    "owner_kind": "instance" if i % 2 == 0 else "user",
                    "owner_id": None if i % 2 == 0 else users[i],
                    "name": f"Провайдер {i:02d}",
                    "type": ("ollama", "openai", "claude")[i % 3],
                    "base_url": f"http://10.0.0.{i}:11434" if i % 3 == 0 else "",
                    "models": [],
                    "created_at": NOW - timedelta(minutes=60 - i),
                }
                for i in range(60)
            ],
        )
    return {"users": users, "orgs": orgs, "projects": projects, "runners": runners, "jobs": jobs}


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, sessions: SessionProvider, resolver: _Resolver) -> None:
        super().__init__()
        self.sessions = sessions
        self.resolver_ = resolver

    @provide
    def resolver(self) -> IActorResolver:
        return self.resolver_

    @provide
    def list_runners(self) -> ListRunnersUC:
        return ListRunnersUC(SqlRunnerAdminReader(self.sessions))

    @provide
    def runner_registry(self) -> RunnerRegistry:
        # Список раннеров разрешает владельца (owners_of) и настройки личных раннеров
        # (personal_settings) через реестр; без личных раннеров в этом мире оба пусты.
        return RunnerRegistry(
            SqlRunnerRepository(self.sessions),
            SqlRegistrationTokenRepository(self.sessions),
            InMemoryAuditLog(),
            NoopUow(),
        )

    @provide
    def runner_summary(self) -> RunnerSummaryUC:
        return RunnerSummaryUC(SqlRunnerAdminReader(self.sessions))

    @provide
    def list_tokens(self) -> ListRegistrationTokensUC:
        return ListRegistrationTokensUC(SqlRunnerAdminReader(self.sessions))

    @provide
    def pick_runners(self) -> PickRunnersUC:
        return PickRunnersUC(SqlRunnerAdminReader(self.sessions))

    @provide
    def list_queue(self) -> ListQueueUC:
        return ListQueueUC(SqlJobAdminReader(self.sessions))

    @provide
    def pick_projects(self) -> PickProjectsUC:
        return PickProjectsUC(SqlAdminProjectPicker(self.sessions))

    @provide
    def storage_owners(self) -> ListStorageOwnersUC:
        return ListStorageOwnersUC(SqlStorageUsageReader(self.sessions))

    @provide
    def providers(self) -> ListInstanceAiProvidersUC:
        return ListInstanceAiProvidersUC(PostgresAIProviderRepository(self.sessions, ReversingCipher()))


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[World]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    seeded = await _seed(pg_migrated_engine)
    resolver = _Resolver()
    app = FastAPI()
    app.include_router(make_admin_router())
    install_exception_handlers(app)
    container = make_async_container(
        _Provider(SessionProvider(create_sessionmaker(pg_migrated_engine)), resolver), FastapiProvider()
    )
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield World(client=client, resolver=resolver, **seeded)
    await container.close()


_LISTS = [
    "/api/admin/runners",
    "/api/admin/runners/summary",
    "/api/admin/runner-tokens",
    "/api/admin/queue",
    "/api/admin/storage/owners",
    "/api/admin/ai-providers",
    "/api/admin/pickers/runners",
    "/api/admin/pickers/projects",
]


async def test__lists__anonymous_401_not_admin_404(world: World) -> None:
    for actor, expected in ((None, 401), (STUDENT, 404)):
        world.resolver.actor = actor
        for path in _LISTS:
            assert (await world.client.get(path)).status_code == expected, path


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/admin/runners", {"limit": 0}),
        ("/api/admin/runners", {"limit": 201}),
        ("/api/admin/runners", {"offset": -1}),
        ("/api/admin/runners", {"sort": "token_hash"}),
        ("/api/admin/runners", {"sort": "--name"}),
        ("/api/admin/runners", {"status": "sleeping"}),
        ("/api/admin/runners", {"q": "x" * 201}),
        ("/api/admin/runner-tokens", {"status": "used"}),
        ("/api/admin/runner-tokens", {"sort": "uses"}),
        ("/api/admin/queue", {"cursor": "not a cursor"}),
        ("/api/admin/queue", {"cursor": base64.urlsafe_b64encode(b"abc").decode()}),
        ("/api/admin/queue", {"from": "2026-10-01T00:00:00"}),
        ("/api/admin/queue", {"state": "sleeping"}),
        ("/api/admin/queue", {"limit": 201}),
        ("/api/admin/storage/owners", {"kind": "group"}),
        ("/api/admin/storage/owners", {"sort": "email"}),
        ("/api/admin/ai-providers", {"type": "gemini"}),
        ("/api/admin/ai-providers", {"sort": "base_url"}),
        ("/api/admin/pickers/runners", {"limit": 21}),
        ("/api/admin/pickers/projects", {"id": "not-a-uuid"}),
    ],
)
async def test__lists__bad_params__422(world: World, path: str, params: dict[str, Any]) -> None:
    assert (await world.client.get(path, params=params)).status_code == 422


async def test__runners__page_total_and_boundaries(world: World) -> None:
    first = await world.get("/api/admin/runners")
    last = await world.get("/api/admin/runners", limit=50, offset=RUNNERS - 10)
    beyond = await world.get("/api/admin/runners", offset=RUNNERS)

    assert (first["total"], first["limit"], first["offset"], len(first["items"])) == (RUNNERS, 50, 0, 50)
    assert len(last["items"]) == 10
    assert beyond == {"items": [], "total": RUNNERS, "limit": 50, "offset": RUNNERS}


async def test__runners__default_order_is_status_then_name(world: World) -> None:
    order = ["online", "stale", "offline", "paused", "revoked"]
    seen: list[str] = []
    for offset in range(0, RUNNERS, 200):
        seen += [r["status"] for r in (await world.get("/api/admin/runners", limit=200, offset=offset))["items"]]

    assert len(seen) == RUNNERS
    assert seen == sorted(seen, key=order.index)


async def test__runners__status_filters_match_statuses(world: World) -> None:
    online = await world.get("/api/admin/runners", status="online", limit=200)
    silent = await world.get("/api/admin/runners", status=["stale", "offline"], limit=200)

    assert online["total"] == RUNNERS // 6 + (1 if RUNNERS % 6 > 0 else 0)
    assert {r["status"] for r in online["items"]} == {"online"}
    assert {r["status"] for r in silent["items"]} == {"stale", "offline"}
    # Никогда не выходивший на связь раннер тоже offline.
    assert any(r["last_seen_at"] is None for r in silent["items"])


async def test__runners__search_tag_class_and_outdated(world: World) -> None:
    by_name = await world.get("/api/admin/runners", q="  GPU_  ")
    by_version = await world.get("/api/admin/runners", q="0.10.1", limit=1)
    by_tag = await world.get("/api/admin/runners", tag="office", limit=1)
    large = await world.get("/api/admin/runners", resource_class="large", limit=1)
    outdated = await world.get("/api/admin/runners", outdated="true", limit=200)
    current = await world.get("/api/admin/runners", outdated="false", limit=200)
    summary = await world.get("/api/admin/runners/summary")

    assert [r["name"] for r in by_name["items"]] == ["gpu_box"]
    assert by_version["total"] == RUNNERS // len(VERSIONS)
    assert by_tag["total"] == RUNNERS // 4
    assert large["total"] == RUNNERS // 10
    # Новейшая версия сравнивается по числам: 0.10.1 новее 0.9.9 и 0.10.0.
    assert summary["newest_version"] == "0.10.1"
    assert {r["version"] for r in outdated["items"]} == {"0.2.0", "0.9.9", "0.10.0"}
    assert not any(r["revoked"] for r in outdated["items"])
    assert outdated["total"] == summary["outdated"]
    assert outdated["total"] + current["total"] == RUNNERS


async def test__runners__sorts_with_stable_tiebreak(world: World) -> None:
    by_name = await world.get("/api/admin/runners", sort="name", limit=3)
    by_name_desc = await world.get("/api/admin/runners", sort="-name", limit=1)
    by_version = await world.get("/api/admin/runners", sort="-version", limit=200)
    by_seen = await world.get("/api/admin/runners", sort="-last_seen_at", limit=200, offset=200)
    page_a = await world.get("/api/admin/runners", sort="version", limit=37, offset=0)
    page_b = await world.get("/api/admin/runners", sort="version", limit=37, offset=37)

    assert [r["name"] for r in by_name["items"]] == ["gpu_box", "runner-0000", "runner-0001"]
    assert by_name_desc["items"][0]["name"] == "runner-0399"
    assert by_version["items"][0]["version"] == "0.10.1"
    # Пустой last_seen_at уходит в конец в обе стороны.
    assert by_seen["items"][-1]["last_seen_at"] is None
    assert not {r["id"] for r in page_a["items"]} & {r["id"] for r in page_b["items"]}


async def test__runners__summary_counts(world: World) -> None:
    summary = await world.get("/api/admin/runners/summary")

    per = dict.fromkeys(("online", "stale", "offline", "paused", "revoked"), 0)
    for i in range(RUNNERS):
        per[("online", "stale", "offline", "paused", "revoked", "offline")[i % 6]] += 1
    assert {k: summary[k] for k in per} == per


async def test__runner_picker__first_matches_and_has_more(world: World) -> None:
    some = await world.get("/api/admin/pickers/runners", q="runner-00")
    exact = await world.get("/api/admin/pickers/runners", q="gpu")

    assert len(some["items"]) == 20
    assert some["has_more"] is True
    assert exact == {
        "items": [{"kind": "runner", "id": world.runners[11], "name": "gpu_box", "detail": "tex"}],
        "has_more": False,
    }


async def test__tokens__status_filter_search_and_sort(world: World) -> None:
    default = await world.get("/api/admin/runner-tokens", limit=3)
    active = await world.get("/api/admin/runner-tokens", status="active", limit=200)
    dead = await world.get("/api/admin/runner-tokens", status=["expired", "exhausted"], limit=1)
    searched = await world.get("/api/admin/runner-tokens", q="сервер В 30")
    by_label = await world.get("/api/admin/runner-tokens", sort="-label", limit=1)
    by_expiry = await world.get("/api/admin/runner-tokens", sort="expires_at", limit=1)

    assert default["total"] == TOKENS
    assert [t["id"] for t in default["items"]] == ["rt_00000", "rt_00001", "rt_00002"]
    assert active["total"] == TOKENS // 4
    assert all(not t["revoked"] and t["uses"] < t["max_uses"] for t in active["items"])
    assert dead["total"] == TOKENS // 2
    assert [t["label"] for t in searched["items"]] == ["Сервер в 305"]
    assert by_label["items"][0]["label"] == "Сервер в 305"
    assert by_expiry["items"][0]["id"] == "rt_00002"


async def _all_jobs(world: World, **params: Any) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    pages = 0
    while True:
        page = await world.get("/api/admin/queue", limit=200, **params, **({"cursor": cursor} if cursor else {}))
        items += page["items"]
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            return items, pages


async def test__queue__cursor_walks_everything_once_newest_first(world: World) -> None:
    items, pages = await _all_jobs(world)

    assert len(items) == JOBS
    assert len({j["id"] for j in items}) == JOBS
    assert pages == JOBS // 200
    queued = [j["queued_at"] for j in items]
    assert queued == sorted(queued, reverse=True)


async def test__queue__cursor_is_opaque_and_legacy_digits_still_work(world: World) -> None:
    first = await world.get("/api/admin/queue", limit=10)
    cursor = first["next_cursor"]
    seq = decode_cursor(cursor)
    by_new = await world.get("/api/admin/queue", limit=10, cursor=cursor)
    by_legacy = await world.get("/api/admin/queue", limit=10, cursor=str(seq))

    assert not cursor.isdigit()
    assert by_new["items"] == by_legacy["items"]
    assert by_new["items"][0]["id"] != first["items"][-1]["id"]


async def test__queue__filters_combine(world: World) -> None:
    user = world.users[7]
    runner = world.runners[3]
    org = world.orgs[0]
    by_user, _ = await _all_jobs(world, user_id=user)
    by_states, _ = await _all_jobs(world, state=["failed", "timed_out"], kind="compile")
    by_runner, _ = await _all_jobs(world, runner_id=runner)
    by_org, _ = await _all_jobs(world, org_id=org)
    by_project, _ = await _all_jobs(world, project_id=str(world.projects[5]))
    window_from = (NOW - timedelta(minutes=100)).isoformat()
    window_to = (NOW - timedelta(minutes=50)).isoformat()
    by_time, _ = await _all_jobs(world, **{"from": window_from, "to": window_to})

    def expected(pred: Any) -> set[str]:
        return {str(j["id"]) for j in world.jobs if pred(j)}

    assert {j["id"] for j in by_user} == expected(lambda j: j["user_id"] == UUID(user))
    assert {j["id"] for j in by_states} == expected(
        lambda j: j["state"] in {"failed", "timed_out"} and j["kind"] == "compile"
    )
    assert {j["id"] for j in by_runner} == expected(lambda j: j["runner_id"] == UUID(runner))
    assert {j["id"] for j in by_org} == expected(lambda j: j["org_id"] == org_key(org))
    assert {j["id"] for j in by_project} == expected(lambda j: j["project_id"] == world.projects[5])
    # from включительно, to не включая: ровно 50 минутных отметок.
    assert len(by_time) == 50


async def test__queue__search_by_job_id_project_and_person(world: World) -> None:
    job = world.jobs[123]
    by_id, _ = await _all_jobs(world, q=str(job["id"]))
    by_hex, _ = await _all_jobs(world, q=job["id"].hex.upper())
    by_person, _ = await _all_jobs(world, q="аННа петРова")
    by_email, _ = await _all_jobs(world, q="person7@")
    by_project, _ = await _all_jobs(world, q="100%_ready")
    with_state, _ = await _all_jobs(world, q="Анна", state="failed")

    def expected(pred: Any) -> set[str]:
        return {str(j["id"]) for j in world.jobs if pred(j)}

    assert [j["id"] for j in by_id] == [str(job["id"])]
    assert [j["id"] for j in by_hex] == [str(job["id"])]
    anna = expected(lambda j: j["user_id"] == UUID(world.users[7]))
    assert {j["id"] for j in by_person} == anna
    assert {j["id"] for j in by_email} == anna
    assert {j["id"] for j in by_project} == expected(lambda j: j["project_id"] == world.projects[42])
    assert {j["id"] for j in with_state} == anna & expected(lambda j: j["state"] == "failed")


async def test__queue__rows_carry_names_and_estimate_only_without_filters(world: World) -> None:
    page = await world.get("/api/admin/queue", user_id=world.users[7], limit=200)
    plain = await world.get("/api/admin/queue", limit=1)
    org_job = (await world.get("/api/admin/queue", org_id=world.orgs[0], limit=1))["items"][0]

    assert page["total_estimate"] is None
    assert {j["user_name"] for j in page["items"]} == {"Анна Петрова"}
    assert {j["user_email"] for j in page["items"]} == {"person7@example.org"}
    with_runner = next(j for j in page["items"] if j["runner_id"])
    assert with_runner["runner_name"].startswith("runner-")
    assert all(j["project_name"] for j in page["items"])
    assert org_job["org_name"] == "Кафедра 00"
    assert plain["total_estimate"] is None or plain["total_estimate"] >= 0


async def test__project_picker__escapes_like_and_skips_deleted(world: World) -> None:
    literal = await world.get("/api/admin/pickers/projects", q="100%_")
    wildcard = await world.get("/api/admin/pickers/projects", q="%")
    deleted = await world.get("/api/admin/pickers/projects", q="Проект 00049")

    assert [p["name"] for p in literal["items"]] == ["Диплом 100%_ready"]
    assert literal["items"][0]["detail"] == "Кафедра 06"
    assert [p["name"] for p in wildcard["items"]] == ["Диплом 100%_ready"]
    assert deleted == {"items": [], "has_more": False}


async def test__pickers__by_id_find_one_even_deleted_project(world: World) -> None:
    gpu = await world.get("/api/admin/pickers/runners", id=world.runners[11])
    project = await world.get("/api/admin/pickers/projects", id=str(world.projects[5]))
    # Удалённый проект поиск не находит, а по id находит: у него остались задачи в очереди.
    deleted = await world.get("/api/admin/pickers/projects", id=str(world.projects[49]))
    unknown = await world.get("/api/admin/pickers/projects", id=str(uuid4()))

    assert [r["name"] for r in gpu["items"]] == ["gpu_box"]
    assert [p["id"] for p in project["items"]] == [str(world.projects[5])]
    assert [p["name"] for p in deleted["items"]] == ["Проект 00049"]
    assert unknown == {"items": [], "has_more": False}


async def test__storage_owners__kinds_search_sort_and_total(world: World) -> None:
    everyone = await world.get("/api/admin/storage/owners", limit=200)
    orgs = await world.get("/api/admin/storage/owners", kind="org", sort="name", limit=200)
    users = await world.get("/api/admin/storage/owners", kind="user", limit=1)
    anna = await world.get("/api/admin/storage/owners", q="person7@")
    heavy = await world.get("/api/admin/storage/owners", sort="-bytes", limit=1)

    # Владельцы живых проектов: каждый третий проект у организации, остальные личные.
    live = [i for i in range(PROJECTS) if i % 50 != 49]
    owners = {i % USERS for i in live if i % 3}
    org_owners = sorted({i % ORGS for i in live if i % 3 == 0})
    assert everyone["total"] == len(org_owners) + len(owners)
    projects = [o["projects"] for o in everyone["items"]]
    assert projects == sorted(projects, reverse=True)
    assert [o["name"] for o in orgs["items"]] == [f"Кафедра {i:02d}" for i in org_owners]
    assert all(o["email"] is None for o in orgs["items"])
    assert users["total"] == len(owners)
    assert [(o["kind"], o["name"], o["email"]) for o in anna["items"]] == [
        ("user", "Анна Петрова", "person7@example.org")
    ]
    # Удалённые проекты не считаются; место только по измеренным проектам.
    org_bytes: dict[str, int] = {}
    for i in live:
        if i % 3 == 0 and i % 2 == 0:
            org_bytes[world.orgs[i % ORGS]] = org_bytes.get(world.orgs[i % ORGS], 0) + 1000 * (i + 1) + 10
    assert heavy["items"][0]["bytes"] == max(org_bytes.values())


async def test__ai_providers__only_shared_with_search_type_and_sort(world: World) -> None:
    shared = await world.get("/api/admin/ai-providers", limit=200)
    ollama = await world.get("/api/admin/ai-providers", type="ollama", limit=200)
    by_url = await world.get("/api/admin/ai-providers", q="10.0.0.12:")
    by_name = await world.get("/api/admin/ai-providers", sort="-name", limit=2, offset=1)

    assert shared["total"] == 30
    created = [p["created_at"] for p in shared["items"]]
    assert created == sorted(created)
    assert {p["type"] for p in ollama["items"]} == {"ollama"}
    assert ollama["total"] == 10
    assert [p["name"] for p in by_url["items"]] == ["Провайдер 12"]
    assert [p["name"] for p in by_name["items"]] == ["Провайдер 56", "Провайдер 54"]
    assert "api_key" not in shared["items"][0]
