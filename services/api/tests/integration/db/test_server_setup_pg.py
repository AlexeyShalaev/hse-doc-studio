"""Мастер первого запуска на настоящем Postgres: гонка двух админов и память о завершении."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from hse_doc_studio.core.identity.auth_settings import AuthEnvOverrides
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.session_policy import SessionPolicy
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.auth import SqlAuditLog, SqlLoginAttemptRepository, SqlSessionRepository
from hse_doc_studio.infra.db.repositories.identity import (
    SqlCredentialRepository,
    SqlFirstAdminRepository,
    SqlInstanceSettingsRepository,
    SqlUserRepository,
)
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.use_cases.identity.login import LoginUC
from hse_doc_studio.use_cases.server_setup.admin import CreateFirstAdminUC, EnsureBootstrapAdminUC
from hse_doc_studio.use_cases.server_setup.state import GetSetupStatusUC, SetupStateService
from hse_doc_studio.use_cases.server_setup.token import SetupToken

from tests.unit.use_cases.identity.conftest import FakeHasher, FakeUow

pytestmark = pytest.mark.pg

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

PASSWORD = "correct horse battery"


class _Stack:
    def __init__(self, engine: AsyncEngine, token: SetupToken) -> None:
        sessions = SessionProvider(create_sessionmaker(engine))
        self.users = SqlUserRepository(sessions)
        self.settings = SqlInstanceSettingsRepository(sessions)
        self.first_admin = SqlFirstAdminRepository(sessions)
        self.credentials = SqlCredentialRepository(sessions)
        self.audit = SqlAuditLog(sessions)
        self.hasher = FakeHasher()
        self.token = token
        self.state = SetupStateService(self.settings)
        login = LoginUC(
            self.users, self.credentials, SqlSessionRepository(sessions), SqlLoginAttemptRepository(sessions),
            self.hasher, self.audit, FakeUow(), SessionPolicy(),
        )  # fmt: skip
        self.create = CreateFirstAdminUC(self.first_admin, self.hasher, login, token, self.state, self.audit)

    def status(self) -> GetSetupStatusUC:
        return GetSetupStatusUC(self.state, self.settings, self.users, self.token, AuthEnvOverrides())


async def test__create_admin__parallel_requests__one_admin_in_the_database(pg_migrated_engine: AsyncEngine) -> None:
    stack = _Stack(pg_migrated_engine, SetupToken(required=True, value="st_pg"))

    outcomes = await asyncio.gather(
        *(
            stack.create.execute("st_pg", "Админ", f"admin{i}@example.org", PASSWORD, ip=None, user_agent="")
            for i in range(4)
        ),
        return_exceptions=True,
    )

    losers = [o for o in outcomes if isinstance(o, IdentityError)]
    assert len(losers) == 3
    assert {e.code for e in losers} == {IdentityErrorCode.setup_already_done}
    assert await stack.users.count() == 1


async def test__completion__is_stored_and_survives_a_new_process(pg_migrated_engine: AsyncEngine) -> None:
    stack = _Stack(pg_migrated_engine, SetupToken(required=False))
    await stack.create.execute(None, "Админ", "admin@example.org", PASSWORD, ip=None, user_agent="")
    assert (await stack.status().execute()).state == "needs_admin"

    await stack.state.mark_completed()

    restarted = _Stack(pg_migrated_engine, SetupToken(required=False))
    assert (await restarted.status().execute()).state == "ready"


async def test__bootstrap_admin__repeated_start__keeps_the_first_password(pg_migrated_engine: AsyncEngine) -> None:
    stack = _Stack(pg_migrated_engine, SetupToken(required=False))
    uc = EnsureBootstrapAdminUC(
        stack.users, stack.first_admin, stack.hasher, stack.state, stack.audit, AuthEnvOverrides()
    )

    first = await uc.execute("root@example.org", PASSWORD)
    admin = await stack.users.get_by_email("root@example.org")
    assert admin is not None
    stored = await stack.credentials.get_hash(admin.id)
    second = await uc.execute("root@example.org", "a completely different one")

    assert (first.outcome, second.outcome) == ("created", "exists")
    assert await stack.credentials.get_hash(admin.id) == stored
