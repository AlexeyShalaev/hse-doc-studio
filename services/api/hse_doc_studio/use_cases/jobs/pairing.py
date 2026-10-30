"""Сопряжение раннера по коду устройства: начало, опрос устройства, подтверждение человеком на сайте."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError
from hse_doc_studio.core.jobs.pairing import (
    PAIRING_INTERVAL_S,
    PAIRING_KEEP,
    PAIRING_TTL,
    IRunnerPairingRepository,
    PairingStatus,
    RunnerPairing,
    new_device_code,
    new_user_code,
    normalize_user_code,
)
from hse_doc_studio.core.jobs.runners import RunnerHostKind, hash_runner_secret
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry

# Опрос немного чаще объявленного интервала прощается: часы устройства и сети неточны.
_POLL_SLACK_S = 0.5
_MAX_USER_CODE_ATTEMPTS = 5


@dataclass(frozen=True)
class PairingStarted:
    device_code: str = field(repr=False)
    user_code: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class PairingPoll:
    status: PairingStatus
    registration_token: str | None = field(default=None, repr=False)


def _aad(pairing_id: str) -> str:
    return column_aad("runner_pairings", "token_secret_enc", pairing_id)


class RunnerPairingService:
    def __init__(  # noqa: PLR0913
        self,
        pairings: IRunnerPairingRepository,
        registry: RunnerRegistry,
        cipher: ISecretCipher,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        clock: Clock = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._pairings = pairings
        self._registry = registry
        self._cipher = cipher
        self._audit = audit
        self._uow = uow
        self._clock = clock
        self._monotonic = monotonic
        # Последний опрос устройства: одна реплика api, памяти процесса достаточно (как у ограничителя частоты).
        self._last_poll: dict[str, float] = {}

    async def start(self, name: str, host_kind: RunnerHostKind, client_ip: str | None) -> PairingStarted:
        if not (await self._registry.personal_settings()).enabled:
            raise RunnerAuthError(RunnerErrorCode.runner_disabled, "personal runners are turned off")
        now = self._clock()
        device_code = new_device_code()
        for _ in range(_MAX_USER_CODE_ATTEMPTS):
            user_code = new_user_code()
            if await self._pairings.get_by_user_code(user_code) is None:
                break
        else:
            raise RuntimeError("could not allocate a free user code")
        await self._pairings.add(
            RunnerPairing(
                id=uuid4().hex,
                device_code_hash=hash_runner_secret(device_code),
                user_code=user_code,
                name=" ".join(name.split())[:128] or "runner",
                host_kind=host_kind,
                client_ip=client_ip,
                status=PairingStatus.pending,
                created_at=now,
                expires_at=now + PAIRING_TTL,
            )
        )
        return PairingStarted(
            device_code=device_code,
            user_code=user_code,
            expires_in=int(PAIRING_TTL.total_seconds()),
            interval=PAIRING_INTERVAL_S,
        )

    async def poll(self, device_code: str) -> PairingPoll:
        """Токен регистрации приходит ровно один раз; опрос чаще интервала даёт `slow_down`."""
        pairing = await self._pairings.get_by_device_hash(hash_runner_secret(device_code))
        if pairing is None:
            return PairingPoll(PairingStatus.expired)
        self._check_interval(pairing.id)
        if pairing.status is PairingStatus.approved and pairing.token_secret_enc is not None:
            secret = self._cipher.decrypt(pairing.token_secret_enc, aad=_aad(pairing.id)).reveal()
            if await self._pairings.deliver(pairing.id):
                self._last_poll.pop(pairing.id, None)
                return PairingPoll(PairingStatus.approved, registration_token=secret)
            return PairingPoll(PairingStatus.expired)
        return PairingPoll(self._device_status(pairing))

    def _check_interval(self, pairing_id: str) -> None:
        tick = self._monotonic()
        last = self._last_poll.get(pairing_id)
        if last is not None and tick - last < PAIRING_INTERVAL_S - _POLL_SLACK_S:
            raise RunnerAuthError(RunnerErrorCode.slow_down, f"poll at most every {PAIRING_INTERVAL_S} s")
        self._last_poll[pairing_id] = tick

    def _device_status(self, pairing: RunnerPairing) -> PairingStatus:
        """Что видит устройство без выдачи токена: ждёт, отклонено или всё (истекло или уже выдано)."""
        if pairing.status is PairingStatus.pending and not pairing.expired_at(self._clock()):
            return PairingStatus.pending
        if pairing.status is PairingStatus.denied:
            return PairingStatus.denied
        return PairingStatus.expired

    async def info(self, actor: Actor, user_code: str) -> RunnerPairing:
        """Что подтверждает человек; решённое чужим сопряжение для него не существует."""
        owner = self._owner(actor)
        pairing = await self._find(user_code)
        if pairing.status is not PairingStatus.pending and pairing.user_id != owner:
            raise IdentityError(IdentityErrorCode.runner_pairing_invalid)
        if pairing.status is PairingStatus.pending and pairing.expired_at(self._clock()):
            raise IdentityError(IdentityErrorCode.runner_pairing_expired)
        return self._view(pairing)

    async def decide(self, actor: Actor, user_code: str, *, approve: bool) -> RunnerPairing:
        owner = self._owner(actor)
        pairing = await self._find(user_code)
        now = self._clock()
        if pairing.status is not PairingStatus.pending:
            raise IdentityError(IdentityErrorCode.runner_pairing_used)
        if pairing.expired_at(now):
            raise IdentityError(IdentityErrorCode.runner_pairing_expired)
        if not approve:
            async with self._uow.begin():
                if not await self._pairings.decide(pairing.id, PairingStatus.denied, user_id=owner, now=now):
                    raise IdentityError(IdentityErrorCode.runner_pairing_used)
                await self._audit.record("runner.pairing_deny", actor_id=owner, target=pairing.id)
            return self._view(await self._find(user_code))
        async with self._uow.begin():
            created = await self._registry.create_pairing_token(owner, label=pairing.name)
            secret_enc = self._cipher.encrypt(Secret(created.secret), aad=_aad(pairing.id))
            decided = await self._pairings.decide(
                pairing.id,
                PairingStatus.approved,
                user_id=owner,
                now=now,
                token_id=created.token.id,
                token_secret_enc=secret_enc,
            )
            if not decided:
                raise IdentityError(IdentityErrorCode.runner_pairing_used)
            await self._audit.record(
                "runner.pairing_approve",
                actor_id=owner,
                target=pairing.id,
                details={"name": pairing.name, "host_kind": pairing.host_kind.value, "client_ip": pairing.client_ip},
            )
        return self._view(await self._find(user_code))

    async def purge(self) -> int:
        return await self._pairings.purge(self._clock() - PAIRING_KEEP)

    @staticmethod
    def _owner(actor: Actor) -> str:
        if actor.id is None:
            raise IdentityError(IdentityErrorCode.auth_required)
        return actor.id

    async def _find(self, user_code: str) -> RunnerPairing:
        code = normalize_user_code(user_code)
        pairing = await self._pairings.get_by_user_code(code) if code is not None else None
        if pairing is None:
            raise IdentityError(IdentityErrorCode.runner_pairing_invalid)
        return pairing

    def _view(self, pairing: RunnerPairing) -> RunnerPairing:
        """Ожидающее сопряжение после срока показывается истёкшим; секрет наружу не уходит."""
        status = pairing.status
        if status is PairingStatus.pending and pairing.expired_at(self._clock()):
            status = PairingStatus.expired
        if status is PairingStatus.delivered:
            status = PairingStatus.approved
        return RunnerPairing(
            id=pairing.id,
            device_code_hash="",
            user_code=pairing.user_code,
            name=pairing.name,
            host_kind=pairing.host_kind,
            client_ip=pairing.client_ip,
            status=status,
            created_at=pairing.created_at,
            expires_at=pairing.expires_at,
            user_id=pairing.user_id,
            decided_at=pairing.decided_at,
        )
