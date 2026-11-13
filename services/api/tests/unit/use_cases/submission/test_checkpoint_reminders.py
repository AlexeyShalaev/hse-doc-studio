"""Напоминание автору о сроке контрольной точки (docs/design/signing-route.md, 16.7): проход задачи лидера.

Хранилище и уведомления в памяти: «уже напомнили» хранилище видит по уведомлениям с ключом повтора, как в Postgres.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Collection
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from hse_doc_studio.core.checkpoint_deadlines import reminder_key
from hse_doc_studio.core.checkpoint_reminders import DueCheckpoint, ReminderRecipient
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.use_cases.submission.checkpoint_reminders import CheckpointReminderSweeper

pytestmark = pytest.mark.unit

MSK = timezone(timedelta(hours=3))
PROJECT = UUID("5b0c1d2e-3f40-4152-8364-758697a8b9c0")
OTHER = UUID("0d1e2f30-4152-4637-8899-aabbccddeeff")
TOPIC = "topic-approval"
DEADLINE = datetime(2026, 11, 15, 23, 59, tzinfo=MSK)
NAME = {"ru": "Заявка на тему КП (SmartLMS)", "en": "Topic application (SmartLMS)"}


@dataclass
class _Sent:
    user_id: str
    kind: NotificationKind
    payload: NotificationPayload
    dedupe_key: str | None


@dataclass
class _World:
    deadlines: dict[tuple[UUID, str], datetime] = field(default_factory=lambda: {(PROJECT, TOPIC): DEADLINE})
    people: dict[UUID, list[ReminderRecipient]] = field(
        default_factory=lambda: {PROJECT: [ReminderRecipient("owner", "ru"), ReminderRecipient("coauthor", "en")]}
    )
    builds: dict[tuple[UUID, str], list[datetime]] = field(default_factory=dict)
    sent: list[_Sent] = field(default_factory=list)
    broken: set[UUID] = field(default_factory=set)
    locks: list[str] = field(default_factory=list)


class _Store:
    def __init__(self, world: _World) -> None:
        self._w = world

    async def due(self, *, now: datetime, until: datetime) -> list[DueCheckpoint]:
        return [
            DueCheckpoint(project_id, f"Проект {project_id.hex[:4]}", profile_id, deadline, NAME)
            for (project_id, profile_id), deadline in sorted(self._w.deadlines.items())
            if now < deadline <= until
        ]

    async def lock(self, key: str) -> None:
        self._w.locks.append(key)

    async def built(self, project_id: UUID, profile_id: str, *, since: datetime) -> list[datetime]:
        return [moment for moment in self._w.builds.get((project_id, profile_id), []) if moment >= since]

    async def recipients(self, project_id: UUID) -> list[ReminderRecipient]:
        if project_id in self._w.broken:
            raise RuntimeError("project is gone")
        return list(self._w.people.get(project_id, []))

    async def reminded(self, user_ids: Collection[str], key: str) -> set[str]:
        return {s.user_id for s in self._w.sent if s.dedupe_key == key and s.user_id in user_ids}


class _Notifier:
    def __init__(self, world: _World) -> None:
        self._w = world

    async def notify(
        self,
        user_id: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        dedupe_key: str | None = None,
        mail: bool = True,
    ) -> None:
        assert mail
        self._w.sent.append(_Sent(user_id, kind, payload, dedupe_key))


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


async def _run(world: _World, now: datetime, *, days: int = 3) -> int:
    """Новый объект на каждый проход: как после перезапуска сервера или смены лидера."""
    sweeper = CheckpointReminderSweeper(_Store(world), _Notifier(world), _Uow(), days=days, clock=lambda: now)
    return await sweeper.run()


async def test__three_days_before__owner_and_authors_once_with_point_name_and_deadline() -> None:
    world = _World()
    now = DEADLINE - timedelta(days=3)

    first = await _run(world, now)
    second = await _run(world, now + timedelta(minutes=15))
    third = await _run(world, DEADLINE - timedelta(hours=1))

    assert (first, second, third) == (2, 0, 0)
    key = reminder_key(PROJECT, TOPIC, DEADLINE)
    assert [(s.user_id, s.kind, s.dedupe_key) for s in world.sent] == [
        ("owner", NotificationKind.checkpoint_due, key),
        ("coauthor", NotificationKind.checkpoint_due, key),
    ]
    owner, coauthor = world.sent[0].payload, world.sent[1].payload
    assert owner == NotificationPayload(
        project_id=str(PROJECT),
        project_name=f"Проект {PROJECT.hex[:4]}",
        excerpt=NAME["ru"],
        profile_id=TOPIC,
        deadline="2026-11-15T23:59:00+03:00",
    )
    assert coauthor.excerpt == NAME["en"]
    assert coauthor.ref_id is None
    # Проход по точке идёт под блокировкой своего ключа повтора.
    assert set(world.locks) == {key}


async def test__too_early_or_after_the_deadline__nothing() -> None:
    world = _World()

    early = await _run(world, DEADLINE - timedelta(days=3, minutes=1))
    late = await _run(world, DEADLINE + timedelta(minutes=1))

    assert (early, late) == (0, 0)
    assert world.sent == []


async def test__new_deadline__new_reminder_same_deadline_again__nothing() -> None:
    world = _World()
    await _run(world, DEADLINE - timedelta(days=2))
    moved = DEADLINE + timedelta(days=5)
    world.deadlines[(PROJECT, TOPIC)] = moved

    before_window = await _run(world, DEADLINE - timedelta(days=1))
    in_window = await _run(world, moved - timedelta(days=1))
    world.deadlines[(PROJECT, TOPIC)] = DEADLINE
    back = await _run(world, DEADLINE - timedelta(days=1))

    assert (before_window, in_window, back) == (0, 2, 0)
    assert [s.payload.deadline for s in world.sent] == [
        "2026-11-15T23:59:00+03:00",
        "2026-11-15T23:59:00+03:00",
        "2026-11-20T23:59:00+03:00",
        "2026-11-20T23:59:00+03:00",
    ]


async def test__package_built_for_the_deadline__no_reminder_early_draft_does_not_count() -> None:
    world = _World()
    world.builds[(PROJECT, TOPIC)] = [DEADLINE - timedelta(days=20)]
    now = DEADLINE - timedelta(days=2)

    with_draft = await _run(world, now)
    world.sent.clear()
    world.builds[(PROJECT, TOPIC)].append(now + timedelta(hours=1))
    world.deadlines[(PROJECT, TOPIC)] = DEADLINE + timedelta(minutes=1)

    packaged = await _run(world, now + timedelta(hours=2))

    assert (with_draft, packaged) == (2, 0)


async def test__author_added_later__gets_it_others_do_not_get_it_twice() -> None:
    world = _World()
    await _run(world, DEADLINE - timedelta(days=2))
    world.people[PROJECT].append(ReminderRecipient("newcomer", None))

    again = await _run(world, DEADLINE - timedelta(days=1))

    assert again == 1
    assert world.sent[-1].user_id == "newcomer"
    # Без языка аккаунта название точки по-русски.
    assert world.sent[-1].payload.excerpt == NAME["ru"]


async def test__one_broken_project__others_still_reminded() -> None:
    world = _World()
    world.deadlines[(OTHER, TOPIC)] = DEADLINE
    world.people[OTHER] = [ReminderRecipient("other-owner", "ru")]
    world.broken.add(PROJECT)

    sent = await _run(world, DEADLINE - timedelta(days=1))

    assert sent == 1
    assert [s.user_id for s in world.sent] == ["other-owner"]


async def test__days_setting__zero_disables_wider_window_reminds_earlier() -> None:
    world = _World()

    disabled = await _run(world, DEADLINE - timedelta(days=1), days=0)
    early = await _run(world, DEADLINE - timedelta(days=6), days=7)

    assert (disabled, early) == (0, 2)
