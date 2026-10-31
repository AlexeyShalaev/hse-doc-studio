"""In-memory реестр раннеров с теми же правилами, что у Postgres-репозиториев."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from hse_doc_studio.core.jobs.admin import (
    RUNNER_STATUS_ORDER,
    RegistrationTokenQuery,
    RunnerQuery,
    RunnerStatus,
    RunnerSummary,
    registration_token_status,
    runner_status,
    version_key,
)
from hse_doc_studio.core.jobs.runners import (
    RegistrationToken,
    Runner,
    RunnerAnnouncement,
    RunnerOwnerKind,
    RunnerPausedBy,
)
from hse_doc_studio.core.listing import Found, Picked, PickerItem, Window


class InMemoryRunnerRepository:
    def __init__(self) -> None:
        self._items: dict[str, Runner] = {}

    async def add(self, runner: Runner) -> None:
        self._items[runner.id] = runner

    async def get(self, runner_id: str) -> Runner | None:
        return self._items.get(runner_id)

    async def get_by_token_hash(self, token_hash: str) -> Runner | None:
        return next((r for r in self._items.values() if r.token_hash == token_hash), None)

    async def list(self) -> list[Runner]:
        return sorted(self._items.values(), key=lambda r: (r.created_at, r.id))

    def _replace(self, runner_id: str, *, only_active: bool = False, **changes: object) -> bool:
        runner = self._items.get(runner_id)
        if runner is None or (only_active and runner.revoked_at is not None):
            return False
        self._items[runner_id] = replace(runner, **changes)  # type: ignore[arg-type]
        return True

    async def set_token_hash(self, runner_id: str, token_hash: str) -> bool:
        return self._replace(runner_id, only_active=True, token_hash=token_hash)

    async def set_paused(self, runner_id: str, paused: bool, by: RunnerPausedBy | None = None) -> bool:
        return self._replace(runner_id, only_active=True, paused=paused, paused_by=by if paused else None)

    async def revoke(self, runner_id: str, now: datetime) -> bool:
        return self._replace(runner_id, revoked_at=now)

    async def touch(self, runner_id: str, now: datetime, version: str | None = None) -> None:
        self._replace(runner_id, last_seen_at=now, **({"version": version} if version else {}))

    async def list_owned(self, owner_id: str) -> list[Runner]:
        return [r for r in await self.list() if r.owner_kind is RunnerOwnerKind.user and r.owner_id == owner_id]

    async def rename(self, runner_id: str, name: str, now: datetime) -> bool:
        return self._replace(runner_id, only_active=True, name=name, renamed_at=now)

    async def apply_announcement(
        self, runner_id: str, info: RunnerAnnouncement, now: datetime, ip: str | None
    ) -> Runner | None:
        runner = self._items.get(runner_id)
        if runner is None or runner.revoked_at is not None:
            return None
        updated = replace(
            runner,
            version=info.version,
            tags=info.tags,
            concurrency=info.concurrency,
            ai_concurrency=info.ai_concurrency,
            host_kind=info.host_kind,
            features=info.features,
            ai_endpoints=info.ai_endpoints,
            last_seen_at=now,
            last_seen_ip=ip,
            offline_at=None,
            name=info.name if info.name is not None and runner.renamed_at is None else runner.name,
        )
        self._items[runner_id] = updated
        return updated

    async def mark_offline(self, runner_id: str, now: datetime) -> None:
        self._replace(runner_id, offline_at=now)

    async def count_active_owned(self, owner_id: str) -> int:
        return sum(1 for r in await self.list_owned(owner_id) if r.revoked_at is None)


class InMemoryRegistrationTokenRepository:
    def __init__(self) -> None:
        self._items: dict[str, RegistrationToken] = {}

    async def add(self, token: RegistrationToken) -> None:
        self._items[token.id] = token

    async def get(self, token_id: str) -> RegistrationToken | None:
        return self._items.get(token_id)

    async def list(self) -> list[RegistrationToken]:
        return sorted(self._items.values(), key=lambda t: (t.created_at, t.id), reverse=True)

    async def revoke(self, token_id: str, now: datetime) -> bool:
        token = self._items.get(token_id)
        if token is None or token.revoked_at is not None:
            return False
        self._items[token_id] = replace(token, revoked_at=now)
        return True

    async def consume(self, token_hash: str, now: datetime) -> RegistrationToken | None:
        token = next((t for t in self._items.values() if t.token_hash == token_hash), None)
        if token is None or not token.usable(now):
            return None
        used = replace(token, uses=token.uses + 1)
        self._items[token.id] = used
        return used

    async def list_owned(self, owner_id: str) -> list[RegistrationToken]:
        return [t for t in await self.list() if t.owner_kind is RunnerOwnerKind.user and t.owner_id == owner_id]

    async def revoke_owned(self, owner_id: str, now: datetime) -> int:
        count = 0
        for token in await self.list_owned(owner_id):
            if token.revoked_at is None:
                self._items[token.id] = replace(token, revoked_at=now)
                count += 1
        return count

    async def upsert_bootstrap(self, token: RegistrationToken) -> None:
        current = self._items.get(token.id)
        if current is None or current.token_hash != token.token_hash:
            self._items[token.id] = token


def _window[T](items: list[T], window: Window) -> Found[T]:
    return Found(items=list(items[window.offset : window.offset + window.limit]), total=len(items))


class InMemoryRunnerAdminReader:
    """IRunnerAdminReader поверх in-memory репозиториев: те же статусы, порядок упрощён до поля и id."""

    def __init__(self, runners: InMemoryRunnerRepository, tokens: InMemoryRegistrationTokenRepository) -> None:
        self._runners = runners
        self._tokens = tokens

    async def _newest(self) -> Runner | None:
        # Устарел ли раннер считается от флота установки: версии личных раннеров не в счёт.
        live = [
            r for r in await self._runners.list() if r.revoked_at is None and r.owner_kind is RunnerOwnerKind.instance
        ]
        return max(live, key=lambda r: version_key(r.version), default=None)

    async def list_runners(self, query: RunnerQuery, now: datetime) -> Found[Runner]:
        newest = await self._newest()

        def outdated(r: Runner) -> bool:
            return newest is not None and r.revoked_at is None and version_key(r.version) < version_key(newest.version)

        needle = (query.q or "").lower()
        found = [
            r
            for r in await self._runners.list()
            if (not needle or needle in f"{r.name} {r.version} {' '.join(sorted(r.tags))}".lower())
            and (not query.statuses or runner_status(r, now) in query.statuses)
            and (query.tag is None or query.tag in r.tags)
            and (query.resource_class is None or r.resource_class == query.resource_class)
            and (query.outdated is None or outdated(r) == query.outdated)
            and (query.owner_kind is None or r.owner_kind is query.owner_kind)
        ]
        keys: dict[str, Callable[[Runner], Any]] = {
            "name": lambda r: r.name.lower(),
            "status": lambda r: (RUNNER_STATUS_ORDER.index(runner_status(r, now)), r.name.lower()),
            "last_seen_at": lambda r: r.last_seen_at or datetime.min.replace(tzinfo=UTC),
            "created_at": lambda r: r.created_at,
            "version": lambda r: version_key(r.version),
            "owner_kind": lambda r: (r.owner_kind.value, r.name.lower()),
        }
        found.sort(key=lambda r: r.id)
        found.sort(key=keys[query.sort.field], reverse=query.sort.descending)
        return _window(found, query.window)

    async def summary(self, now: datetime) -> RunnerSummary:
        # Сводка только по раннерам установки: у личных раннеров людей своя сводка на экране.
        runners = [r for r in await self._runners.list() if r.owner_kind is RunnerOwnerKind.instance]
        newest = await self._newest()
        counts = {s: sum(1 for r in runners if runner_status(r, now) is s) for s in RunnerStatus}
        outdated = sum(
            1
            for r in runners
            if newest is not None and r.revoked_at is None and version_key(r.version) < version_key(newest.version)
        )
        return RunnerSummary(
            online=counts[RunnerStatus.online],
            paused=counts[RunnerStatus.paused],
            stale=counts[RunnerStatus.stale],
            offline=counts[RunnerStatus.offline],
            revoked=counts[RunnerStatus.revoked],
            outdated=outdated,
            newest_version=newest.version if newest else None,
        )

    async def list_tokens(self, query: RegistrationTokenQuery, now: datetime) -> Found[RegistrationToken]:
        needle = (query.q or "").lower()
        found = [
            t
            for t in await self._tokens.list()
            if (not needle or needle in t.label.lower())
            and (not query.statuses or registration_token_status(t, now) in query.statuses)
        ]
        keys: dict[str, Callable[[RegistrationToken], Any]] = {
            "created_at": lambda t: t.created_at,
            "expires_at": lambda t: t.expires_at or datetime.max.replace(tzinfo=UTC),
            "label": lambda t: t.label.lower(),
        }
        found.sort(key=lambda t: t.id)
        found.sort(key=keys[query.sort.field], reverse=query.sort.descending)
        return _window(found, query.window)

    async def pick(self, q: str | None, limit: int, *, item_id: str | None = None) -> Picked[PickerItem]:
        needle = (q or "").lower()
        found = [
            r for r in await self._runners.list() if needle in r.name.lower() and (item_id is None or r.id == item_id)
        ]
        found.sort(key=lambda r: (r.name.lower(), r.id))
        items = [
            PickerItem(kind="runner", id=r.id, name=r.name, detail=", ".join(sorted(r.tags)) or None)
            for r in found[:limit]
        ]
        return Picked(items=items, has_more=len(found) > limit)
