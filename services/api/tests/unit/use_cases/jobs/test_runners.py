from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError, RunnerNotFoundError
from hse_doc_studio.core.jobs.runners import hash_runner_secret
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION, RunnerRegisterRequest
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository

T0 = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)
USER = Actor.user("user")


class _Uow:
    @asynccontextmanager
    async def begin(self):  # type: ignore[no-untyped-def]
        yield


class _Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


class World:
    def __init__(self) -> None:
        self.clock = _Clock()
        self.runners = InMemoryRunnerRepository()
        self.tokens = InMemoryRegistrationTokenRepository()
        self.audit = InMemoryAuditLog()
        self.registry = RunnerRegistry(self.runners, self.tokens, self.audit, _Uow(), clock=self.clock)  # type: ignore[arg-type]


def _request(**kwargs: object) -> RunnerRegisterRequest:
    values: dict[str, object] = {
        "name": "r1",
        "protocol": RUNNER_PROTOCOL_VERSION,
        "version": "0.3.0",
        "tags": frozenset({"office"}),
        "concurrency": 2,
    }
    return RunnerRegisterRequest(**{**values, **kwargs})  # type: ignore[arg-type]


@pytest.fixture
def world() -> World:
    return World()


async def test__register__valid_token__issues_runner_token_and_stores_only_hashes(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN, label="compose")

    registered = await world.registry.register(created.secret, _request())

    stored = (await world.runners.list())[0]
    assert stored.token_hash == hash_runner_secret(registered.secret)
    assert registered.secret not in repr(stored) + repr(registered) + repr(created)
    assert created.secret not in repr(await world.tokens.list())
    assert (await world.registry.authenticate(registered.secret)).id == registered.runner.id
    assert stored.tags == frozenset({"office"})


async def test__register__single_use_token__second_use_rejected(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN)
    await world.registry.register(created.secret, _request())

    with pytest.raises(RunnerAuthError) as err:
        await world.registry.register(created.secret, _request(name="r2"))

    assert err.value.code is RunnerErrorCode.runner_unauthorized
    assert len(await world.runners.list()) == 1


async def test__register__max_uses__allows_exactly_that_many(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN, max_uses=2)

    await world.registry.register(created.secret, _request(name="a"))
    await world.registry.register(created.secret, _request(name="b"))
    with pytest.raises(RunnerAuthError):
        await world.registry.register(created.secret, _request(name="c"))


async def test__register__expired_token__rejected(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN, ttl=timedelta(hours=1))
    world.clock.now += timedelta(hours=1, seconds=1)

    with pytest.raises(RunnerAuthError):
        await world.registry.register(created.secret, _request())


async def test__register__revoked_token__rejected(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN)
    await world.registry.revoke_registration_token(ADMIN, created.token.id)

    with pytest.raises(RunnerAuthError):
        await world.registry.register(created.secret, _request())


async def test__register__unknown_secret__rejected(world: World) -> None:
    with pytest.raises(RunnerAuthError) as err:
        await world.registry.register("hsrt_nope", _request())

    assert err.value.code is RunnerErrorCode.runner_unauthorized


async def test__register__old_protocol__rejected_without_spending_the_token(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN)

    with pytest.raises(RunnerAuthError) as err:
        await world.registry.register(created.secret, _request(protocol=RUNNER_PROTOCOL_VERSION + 1))

    assert err.value.code is RunnerErrorCode.runner_protocol_unsupported
    assert (await world.tokens.get(created.token.id)).uses == 0  # type: ignore[union-attr]


async def test__authenticate__revoked_runner__rejected_like_unknown(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN)
    registered = await world.registry.register(created.secret, _request())

    await world.registry.revoke(ADMIN, registered.runner.id)

    for secret in (registered.secret, "hsrn_unknown"):
        with pytest.raises(RunnerAuthError) as err:
            await world.registry.authenticate(secret)
        assert err.value.code is RunnerErrorCode.runner_unauthorized


async def test__rotate_token__old_token_stops_working_new_one_works(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN)
    registered = await world.registry.register(created.secret, _request())

    rotated = await world.registry.rotate_token(ADMIN, registered.runner.id)

    with pytest.raises(RunnerAuthError):
        await world.registry.authenticate(registered.secret)
    assert (await world.registry.authenticate(rotated.secret)).id == registered.runner.id


async def test__rotate_token__revoked_runner__not_found(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN)
    registered = await world.registry.register(created.secret, _request())
    await world.registry.revoke(ADMIN, registered.runner.id)

    with pytest.raises(RunnerNotFoundError):
        await world.registry.rotate_token(ADMIN, registered.runner.id)


async def test__pause__marks_runner_but_keeps_it_authenticated(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN)
    registered = await world.registry.register(created.secret, _request())

    await world.registry.set_paused(ADMIN, registered.runner.id, True)

    assert (await world.registry.authenticate(registered.secret)).paused is True


async def test__management__non_admin__forbidden(world: World) -> None:
    created = await world.registry.create_registration_token(ADMIN)
    registered = await world.registry.register(created.secret, _request())
    calls = [
        world.registry.create_registration_token(USER),
        world.registry.list_registration_tokens(USER),
        world.registry.revoke_registration_token(USER, created.token.id),
        world.registry.list_runners(USER),
        world.registry.rotate_token(USER, registered.runner.id),
        world.registry.revoke(USER, registered.runner.id),
        world.registry.set_paused(USER, registered.runner.id, True),
    ]

    for call in calls:
        with pytest.raises(IdentityError):
            await call


async def test__create_registration_token__bad_limits__rejected(world: World) -> None:
    for kwargs in ({"ttl": timedelta(0)}, {"ttl": timedelta(days=365)}, {"max_uses": 0}, {"max_uses": 1000}):
        with pytest.raises(ValueError):  # noqa: PT011
            await world.registry.create_registration_token(ADMIN, **kwargs)  # type: ignore[arg-type]


async def test__bootstrap_token__registers_one_runner_then_is_spent_across_restarts(world: World) -> None:
    await world.registry.ensure_bootstrap_token("boot-secret")
    await world.registry.register("boot-secret", _request())

    # Перезапуск api с тем же значением в окружении не оживляет токен.
    await world.registry.ensure_bootstrap_token("boot-secret")
    with pytest.raises(RunnerAuthError):
        await world.registry.register("boot-secret", _request(name="again"))

    # Новое значение в окружении это новый токен.
    await world.registry.ensure_bootstrap_token("boot-secret-2")
    await world.registry.register("boot-secret-2", _request(name="second"))
    assert len(await world.runners.list()) == 2


async def test__secrets__never_reach_logs_or_audit(world: World, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    await world.registry.ensure_bootstrap_token("boot-secret-value")
    created = await world.registry.create_registration_token(ADMIN)
    registered = await world.registry.register(created.secret, _request())
    rotated = await world.registry.rotate_token(ADMIN, registered.runner.id)
    await world.registry.revoke(ADMIN, registered.runner.id)

    seen = caplog.text + repr(await world.audit.list(limit=100))
    for secret in ("boot-secret-value", created.secret, registered.secret, rotated.secret):
        assert secret not in seen
    actions = {entry.action for entry in await world.audit.list(limit=100)}
    assert {
        "runner.registration_token_create",
        "runner.register",
        "runner.token_rotate",
        "runner.revoke",
    } <= actions
