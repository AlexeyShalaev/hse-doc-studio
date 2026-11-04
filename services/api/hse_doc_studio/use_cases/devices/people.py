"""Люди в проекте: сигнал веб-вкладки и общий список «кто сейчас здесь» (docs/design/connected-devices.md, 15).

Источников два: вкладка, которая шлёт сигнал раз в минуту и при смене места, и локальная Студия, уже сообщающая серверу
свои проекты (`RecordHeartbeatUC`). Отдельного канала для людей нет: окно «онлайн» и интервал общие с устройствами, в БД
и в аудит сигнал вкладки не пишется. Права проверяются на каждый показ (с короткой памятью проверки): потерявший доступ
человек исчезает из списка в течение `VERDICT_TTL_S`, а читатель не может заявить, что «редактирует».
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.collab.colors import person_color
from hse_doc_studio.core.devices.entities import ConnectedDevice, PresenceConfig
from hse_doc_studio.core.devices.people import (
    MAX_PEOPLE,
    NEEDS_WRITE,
    WRITE_ROLES,
    Activity,
    Channel,
    PersonOnline,
    ProjectPeople,
    WebSession,
    WebSignal,
)
from hse_doc_studio.core.devices.protocols import IDeviceRepository, IWebPresenceRegistry
from hse_doc_studio.core.identity.normalize import avatar_initials
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.use_cases.devices.service import DeviceViewBuilder

VERDICT_TTL_S = 20.0
_VERDICT_LIMIT = 4096


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Verdict:
    """Участник ли человек проекта и кем: решение по членству, без ссылок доступа."""

    role: Role | None
    name: str


class VerdictCache:
    """Общая память проверок на процесс: запросы приходят со своими репозиториями, а помнить нужно между запросами."""

    def __init__(self, ttl_s: float = VERDICT_TTL_S, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_s
        self._monotonic = monotonic
        self._items: dict[tuple[UUID, str], tuple[float, _Verdict]] = {}

    def get(self, key: tuple[UUID, str]) -> _Verdict | None:
        cached = self._items.get(key)
        if cached is not None and self._monotonic() - cached[0] < self._ttl:
            return cached[1]
        return None

    def put(self, key: tuple[UUID, str], verdict: _Verdict) -> None:
        now = self._monotonic()
        if len(self._items) >= _VERDICT_LIMIT:
            self._items = {k: v for k, v in self._items.items() if now - v[0] < self._ttl}
        self._items[key] = (now, verdict)

    def forget(self, project_id: UUID, user_id: str) -> None:
        self._items.pop((project_id, user_id), None)


class MemberVerdicts:
    """«Участник ли и с какой ролью»: список людей не должен спрашивать БД о каждом на каждый сигнал."""

    def __init__(self, cache: VerdictCache, acl: IProjectAclRepository, users: IUserRepository) -> None:
        self._cache = cache
        self._acl = acl
        self._users = users

    async def of(self, project_id: UUID, user_id: str, known_name: str | None = None) -> _Verdict:
        key = (project_id, user_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        name = known_name
        if name is None:
            user = await self._users.get(user_id)
            name = user.name if user is not None else ""
        member = Actor.user(user_id, name or None)
        acl = await self._acl.load_for(member, project_id, include_links=False)
        grant = acl.grant_for(member) if acl is not None else None
        allowed = decide(member, Action.PROJECT_VIEW, acl) is Decision.allow
        verdict = _Verdict(grant.role if allowed and grant is not None else None, name)
        self._cache.put(key, verdict)
        return verdict


class ProjectPeopleUC:
    """Собирает список людей онлайн для одного смотрящего. Смотрящий должен уже иметь право просмотра проекта."""

    def __init__(
        self,
        web: IWebPresenceRegistry,
        devices: IDeviceRepository,
        builder: DeviceViewBuilder,
        verdicts: MemberVerdicts,
        config: PresenceConfig,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._web = web
        self._devices = devices
        self._builder = builder
        self._verdicts = verdicts
        self._config = config
        self._clock = clock

    async def execute(
        self, viewer: Actor, project_id: UUID, devices: list[ConnectedDevice] | None = None
    ) -> ProjectPeople:
        """`devices` отдаёт тот, кто уже спросил устройства проекта: второй запрос в БД не нужен."""
        now = self._clock()
        window = self._config.online_window_s
        by_user: dict[str, list[WebSession]] = {}
        for session in self._web.sessions(project_id, now, window):
            by_user.setdefault(session.user_id, []).append(session)
        studio: dict[str, datetime] = {}
        reporting = devices if devices is not None else await self._devices.list_for_project(project_id)
        for device in reporting:
            if self._builder.online(device):
                seen = self._builder.last_seen(device)
                studio[device.user_id] = max(seen, studio.get(device.user_id, seen))
        found: list[PersonOnline] = []
        for user_id in sorted(set(by_user) | set(studio)):
            person = await self._person(viewer, project_id, user_id, by_user.get(user_id, []), studio.get(user_id))
            if person is not None:
                found.append(person)
        found.sort(key=lambda p: (not p.me, p.name.casefold(), p.user_id))
        return ProjectPeople(
            interval_s=self._config.interval_s,
            online_window_s=window,
            people=tuple(found[:MAX_PEOPLE]),
            total=len(found),
        )

    async def _person(
        self,
        viewer: Actor,
        project_id: UUID,
        user_id: str,
        sessions: list[WebSession],
        studio_seen: datetime | None,
    ) -> PersonOnline | None:
        freshest = max(sessions, key=lambda s: s.seen_at) if sessions else None
        verdict = await self._verdicts.of(project_id, user_id, freshest.name if freshest is not None else None)
        if verdict.role is None:
            return None
        present = ((Channel.web, freshest is not None), (Channel.studio, studio_seen is not None))
        channels = tuple(channel for channel, there in present if there)
        activity = freshest.activity if freshest is not None else Activity.local
        if activity in NEEDS_WRITE and verdict.role not in WRITE_ROLES:
            activity = Activity.viewing
        seen = max(t for t in (freshest.seen_at if freshest is not None else None, studio_seen) if t is not None)
        name = verdict.name or "?"
        return PersonOnline(
            user_id=user_id,
            name=name,
            initials=avatar_initials(name),
            color=person_color(user_id),
            role=verdict.role,
            me=user_id == viewer.id,
            activity=activity,
            doc_id=freshest.doc_id if freshest is not None else None,
            channels=channels,
            seen_at=seen,
        )


class RecordWebPresenceUC:
    """Сигнал одной вкладки: запоминает её место и сразу отвечает списком людей (отдельного запроса за списком нет)."""

    def __init__(
        self,
        web: IWebPresenceRegistry,
        verdicts: MemberVerdicts,
        people: ProjectPeopleUC,
        config: PresenceConfig,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._web = web
        self._verdicts = verdicts
        self._people = people
        self._config = config
        self._clock = clock

    async def execute(self, actor: Actor, project_id: UUID, signal: WebSignal) -> ProjectPeople:
        """Участник проекта попадает в список; всё остальное (гость, ссылка, чужой) получает пустой ответ."""
        if actor.id is None or actor.is_guest:
            return self._empty()
        verdict = await self._verdicts.of(project_id, actor.id, actor.name)
        if verdict.role is None:
            return self._empty()
        activity = signal.activity
        if activity in NEEDS_WRITE and verdict.role not in WRITE_ROLES:
            activity = Activity.viewing
        self._web.observe(
            project_id,
            actor.id,
            verdict.name or actor.name or "",
            WebSignal(signal.session_id, activity, signal.doc_id),
            self._clock(),
            self._config.online_window_s,
        )
        return await self._people.execute(actor, project_id)

    async def empty(self) -> ProjectPeople:
        return self._empty()

    def _empty(self) -> ProjectPeople:
        return ProjectPeople(self._config.interval_s, self._config.online_window_s, (), 0)


class LeaveWebPresenceUC:
    """Вкладка закрыта: её сессия уходит сразу, не дожидаясь окна. Чужую не убрать: ключ включает человека."""

    def __init__(self, web: IWebPresenceRegistry) -> None:
        self._web = web

    def execute(self, actor: Actor, project_id: UUID, session_id: str) -> None:
        if actor.id is not None and not actor.is_guest:
            self._web.leave(project_id, actor.id, session_id)
