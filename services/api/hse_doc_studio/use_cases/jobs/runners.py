"""Реестр раннеров: токены регистрации, регистрация, проверка токена раннера, ротация, отзыв, пауза."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import timedelta
from uuid import UUID, uuid4

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.enums import JobState, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError, RunnerNotFoundError
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.relay import RELAY_KEEPALIVE_S, RelayErrorCode
from hse_doc_studio.core.jobs.routing import IPersonalRunnerSettings, PersonalRunnerSettings, RunnerScope
from hse_doc_studio.core.jobs.runners import (
    BOOTSTRAP_TOKEN_ID,
    REGISTRATION_TOKEN_PREFIX,
    RUNNER_TOKEN_PREFIX,
    IRegistrationTokenRepository,
    IRunnerRepository,
    RegistrationToken,
    RegistrationTokenPurpose,
    Runner,
    RunnerAnnouncement,
    RunnerOwnerKind,
    RunnerPausedBy,
    hash_runner_secret,
    new_runner_secret,
)
from hse_doc_studio.core.jobs.wire import (
    RUNNER_PROTOCOL_VERSION,
    SERVER_FEATURES,
    RunnerAnnounceRequest,
    RunnerAnnounceResponse,
    RunnerRegisterRequest,
)
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService

logger = logging.getLogger(__name__)

DEFAULT_REGISTRATION_TTL = timedelta(days=1)
MAX_REGISTRATION_TTL = timedelta(days=30)
MAX_REGISTRATION_USES = 100
MAX_RUNNER_NAME = 128
# Личные токены регистрации: срок до недели, не больше пяти неиспользованных, в списке неделю после истечения.
MAX_PERSONAL_TOKEN_TTL = timedelta(hours=168)
MAX_UNUSED_PERSONAL_TOKENS = 5
PERSONAL_TOKEN_LIST_KEEP = timedelta(days=7)
# Отозванные личные раннеры видны хозяину ещё месяц.
REVOKED_RUNNER_LIST_KEEP = timedelta(days=30)
PAIRING_TOKEN_TTL = timedelta(minutes=10)


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


def _require_user(actor: Actor) -> str:
    if actor.id is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor.id


class RunnerRegistry:
    def __init__(  # noqa: PLR0913
        self,
        runners: IRunnerRepository,
        registration_tokens: IRegistrationTokenRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        clock: Clock = utc_now,
        personal: IPersonalRunnerSettings | None = None,
        users: IUserRepository | None = None,
        queue: JobQueueService | None = None,
        jobs: IJobQueue | None = None,
    ) -> None:
        self._runners = runners
        self._tokens = registration_tokens
        self._audit = audit
        self._uow = uow
        self._clock = clock
        self._personal = personal
        self._users = users
        self._queue = queue
        self._jobs = jobs

    async def personal_settings(self) -> PersonalRunnerSettings:
        return await self._personal.current() if self._personal is not None else PersonalRunnerSettings()

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

    async def list_registration_tokens(self, actor: Actor) -> list[RegistrationToken]:
        """Токены установки; личные токены людей админ здесь не видит."""
        _require_admin(actor)
        return [t for t in await self._tokens.list() if t.owner_kind is RunnerOwnerKind.instance]

    async def revoke_registration_token(self, actor: Actor, token_id: str) -> None:
        creator = _require_admin(actor)
        async with self._uow.begin():
            if not await self._tokens.revoke(token_id, self._clock()):
                raise RunnerNotFoundError("registration token not found")
            token = await self._tokens.get(token_id)
            if token is not None and token.owner_kind is not RunnerOwnerKind.instance:
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
            if consumed.owner_kind is RunnerOwnerKind.user:
                # Отказ внутри транзакции откатывает и списание токена: человек может повторить позже.
                await self._check_personal_registration(consumed)
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
                details={
                    "registration_token": consumed.id,
                    "name": runner.name,
                    "tags": sorted(runner.tags),
                    "owner_kind": runner.owner_kind.value,
                    "owner_id": runner.owner_id,
                    "host_kind": runner.host_kind.value,
                },
            )
        return RegisteredRunner(runner=runner, secret=secret)

    async def _check_personal_registration(self, token: RegistrationToken) -> None:
        settings = await self.personal_settings()
        if not settings.enabled or token.owner_id is None or not await self._owner_active(token.owner_id):
            raise RunnerAuthError(RunnerErrorCode.runner_disabled, "personal runners are not available")
        if await self._runners.count_active_owned(token.owner_id) >= settings.max_per_user:
            raise RunnerAuthError(RunnerErrorCode.runner_limit, f"at most {settings.max_per_user} personal runners")

    async def _owner_active(self, owner_id: str) -> bool:
        if self._users is None:
            return True
        user = await self._users.get(owner_id)
        return user is not None and user.can_sign_in

    async def authenticate(self, runner_secret: str) -> Runner:
        """Раннер по токену; неизвестный и отозванный токен дают один и тот же отказ.

        Личный раннер отключённого человека или при выключенных личных раннерах получает `runner_disabled`.
        """
        runner = await self._runners.get_by_token_hash(hash_runner_secret(runner_secret))
        if runner is None:
            raise RunnerAuthError(RunnerErrorCode.runner_unauthorized)
        if runner.revoked_at is not None:
            raise RunnerAuthError(RunnerErrorCode.runner_unauthorized)
        if runner.scope is RunnerScope.personal:
            if not (await self.personal_settings()).enabled:
                await self._gone(runner)
                raise RunnerAuthError(RunnerErrorCode.runner_disabled, "personal runners are turned off")
            if runner.owner_id is None or not await self._owner_active(runner.owner_id):
                await self._gone(runner)
                raise RunnerAuthError(RunnerErrorCode.runner_disabled, "the runner owner is disabled")
        return runner

    async def _gone(self, runner: Runner) -> None:
        """`runner_disabled` для раннера фатален: CLI-раннер завершается, Студия ждёт минуты.

        Без пометки «ушёл» раннер после включения личных раннеров ещё минуту числился бы в сети по
        последнему опросу, и сборки ждали бы мёртвый раннер окно ожидания, а не шли сразу на общие.
        Следующий успешный опрос пометку снимает, как после `/offline`.
        """
        if runner.offline_at is None or (runner.last_seen_at is not None and runner.offline_at < runner.last_seen_at):
            await self._runners.mark_offline(runner.id, self._clock())

    # --- протокол: согласование, уход, самоотзыв ---

    async def announce(self, runner: Runner, request: RunnerAnnounceRequest, ip: str | None) -> RunnerAnnounceResponse:
        """Сервер запоминает пересечение возможностей: ничего нового раннеру не шлёт, пока он это не объявил."""
        features = request.features & SERVER_FEATURES
        name = request.name.strip()[:MAX_RUNNER_NAME] if request.name else None
        updated = await self._runners.apply_announcement(
            runner.id,
            RunnerAnnouncement(
                name=name or None,
                version=request.version,
                tags=request.tags,
                concurrency=request.concurrency,
                ai_concurrency=request.ai_concurrency,
                host_kind=request.host_kind,
                features=features,
                ai_endpoints=request.ai_endpoints,
            ),
            self._clock(),
            ip,
        )
        if updated is None:
            raise RunnerAuthError(RunnerErrorCode.runner_unauthorized)
        changes = _announcement_changes(runner, updated)
        if changes:
            # Украденный токен мог бы тихо объявить другие ИИ-адреса: смена того, что раннер умеет, в журнале.
            await self._audit.record(
                "runner.announce",
                actor_id=runner.owner_id,
                target=runner.id,
                details={**_owner_details(runner), **changes},
            )
        return RunnerAnnounceResponse(
            runner_id=updated.id,
            server_features=features,
            owner_kind=updated.owner_kind,
            paused=updated.paused,
            relay_keepalive_s=RELAY_KEEPALIVE_S,
        )

    async def go_offline(self, runner: Runner) -> None:
        """Мягкая остановка: ждущие этот раннер сборки сразу идут на общие, если других раннеров хозяина нет."""
        await self._runners.mark_offline(runner.id, self._clock())
        await self._after_runner_left(runner, cancel_relays=False)

    async def deregister(self, runner: Runner) -> None:
        async with self._uow.begin():
            await self._runners.revoke(runner.id, self._clock())
            await self._audit.record(
                "runner.deregister", actor_id=runner.owner_id, target=runner.id, details=_owner_details(runner)
            )
        await self._after_runner_left(runner, cancel_relays=True)

    async def _after_runner_left(self, runner: Runner, *, cancel_relays: bool) -> None:
        if runner.scope is not RunnerScope.personal or self._queue is None:
            return
        if cancel_relays:
            await self._queue.cancel_pinned(
                runner_id=UUID(runner.id), error_code=RelayErrorCode.relay_unavailable.value
            )
        if runner.owner_id is None:
            return
        now = self._clock()
        others_online = any(
            other.id != runner.id and runner_status(other, now) is RunnerStatus.online
            for other in await self._runners.list_owned(runner.owner_id)
        )
        if not others_online:
            await self._queue.expire_personal_wait(owner_id=runner.owner_id)

    # --- аккаунт: свои раннеры и личные токены ---

    async def create_personal_token(
        self, actor: Actor, *, label: str = "", ttl: timedelta = DEFAULT_REGISTRATION_TTL
    ) -> CreatedRegistrationToken:
        owner = _require_user(actor)
        if not timedelta(0) < ttl <= MAX_PERSONAL_TOKEN_TTL:
            raise ValueError("срок личного токена регистрации вне допустимого")
        if not (await self.personal_settings()).enabled:
            raise IdentityError(IdentityErrorCode.personal_runners_disabled)
        now = self._clock()
        unused = [
            t
            for t in await self._tokens.list_owned(owner)
            if t.purpose is RegistrationTokenPurpose.manual and t.usable(now)
        ]
        if len(unused) >= MAX_UNUSED_PERSONAL_TOKENS:
            raise IdentityError(IdentityErrorCode.personal_runner_limit)
        secret = new_runner_secret(REGISTRATION_TOKEN_PREFIX)
        token = RegistrationToken(
            id=uuid4().hex,
            token_hash=hash_runner_secret(secret),
            created_by=owner,
            created_at=now,
            expires_at=now + ttl,
            max_uses=1,
            label=label.strip()[:MAX_RUNNER_NAME],
            owner_kind=RunnerOwnerKind.user,
            owner_id=owner,
        )
        async with self._uow.begin():
            await self._tokens.add(token)
            await self._audit.record(
                "runner.personal_token_create", actor_id=owner, target=token.id, details={"label": token.label}
            )
        return CreatedRegistrationToken(token=token, secret=secret)

    async def create_pairing_token(self, owner: str, *, label: str) -> CreatedRegistrationToken:
        """Токен для устройства, подтверждённого кодом: одно использование, срок как у кода; транзакция вызывающего."""
        settings = await self.personal_settings()
        if not settings.enabled:
            raise IdentityError(IdentityErrorCode.personal_runners_disabled)
        if await self._runners.count_active_owned(owner) >= settings.max_per_user:
            raise IdentityError(IdentityErrorCode.personal_runner_limit)
        now = self._clock()
        secret = new_runner_secret(REGISTRATION_TOKEN_PREFIX)
        token = RegistrationToken(
            id=uuid4().hex,
            token_hash=hash_runner_secret(secret),
            created_by=owner,
            created_at=now,
            expires_at=now + PAIRING_TOKEN_TTL,
            max_uses=1,
            label=label.strip()[:MAX_RUNNER_NAME],
            owner_kind=RunnerOwnerKind.user,
            owner_id=owner,
            purpose=RegistrationTokenPurpose.pairing,
        )
        await self._tokens.add(token)
        return CreatedRegistrationToken(token=token, secret=secret)

    async def list_personal_tokens(self, actor: Actor) -> list[RegistrationToken]:
        owner = _require_user(actor)
        horizon = self._clock() - PERSONAL_TOKEN_LIST_KEEP
        return [
            t
            for t in await self._tokens.list_owned(owner)
            if t.purpose is RegistrationTokenPurpose.manual and (t.expires_at is None or t.expires_at > horizon)
        ]

    async def revoke_personal_token(self, actor: Actor, token_id: str) -> None:
        owner = _require_user(actor)
        token = await self._tokens.get(token_id)
        if token is None or token.owner_kind is not RunnerOwnerKind.user or token.owner_id != owner:
            raise RunnerNotFoundError("registration token not found")
        async with self._uow.begin():
            await self._tokens.revoke(token_id, self._clock())
            await self._audit.record("runner.personal_token_revoke", actor_id=owner, target=token_id)

    async def list_my_runners(self, actor: Actor) -> list[Runner]:
        owner = _require_user(actor)
        horizon = self._clock() - REVOKED_RUNNER_LIST_KEEP
        return [r for r in await self._runners.list_owned(owner) if r.revoked_at is None or r.revoked_at > horizon]

    async def running_jobs(self, runner_ids: set[str]) -> dict[str, int]:
        """Сколько задач идёт на каждом из раннеров (для списка «Мои раннеры» и админки)."""
        counts = dict.fromkeys(runner_ids, 0)
        if self._jobs is None or not runner_ids:
            return counts
        for job in await self._jobs.list(state=JobState.running):
            key = job.runner_id.hex if job.runner_id is not None else None
            if key in counts:
                counts[key] += 1
        return counts

    async def my_runner(self, actor: Actor, runner_id: str) -> Runner:
        """Чужой раннер неотличим от несуществующего."""
        owner = _require_user(actor)
        runner = await self._runners.get(runner_id)
        if runner is None or runner.owner_kind is not RunnerOwnerKind.user or runner.owner_id != owner:
            raise RunnerNotFoundError("runner not found")
        return runner

    async def update_my_runner(
        self, actor: Actor, runner_id: str, *, name: str | None = None, paused: bool | None = None
    ) -> Runner:
        runner = await self.my_runner(actor, runner_id)
        if runner.revoked_at is not None:
            raise IdentityError(IdentityErrorCode.runner_revoked)
        clean = " ".join(name.split())[:MAX_RUNNER_NAME] if name is not None else None
        if name is not None and not clean:
            raise IdentityError(IdentityErrorCode.input_invalid)
        # Пауза админа это модерация: хозяин её не снимает (иначе у админа нет ничего между «ничего» и отзывом).
        if paused is False and runner.paused and runner.paused_by is RunnerPausedBy.admin:
            raise IdentityError(IdentityErrorCode.runner_paused_by_admin)
        async with self._uow.begin():
            if clean is not None and clean != runner.name:
                await self._runners.rename(runner_id, clean, self._clock())
                await self._audit.record("runner.rename", actor_id=actor.id, target=runner_id, details={"name": clean})
            if paused is not None and paused != runner.paused:
                await self._runners.set_paused(runner_id, paused, RunnerPausedBy.owner)
                await self._audit.record(
                    "runner.pause" if paused else "runner.resume", actor_id=actor.id, target=runner_id
                )
        if paused:
            await self._after_runner_left(runner, cancel_relays=True)
        return await self.my_runner(actor, runner_id)

    async def rotate_my_token(self, actor: Actor, runner_id: str) -> RegisteredRunner:
        runner = await self.my_runner(actor, runner_id)
        if runner.revoked_at is not None:
            raise IdentityError(IdentityErrorCode.runner_revoked)
        return await self._rotate(runner, actor_id=_require_user(actor))

    async def revoke_my_runner(self, actor: Actor, runner_id: str) -> None:
        runner = await self.my_runner(actor, runner_id)
        if runner.revoked_at is not None:
            return
        await self._revoke(runner, actor_id=_require_user(actor))

    async def revoke_all_of_user(self, user_id: str) -> int:
        """Удаление человека: его раннеры и токены отзываются в транзакции вызывающего."""
        now = self._clock()
        revoked = 0
        for runner in await self._runners.list_owned(user_id):
            if runner.revoked_at is None and await self._runners.revoke(runner.id, now):
                revoked += 1
        await self._tokens.revoke_owned(user_id, now)
        if revoked and self._queue is not None:
            await self._queue.expire_personal_wait(owner_id=user_id)
        return revoked

    async def _rotate(self, runner: Runner, *, actor_id: str) -> RegisteredRunner:
        secret = new_runner_secret(RUNNER_TOKEN_PREFIX)
        token_hash = hash_runner_secret(secret)
        async with self._uow.begin():
            await self._runners.set_token_hash(runner.id, token_hash)
            await self._audit.record(
                "runner.token_rotate", actor_id=actor_id, target=runner.id, details=_owner_details(runner)
            )
        return RegisteredRunner(runner=replace(runner, token_hash=token_hash), secret=secret)

    async def _revoke(self, runner: Runner, *, actor_id: str) -> None:
        async with self._uow.begin():
            if not await self._runners.revoke(runner.id, self._clock()):
                raise RunnerNotFoundError("runner not found")
            await self._audit.record(
                "runner.revoke", actor_id=actor_id, target=runner.id, details=_owner_details(runner)
            )
        await self._after_runner_left(runner, cancel_relays=True)

    async def list_runners(self, actor: Actor, owner_kind: RunnerOwnerKind | None = None) -> list[Runner]:
        _require_admin(actor)
        return [r for r in await self._runners.list() if owner_kind is None or r.owner_kind is owner_kind]

    async def owners_of(self, runners: list[Runner]) -> dict[str, tuple[str, str]]:
        """Имя и почта хозяев личных раннеров: админу нужно знать, с кем связаться."""
        found: dict[str, tuple[str, str]] = {}
        if self._users is None:
            return found
        for owner_id in {r.owner_id for r in runners if r.owner_id is not None}:
            user = await self._users.get(owner_id)
            if user is not None:
                found[owner_id] = (user.name, user.email)
        return found

    async def rotate_token(self, actor: Actor, runner_id: str) -> RegisteredRunner:
        """Админ меняет токен только общему раннеру: иначе он получил бы токен, под которым видны проекты человека."""
        creator = _require_admin(actor)
        runner = await self._runners.get(runner_id)
        if runner is None or runner.revoked_at is not None:
            raise RunnerNotFoundError("runner not found")
        if runner.scope is RunnerScope.personal:
            raise IdentityError(IdentityErrorCode.forbidden)
        return await self._rotate(runner, actor_id=creator)

    async def revoke(self, actor: Actor, runner_id: str) -> None:
        creator = _require_admin(actor)
        runner = await self._runners.get(runner_id)
        if runner is None:
            raise RunnerNotFoundError("runner not found")
        await self._revoke(runner, actor_id=creator)

    async def set_paused(self, actor: Actor, runner_id: str, paused: bool) -> None:
        creator = _require_admin(actor)
        runner = await self._runners.get(runner_id)
        async with self._uow.begin():
            if runner is None or not await self._runners.set_paused(runner_id, paused, RunnerPausedBy.admin):
                raise RunnerNotFoundError("runner not found")
            await self._audit.record(
                "runner.pause" if paused else "runner.resume",
                actor_id=creator,
                target=runner_id,
                details=_owner_details(runner),
            )
        if paused:
            await self._after_runner_left(runner, cancel_relays=True)


def _announcement_changes(before: Runner, after: Runner) -> dict[str, object]:
    """Что `/announce` поменял в возможностях раннера: теги, возможности протокола, ИИ-адреса (было и стало)."""
    changes: dict[str, object] = {}
    if before.tags != after.tags:
        changes["tags"] = {"from": sorted(before.tags), "to": sorted(after.tags)}
    if before.features != after.features:
        changes["features"] = {"from": sorted(before.features), "to": sorted(after.features)}
    if before.ai_endpoints != after.ai_endpoints:
        changes["ai_endpoints"] = {
            "from": [f"{e.name}:{e.flavor.value}" for e in before.ai_endpoints],
            "to": [f"{e.name}:{e.flavor.value}" for e in after.ai_endpoints],
        }
    return changes


def _owner_details(runner: Runner) -> dict[str, object]:
    return {"owner_kind": runner.owner_kind.value, "owner_id": runner.owner_id}
