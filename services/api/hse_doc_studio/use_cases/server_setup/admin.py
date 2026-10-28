"""Первый администратор: из мастера (с токеном установки) или из окружения при старте."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from hse_doc_studio.core.identity.auth_settings import AuthEnvOverrides
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.passwords import check_password
from hse_doc_studio.core.identity.protocols import IAuditLog, IFirstAdminRepository, IPasswordHasher, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.use_cases.identity.login import LoginResult, LoginUC
from hse_doc_studio.use_cases.server_setup.state import SetupStateService
from hse_doc_studio.use_cases.server_setup.token import SetupToken


def _first_admin(email: str, name: str, now: datetime) -> User:
    normalized = normalize_email(email)
    return User(
        id=uuid.uuid4().hex,
        email=email.strip(),
        email_normalized=normalized,
        name=name.strip() or normalized.partition("@")[0],
        status=UserStatus.active,
        created_at=now,
        # Адрес назвал оператор установки: подтверждать письмом нечего.
        email_verified=True,
        is_instance_admin=True,
    )


class CreateFirstAdminUC:
    def __init__(
        self,
        first_admin: IFirstAdminRepository,
        hasher: IPasswordHasher,
        login: LoginUC,
        token: SetupToken,
        state: SetupStateService,
        audit: IAuditLog,
        clock: Clock = utc_now,
    ) -> None:
        self._first_admin = first_admin
        self._hasher = hasher
        self._login = login
        self._token = token
        self._state = state
        self._audit = audit
        self._clock = clock

    async def execute(
        self, setup_token: str | None, name: str, email: str, password: str, *, ip: str | None, user_agent: str
    ) -> LoginResult:
        """Ровно один вызов станет админом: остальные (в том числе параллельные) получат `setup_already_done`.
        Админ сразу входит: мастер продолжается его сессией."""
        if await self._state.is_completed():
            raise IdentityError(IdentityErrorCode.setup_already_done)
        if not self._token.verify(setup_token):
            raise IdentityError(IdentityErrorCode.setup_token_invalid)
        check_password(password, email)
        user = _first_admin(email, name, self._clock())
        await self._first_admin.create_first_admin(user, self._hasher.hash(password))
        self._token.revoke()
        await self._audit.record("setup.admin_created", actor_id=user.id, details={"ip": ip})
        return await self._login.execute(email, password, ip=ip, user_agent=user_agent)


BootstrapOutcome = Literal["created", "exists"]


@dataclass(frozen=True)
class BootstrapAdminResult:
    outcome: BootstrapOutcome
    # Окружение задало и админа, и режим регистрации: выбирать в мастере нечего, он закрыт сам.
    wizard_completed: bool


class EnsureBootstrapAdminUC:
    """Администратор из окружения при старте. Идемпотентно: существующего админа и его пароль не трогает."""

    def __init__(
        self,
        users: IUserRepository,
        first_admin: IFirstAdminRepository,
        hasher: IPasswordHasher,
        state: SetupStateService,
        audit: IAuditLog,
        env: AuthEnvOverrides,
        clock: Clock = utc_now,
    ) -> None:
        self._users = users
        self._first_admin = first_admin
        self._hasher = hasher
        self._state = state
        self._audit = audit
        self._env = env
        self._clock = clock

    async def execute(self, email: str, password: str, name: str = "") -> BootstrapAdminResult:
        outcome: BootstrapOutcome = "exists"
        if await self._users.count() == 0:
            check_password(password, email)
            user = _first_admin(email, name, self._clock())
            try:
                await self._first_admin.create_first_admin(user, self._hasher.hash(password))
            except IdentityError as error:
                if error.code is not IdentityErrorCode.setup_already_done:
                    raise
            else:
                outcome = "created"
                await self._audit.record("setup.admin_bootstrapped", actor_id=user.id, details={"source": "env"})
        completed = self._env.registration_mode is not None
        if completed and not await self._state.is_completed():
            await self._state.mark_completed()
            await self._audit.record("setup.completed", actor_id=None, details={"source": "env"})
        return BootstrapAdminResult(outcome, completed)
