from __future__ import annotations

from dataclasses import dataclass

import pytest
from hse_doc_studio.core.identity.auth_settings import AuthEnvOverrides
from hse_doc_studio.core.identity.session_policy import SessionPolicy
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService, UpdateAuthSettingsUC
from hse_doc_studio.use_cases.identity.login import LoginUC
from hse_doc_studio.use_cases.server_setup.admin import CreateFirstAdminUC, EnsureBootstrapAdminUC
from hse_doc_studio.use_cases.server_setup.settings import ApplyInitialSettingsUC, CompleteSetupUC
from hse_doc_studio.use_cases.server_setup.state import GetSetupStatusUC, SetupStateService
from hse_doc_studio.use_cases.server_setup.token import SetupToken

from tests.fakes.auth import InMemoryAuditLog, InMemoryLoginAttemptRepository, InMemorySessionRepository
from tests.fakes.identity import (
    InMemoryCredentialRepository,
    InMemoryFirstAdminRepository,
    InMemoryIdentityStore,
    InMemoryInstanceSettingsRepository,
    InMemoryUserRepository,
)
from tests.unit.use_cases.identity.conftest import Clock, FakeHasher, FakeUow


class NoOidc:
    """Единый вход не подключён: пока так, пароль единственный способ войти."""

    def __init__(self, *, enabled: int = 0) -> None:
        self.enabled = enabled

    async def list(self, *, only_enabled: bool = False) -> list[object]:  # noqa: ARG002
        return [object()] * self.enabled


@dataclass
class SetupWorld:
    clock: Clock
    hasher: FakeHasher
    users: InMemoryUserRepository
    first_admin: InMemoryFirstAdminRepository
    creds: InMemoryCredentialRepository
    sessions: InMemorySessionRepository
    audit: InMemoryAuditLog
    settings: InMemoryInstanceSettingsRepository
    token: SetupToken
    env: AuthEnvOverrides
    oidc: NoOidc

    def state(self) -> SetupStateService:
        return SetupStateService(self.settings)

    def status_uc(self, state: SetupStateService | None = None) -> GetSetupStatusUC:
        return GetSetupStatusUC(state or self.state(), self.settings, self.users, self.token, self.env)

    def login_uc(self) -> LoginUC:
        return LoginUC(
            self.users, self.creds, self.sessions, InMemoryLoginAttemptRepository(), self.hasher, self.audit,
            FakeUow(), SessionPolicy(), self.clock,
        )  # fmt: skip

    def create_admin_uc(self, state: SetupStateService | None = None) -> CreateFirstAdminUC:
        return CreateFirstAdminUC(
            self.first_admin, self.hasher, self.login_uc(), self.token, state or self.state(), self.audit, self.clock
        )

    def bootstrap_uc(self, state: SetupStateService | None = None) -> EnsureBootstrapAdminUC:
        return EnsureBootstrapAdminUC(
            self.users, self.first_admin, self.hasher, state or self.state(), self.audit, self.env, self.clock
        )

    def settings_uc(self, state: SetupStateService | None = None) -> ApplyInitialSettingsUC:
        service = AuthSettingsService(self.settings, self.env)
        update = UpdateAuthSettingsUC(service, self.settings, self.audit)
        return ApplyInitialSettingsUC(service, update, self.oidc, state or self.state())

    def complete_uc(self, state: SetupStateService | None = None) -> CompleteSetupUC:
        return CompleteSetupUC(state or self.state(), self.audit)


def make_world(*, token_required: bool = True, env: AuthEnvOverrides | None = None) -> SetupWorld:
    store = InMemoryIdentityStore()
    return SetupWorld(
        clock=Clock(),
        hasher=FakeHasher(),
        users=InMemoryUserRepository(store),
        first_admin=InMemoryFirstAdminRepository(store),
        creds=InMemoryCredentialRepository(store),
        sessions=InMemorySessionRepository(),
        audit=InMemoryAuditLog(),
        settings=InMemoryInstanceSettingsRepository(),
        token=SetupToken(required=token_required, value="st_secret" if token_required else None),
        env=env or AuthEnvOverrides(),
        oidc=NoOidc(),
    )


@pytest.fixture
def world() -> SetupWorld:
    return make_world()
