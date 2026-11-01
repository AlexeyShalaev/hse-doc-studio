from __future__ import annotations

import asyncio

import pytest
from hse_doc_studio.core.identity.auth_settings import (
    KEY_PASSWORD_ENABLED,
    KEY_REGISTRATION_DOMAINS,
    KEY_REGISTRATION_MODE,
    KEY_REQUIRE_APPROVAL,
    AuthEnvOverrides,
)
from hse_doc_studio.core.identity.entities import RegistrationMode
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
from hse_doc_studio.use_cases.identity.login import LoginResult
from hse_doc_studio.use_cases.server_setup.settings import InitialSettings
from hse_doc_studio.use_cases.server_setup.token import SetupToken

from tests.unit.use_cases.server_setup.conftest import NoOidc, SetupWorld, make_world

PASSWORD = "correct horse battery"


async def _create_admin(
    world: SetupWorld, token: str | None = "st_secret", email: str = "boss@example.org"
) -> LoginResult:
    return await world.create_admin_uc().execute(token, "Босс", email, PASSWORD, ip="10.0.0.1", user_agent="UA")


def _code(error: pytest.ExceptionInfo[IdentityError]) -> IdentityErrorCode:
    return error.value.code


async def test__status__fresh_install__needs_admin_and_token(world: SetupWorld) -> None:
    status = await world.status_uc().execute()

    assert (status.state, status.token_required, status.steps_done) == ("needs_admin", True, ())


async def test__status__token_disabled__does_not_ask_for_it() -> None:
    world = make_world(token_required=False)

    assert (await world.status_uc().execute()).token_required is False


async def test__create_admin__wrong_token__nothing_is_created(world: SetupWorld) -> None:
    with pytest.raises(IdentityError) as error:
        await _create_admin(world, token="st_guess")
    with pytest.raises(IdentityError) as missing:
        await _create_admin(world, token=None)

    assert _code(error) is IdentityErrorCode.setup_token_invalid
    assert _code(missing) is IdentityErrorCode.setup_token_invalid
    assert await world.users.count() == 0


async def test__create_admin__right_token__admin_is_active_verified_and_signed_in(world: SetupWorld) -> None:
    result = await _create_admin(world)

    assert result.user.is_instance_admin
    assert result.user.email_verified
    assert result.user.can_sign_in
    assert result.session.user_id == result.user.id
    assert "setup.admin_created" in [e.action for e in await world.audit.list()]
    status = await world.status_uc().execute()
    assert (status.state, status.token_required, status.steps_done) == ("needs_admin", False, ("admin",))


async def test__create_admin__token_is_spent_after_success(world: SetupWorld) -> None:
    await _create_admin(world)

    assert world.token.required is False
    assert world.token.value is None


async def test__create_admin__weak_password__rejected_before_anything_is_stored(world: SetupWorld) -> None:
    with pytest.raises(IdentityError) as error:
        await world.create_admin_uc().execute("st_secret", "Босс", "boss@example.org", "short", ip=None, user_agent="")

    assert _code(error) is IdentityErrorCode.password_policy
    assert await world.users.count() == 0


async def test__create_admin__two_parallel_calls__exactly_one_admin(world: SetupWorld) -> None:
    outcomes = await asyncio.gather(
        _create_admin(world, email="a@example.org"),
        _create_admin(world, email="b@example.org"),
        _create_admin(world, email="c@example.org"),
        return_exceptions=True,
    )

    winners = [o for o in outcomes if not isinstance(o, BaseException)]
    losers = [o for o in outcomes if isinstance(o, IdentityError)]
    assert len(winners) == 1
    assert len(losers) == 2
    assert {e.code for e in losers} <= {IdentityErrorCode.setup_already_done, IdentityErrorCode.setup_token_invalid}
    assert await world.users.count() == 1


async def test__create_admin__after_completion__refused(world: SetupWorld) -> None:
    state = world.state()
    await state.mark_completed()

    with pytest.raises(IdentityError) as error:
        await world.create_admin_uc(state).execute("st_secret", "x", "x@example.org", PASSWORD, ip=None, user_agent="")

    assert _code(error) is IdentityErrorCode.setup_already_done


async def test__create_admin__password_is_not_in_audit(world: SetupWorld) -> None:
    await _create_admin(world)

    dump = repr(await world.audit.list())
    assert PASSWORD not in dump


async def test__bootstrap_admin__creates_once_and_never_touches_an_existing_password(world: SetupWorld) -> None:
    first = await world.bootstrap_uc().execute("root@example.org", PASSWORD, "Root")
    admin = await world.users.get_by_email("root@example.org")
    assert admin is not None
    hash_before = await world.creds.get_hash(admin.id)

    second = await world.bootstrap_uc().execute("root@example.org", "another password 1", "Root")

    assert (first.outcome, second.outcome) == ("created", "exists")
    assert await world.users.count() == 1
    assert await world.creds.get_hash(admin.id) == hash_before


async def test__bootstrap_admin__weak_password__is_an_error(world: SetupWorld) -> None:
    with pytest.raises(IdentityError) as error:
        await world.bootstrap_uc().execute("root@example.org", "123", "")

    assert _code(error) is IdentityErrorCode.password_policy


async def test__bootstrap_admin__registration_mode_from_env__wizard_is_completed() -> None:
    world = make_world(env=AuthEnvOverrides(registration_mode=RegistrationMode.closed))
    state = world.state()

    result = await world.bootstrap_uc(state).execute("root@example.org", PASSWORD)

    assert result.wizard_completed
    assert await state.is_completed()


async def test__bootstrap_admin__without_env_mode__wizard_stays_open(world: SetupWorld) -> None:
    state = world.state()

    result = await world.bootstrap_uc(state).execute("root@example.org", PASSWORD)

    assert not result.wizard_completed
    assert not await state.is_completed()
    assert (await world.status_uc(state).execute()).steps_done == ("admin",)


async def test__registration__before_a_mode_is_chosen__is_invite_only(world: SetupWorld) -> None:
    effective = await AuthSettingsService(world.settings, world.env).effective()

    assert effective.registration_mode is RegistrationMode.invite


async def test__settings__saved_and_step_marked_done(world: SetupWorld) -> None:
    admin = await _create_admin(world)

    await world.settings_uc().execute(
        admin.user.id,
        InitialSettings(RegistrationMode.domains, ["@HSE.ru", "edu.hse.ru"], True, True),
    )

    values = await world.settings.get_all()
    assert values[KEY_REGISTRATION_MODE] == "domains"
    assert values[KEY_REGISTRATION_DOMAINS] == ["hse.ru", "edu.hse.ru"]
    assert values[KEY_REQUIRE_APPROVAL] is True
    assert (await world.status_uc().execute()).steps_done == ("admin", "settings")


async def test__settings__domains_are_dropped_outside_the_domains_mode(world: SetupWorld) -> None:
    admin = await _create_admin(world)

    await world.settings_uc().execute(admin.user.id, InitialSettings(RegistrationMode.open, ["hse.ru"], False, True))

    assert (await world.settings.get_all())[KEY_REGISTRATION_DOMAINS] == []


async def test__settings__keys_from_env_are_skipped_not_overwritten() -> None:
    world = make_world(env=AuthEnvOverrides(registration_mode=RegistrationMode.closed, password_enabled=True))
    admin = await _create_admin(world)

    await world.settings_uc().execute(admin.user.id, InitialSettings(RegistrationMode.open, [], True, False))

    values = await world.settings.get_all()
    assert KEY_REGISTRATION_MODE not in values
    assert KEY_PASSWORD_ENABLED not in values
    assert values[KEY_REQUIRE_APPROVAL] is True


async def test__settings__password_off_without_sso__refused(world: SetupWorld) -> None:
    admin = await _create_admin(world)

    with pytest.raises(IdentityError) as error:
        await world.settings_uc().execute(admin.user.id, InitialSettings(RegistrationMode.invite, [], False, False))

    assert _code(error) is IdentityErrorCode.forbidden
    assert KEY_PASSWORD_ENABLED not in await world.settings.get_all()


async def test__settings__password_off_with_sso__allowed(world: SetupWorld) -> None:
    world.oidc = NoOidc(enabled=1)
    admin = await _create_admin(world)

    await world.settings_uc().execute(admin.user.id, InitialSettings(RegistrationMode.invite, [], False, False))

    assert (await world.settings.get_all())[KEY_PASSWORD_ENABLED] is False


async def test__complete__marks_ready_and_is_remembered_by_a_new_service(world: SetupWorld) -> None:
    admin = await _create_admin(world)

    await world.complete_uc().execute(admin.user.id)

    status = await world.status_uc(world.state()).execute()
    assert (status.state, status.token_required, status.steps_done) == ("ready", False, ("admin", "settings"))


async def test__token__generated_value_is_random_and_prefixed() -> None:
    first, second = SetupToken(required=True), SetupToken(required=True)

    assert first.value is not None
    assert first.value.startswith("st_")
    assert first.value != second.value


async def test__token__compare_is_exact_and_tolerates_odd_input() -> None:
    token = SetupToken(required=True, value="st_x")

    assert token.verify("st_x")
    assert not token.verify("st_y")
    assert not token.verify("")
    assert not token.verify(None)
    assert not token.verify("st_\udcff")
