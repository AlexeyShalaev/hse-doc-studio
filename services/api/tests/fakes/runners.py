"""In-memory реестр раннеров с теми же правилами, что у Postgres-репозиториев."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from hse_doc_studio.core.jobs.runners import RegistrationToken, Runner, RunnerAnnouncement, RunnerOwnerKind


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

    async def set_paused(self, runner_id: str, paused: bool) -> bool:
        return self._replace(runner_id, only_active=True, paused=paused)

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
