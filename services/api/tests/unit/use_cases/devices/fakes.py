"""Заготовки для тестов подключённых Студий: память вместо БД и часы, которые двигает тест."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from hse_doc_studio.core.devices.entities import (
    ConnectedDevice,
    DeviceActivity,
    DeviceOs,
    DeviceReport,
    EndpointReport,
    PresenceConfig,
    ProjectReport,
    RunnerReport,
    SyncCode,
)
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor
from hse_doc_studio.core.jobs.routing import PersonalRunnerSettings
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint, Runner, RunnerOwnerKind
from hse_doc_studio.core.jobs.wire import FEATURE_AI_RELAY
from hse_doc_studio.infra.devices.registry import PresenceRegistry
from hse_doc_studio.use_cases.devices.service import DeviceViewBuilder

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
PROJECT = UUID("11111111-1111-1111-1111-111111111111")
CONFIG = PresenceConfig(interval_s=60, online_window_s=180, persist_interval_s=120, retention_days=60)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: int) -> None:
        self.now += timedelta(**delta)


class MemoryDevices:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], ConnectedDevice] = {}
        self.writes = 0

    async def upsert(self, device: ConnectedDevice) -> None:
        self.writes += 1
        self.rows[(device.user_id, device.device_id)] = device

    async def list_for_user(self, user_id: str) -> list[ConnectedDevice]:
        return sorted(
            (d for d in self.rows.values() if d.user_id == user_id), key=lambda d: d.last_seen_at, reverse=True
        )

    async def get(self, user_id: str, device_id: str) -> ConnectedDevice | None:
        return self.rows.get((user_id, device_id))

    async def list_for_project(self, project_id: UUID) -> list[ConnectedDevice]:
        return [d for d in self.rows.values() if project_id in d.project_ids]

    async def delete(self, user_id: str, device_id: str) -> bool:
        return self.rows.pop((user_id, device_id), None) is not None

    async def purge_older_than(self, horizon: datetime) -> int:
        stale = [k for k, d in self.rows.items() if d.last_seen_at < horizon]
        for key in stale:
            del self.rows[key]
        return len(stale)


class MemoryRunners:
    def __init__(self, *runners: Runner) -> None:
        self.items = {r.id: r for r in runners}

    async def list_owned(self, owner_id: str) -> list[Runner]:
        return [r for r in self.items.values() if r.owner_id == owner_id]


class MemoryProviders:
    def __init__(self, *providers: AIProvider) -> None:
        self.items = list(providers)

    async def list_all(self) -> list[AIProvider]:
        return list(self.items)


class FixedSettings:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    async def current(self) -> PersonalRunnerSettings:
        return PersonalRunnerSettings(enabled=self.enabled)


class MemoryUsers:
    def __init__(self, *users: User) -> None:
        self.items = {u.id: u for u in users}

    async def get(self, user_id: str) -> User | None:
        return self.items.get(user_id)


class MemoryAcl:
    """Участники проекта: `{user_id: Role}`; остальным проект не виден."""

    def __init__(self, members: dict[str, Role], *, show_sources: bool = True) -> None:
        self.members = members
        self.show_sources = show_sources

    async def load_for(self, actor: Actor, project_id: UUID, *, include_links: bool = True) -> ProjectAcl | None:
        role = self.members.get(actor.id or "")
        if role is None:
            return None
        return ProjectAcl(
            project_id=str(project_id),
            owner_id="owner",
            grants={actor.key or "": Grant(role=role, show_sources=self.show_sources)},
        )


def user(user_id: str, name: str, *, admin: bool = False) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.org",
        email_normalized=f"{user_id}@example.org",
        name=name,
        status=UserStatus.active,
        created_at=T0,
        is_instance_admin=admin,
    )


def actor(user_id: str, name: str = "Person") -> Actor:
    return Actor.user(user_id, name, f"{user_id}@example.org")


def runner(
    runner_id: str = "r1",
    owner: str = "anna",
    *,
    seen: datetime = T0,
    endpoints: tuple[str, ...] = ("ollama",),
    relay: bool = True,
    paused: bool = False,
) -> Runner:
    return Runner(
        id=runner_id,
        name="MacBook Анны",
        token_hash="x",
        tags=frozenset({"ai", "tex"}),
        concurrency=2,
        resource_class="standard",
        version="0.6.0",
        created_at=T0,
        last_seen_at=seen,
        paused=paused,
        owner_kind=RunnerOwnerKind.user,
        owner_id=owner,
        features=frozenset({FEATURE_AI_RELAY}) if relay else frozenset(),
        ai_endpoints=tuple(DeclaredAiEndpoint(name, AiEndpointFlavor.ollama) for name in endpoints),
    )


def provider(runner_id: str = "r1", endpoint: str = "ollama", name: str = "Моя Ollama") -> AIProvider:
    return AIProvider(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        name=name,
        type=AIProviderType.runner,
        api_key="",
        base_url="",
        models=[],
        created_at=T0,
        runner_id=runner_id,
        runner_endpoint=endpoint,
    )


def report(
    device_id: str = "a" * 32,
    *,
    name: str = "MacBook Анны",
    activity: DeviceActivity = DeviceActivity.idle,
    runner_id: str | None = "r1",
    endpoints: tuple[EndpointReport, ...] = (EndpointReport("ollama", "ollama", True, ("qwen3:4b",)),),
    projects: tuple[ProjectReport, ...] = (ProjectReport(PROJECT, SyncCode.synced, last_sync_at=T0),),
) -> DeviceReport:
    return DeviceReport(
        device_id=device_id,
        name=name,
        version="0.6.0",
        os=DeviceOs.macos,
        activity=activity,
        runner=RunnerReport(runner_id=runner_id, state="online", running_jobs=0) if runner_id else None,
        endpoints=endpoints,
        projects=projects,
    )


def stored(user_id: str, rep: DeviceReport, *, seen: datetime = T0) -> ConnectedDevice:
    return ConnectedDevice(
        user_id=user_id,
        device_id=rep.device_id,
        first_seen_at=seen,
        last_seen_at=seen,
        report=rep,
        project_ids=tuple(p.project_id for p in rep.projects),
    )


def builder(
    clock: Clock,
    *,
    runners: MemoryRunners | None = None,
    providers: MemoryProviders | None = None,
    registry: PresenceRegistry | None = None,
    enabled: bool = True,
) -> DeviceViewBuilder:
    return DeviceViewBuilder(
        runners or MemoryRunners(),  # type: ignore[arg-type]
        providers or MemoryProviders(),  # type: ignore[arg-type]
        FixedSettings(enabled),  # type: ignore[arg-type]
        registry or PresenceRegistry(),
        CONFIG,
        clock=clock,
    )
