from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.session_policy import SessionPolicy
from hse_doc_studio.use_cases.identity.change_password import ChangePasswordUC
from hse_doc_studio.use_cases.identity.login import LoginUC
from hse_doc_studio.use_cases.identity.sessions import SessionService

from tests.fakes.auth import InMemoryAuditLog, InMemoryLoginAttemptRepository, InMemorySessionRepository
from tests.fakes.identity import (
    InMemoryCredentialRepository,
    InMemoryIdentityStore,
    InMemoryUserRepository,
)

T0 = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


class FakeHasher:
    """Считает вызовы: по ним проверяется, что неизвестный e-mail стоит столько же, сколько известный."""

    def __init__(self) -> None:
        self.hash_calls = 0
        self.verify_calls = 0
        self.stale_prefix = "v2"

    def hash(self, password: str) -> str:
        self.hash_calls += 1
        return f"{self.stale_prefix}:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        self.verify_calls += 1
        return password_hash == f"{password_hash.split(':', 1)[0]}:{password}"

    def needs_rehash(self, password_hash: str) -> bool:
        return not password_hash.startswith(f"{self.stale_prefix}:")


class FakeUow:
    def __init__(self) -> None:
        self.begins = 0

    @asynccontextmanager
    async def begin(self):  # type: ignore[no-untyped-def]
        self.begins += 1
        yield


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


@dataclass
class World:
    clock: Clock
    hasher: FakeHasher
    store: InMemoryIdentityStore
    users: InMemoryUserRepository
    creds: InMemoryCredentialRepository
    sessions: InMemorySessionRepository
    attempts: InMemoryLoginAttemptRepository
    audit: InMemoryAuditLog
    uow: FakeUow
    policy: SessionPolicy

    def login_uc(self) -> LoginUC:
        return LoginUC(
            self.users, self.creds, self.sessions, self.attempts, self.hasher, self.audit, self.uow,
            self.policy, self.clock,
        )  # fmt: skip

    def service(self) -> SessionService:
        return SessionService(self.sessions, self.users, self.policy, self.clock)

    def change_uc(self) -> ChangePasswordUC:
        return ChangePasswordUC(self.users, self.creds, self.sessions, self.hasher, self.audit, self.uow)

    async def add_user(
        self, email: str = "ann@example.org", password: str = "correct horse battery", *,
        status: UserStatus = UserStatus.active, user_id: str = "u1",
    ) -> User:  # fmt: skip
        user = User(
            id=user_id, email=email, email_normalized=normalize_email(email), name="Ann", status=status,
            created_at=T0, email_verified=True,
        )  # fmt: skip
        await self.users.add(user)
        await self.creds.set_hash(user.id, self.hasher.hash(password))
        return replace(user)


@pytest.fixture
def world() -> World:
    store = InMemoryIdentityStore()
    return World(
        clock=Clock(),
        hasher=FakeHasher(),
        store=store,
        users=InMemoryUserRepository(store),
        creds=InMemoryCredentialRepository(store),
        sessions=InMemorySessionRepository(),
        attempts=InMemoryLoginAttemptRepository(),
        audit=InMemoryAuditLog(),
        uow=FakeUow(),
        policy=SessionPolicy(),
    )
