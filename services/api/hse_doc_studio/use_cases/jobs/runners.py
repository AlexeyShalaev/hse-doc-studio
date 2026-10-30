"""Реестр раннеров: токены регистрации, регистрация, проверка токена раннера, ротация, отзыв, пауза."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import timedelta
from uuid import uuid4

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError, RunnerNotFoundError
from hse_doc_studio.core.jobs.runners import (
    BOOTSTRAP_TOKEN_ID,
    REGISTRATION_TOKEN_PREFIX,
    RUNNER_TOKEN_PREFIX,
    IRegistrationTokenRepository,
    IRunnerRepository,
    RegistrationToken,
    Runner,
    hash_runner_secret,
    new_runner_secret,
)
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION, RunnerRegisterRequest
from hse_doc_studio.core.uow import IUnitOfWork

logger = logging.getLogger(__name__)

DEFAULT_REGISTRATION_TTL = timedelta(days=1)
MAX_REGISTRATION_TTL = timedelta(days=30)
MAX_REGISTRATION_USES = 100
MAX_RUNNER_NAME = 128


@dataclass(frozen=True)
class CreatedRegistrationToken:
    token: RegistrationToken
    # Секрет виден только здесь, в БД лежит хеш.
    secret: str = field(repr=False)


@dataclass(frozen=True)
class RegisteredRunner:
    runner: Runner
    secret: str = field(repr=False)


def _require_admin(actor: Actor) -> str:
    if not actor.is_instance_admin or actor.id is None:
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor.id


class RunnerRegistry:
    def __init__(
        self,
        runners: IRunnerRepository,
        registration_tokens: IRegistrationTokenRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._runners = runners
        self._tokens = registration_tokens
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def create_registration_token(
        self,
        actor: Actor,
        *,
        label: str = "",
        ttl: timedelta = DEFAULT_REGISTRATION_TTL,
        max_uses: int = 1,
    ) -> CreatedRegistrationToken:
        creator = _require_admin(actor)
        if not timedelta(0) < ttl <= MAX_REGISTRATION_TTL or not 1 <= max_uses <= MAX_REGISTRATION_USES:
            raise ValueError("срок или число использований токена регистрации вне допустимого")
        now = self._clock()
        secret = new_runner_secret(REGISTRATION_TOKEN_PREFIX)
        token = RegistrationToken(
            id=uuid4().hex,
            token_hash=hash_runner_secret(secret),
            created_by=creator,
            created_at=now,
            expires_at=now + ttl,
            max_uses=max_uses,
            label=label.strip()[:MAX_RUNNER_NAME],
        )
        async with self._uow.begin():
            await self._tokens.add(token)
            await self._audit.record(
                "runner.registration_token_create",
                actor_id=creator,
                target=token.id,
                details={"max_uses": max_uses, "label": token.label},
            )
        return CreatedRegistrationToken(token=token, secret=secret)

    async def revoke_registration_token(self, actor: Actor, token_id: str) -> None:
        creator = _require_admin(actor)
        async with self._uow.begin():
            if not await self._tokens.revoke(token_id, self._clock()):
                raise RunnerNotFoundError("registration token not found")
            await self._audit.record("runner.registration_token_revoke", actor_id=creator, target=token_id)

    async def ensure_bootstrap_token(self, secret: str) -> None:
        """Токен первого раннера из окружения: одноразовый, не оживает после использования."""
        now = self._clock()
        await self._tokens.upsert_bootstrap(
            RegistrationToken(
                id=BOOTSTRAP_TOKEN_ID,
                token_hash=hash_runner_secret(secret),
                created_by=None,
                created_at=now,
                expires_at=None,
                max_uses=1,
                label="bootstrap",
            )
        )
        logger.warning(
            "Задан токен раннера из окружения (bootstrap). После регистрации первого раннера уберите его из окружения."
        )

    async def register(self, registration_secret: str, request: RunnerRegisterRequest) -> RegisteredRunner:
        """Раннер представляется токеном регистрации и получает постоянный токен; токен регистрации тратится."""
        if request.protocol != RUNNER_PROTOCOL_VERSION:
            raise RunnerAuthError(
                RunnerErrorCode.runner_protocol_unsupported,
                f"server speaks runner protocol {RUNNER_PROTOCOL_VERSION}, runner sent {request.protocol}",
            )
        now = self._clock()
        secret = new_runner_secret(RUNNER_TOKEN_PREFIX)
        # Списание токена, раннер и аудит одной транзакцией: сбой не сжигает токен регистрации впустую.
        async with self._uow.begin():
            consumed = await self._tokens.consume(hash_runner_secret(registration_secret), now)
            if consumed is None:
                raise RunnerAuthError(RunnerErrorCode.runner_unauthorized)
            runner = Runner(
                id=uuid4().hex,
                name=request.name.strip()[:MAX_RUNNER_NAME] or "runner",
                token_hash=hash_runner_secret(secret),
                tags=request.tags,
                concurrency=request.concurrency,
                resource_class=request.resource_class,
                version=request.version,
                created_at=now,
                created_by=consumed.created_by,
                last_seen_at=now,
                owner_kind=consumed.owner_kind,
                owner_id=consumed.owner_id,
            )
            await self._runners.add(runner)
            await self._audit.record(
                "runner.register",
                actor_id=consumed.created_by,
                target=runner.id,
                details={"registration_token": consumed.id, "name": runner.name, "tags": sorted(runner.tags)},
            )
        return RegisteredRunner(runner=runner, secret=secret)

    async def authenticate(self, runner_secret: str) -> Runner:
        """Раннер по токену; неизвестный и отозванный токен дают один и тот же отказ."""
        runner = await self._runners.get_by_token_hash(hash_runner_secret(runner_secret))
        if runner is None:
            raise RunnerAuthError(RunnerErrorCode.runner_unauthorized)
        if runner.revoked_at is not None:
            raise RunnerAuthError(RunnerErrorCode.runner_unauthorized)
        return runner

    async def rotate_token(self, actor: Actor, runner_id: str) -> RegisteredRunner:
        creator = _require_admin(actor)
        runner = await self._runners.get(runner_id)
        if runner is None or runner.revoked_at is not None:
            raise RunnerNotFoundError("runner not found")
        secret = new_runner_secret(RUNNER_TOKEN_PREFIX)
        token_hash = hash_runner_secret(secret)
        async with self._uow.begin():
            await self._runners.set_token_hash(runner_id, token_hash)
            await self._audit.record("runner.token_rotate", actor_id=creator, target=runner_id)
        return RegisteredRunner(runner=replace(runner, token_hash=token_hash), secret=secret)

    async def revoke(self, actor: Actor, runner_id: str) -> None:
        creator = _require_admin(actor)
        async with self._uow.begin():
            if not await self._runners.revoke(runner_id, self._clock()):
                raise RunnerNotFoundError("runner not found")
            await self._audit.record("runner.revoke", actor_id=creator, target=runner_id)

    async def set_paused(self, actor: Actor, runner_id: str, paused: bool) -> None:
        creator = _require_admin(actor)
        async with self._uow.begin():
            if not await self._runners.set_paused(runner_id, paused):
                raise RunnerNotFoundError("runner not found")
            await self._audit.record("runner.pause" if paused else "runner.resume", actor_id=creator, target=runner_id)
