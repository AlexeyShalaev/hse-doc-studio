"""PostgresSettingsRepository: ключи пользователя изолированы, ключи установки меняет только админ."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.settings_scope import SOURCE_ENV
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.identity import SqlInstanceSettingsRepository, SqlUserRepository
from hse_doc_studio.infra.db.repositories.settings import _INSTANCE_KEYS, PostgresSettingsRepository
from hse_doc_studio.infra.db.session import SessionProvider

from tests.contract.test_identity_contract import make_user
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True)  # type: ignore[arg-type]
_ANNA = Actor.user("anna")
_BORIS = Actor.user("boris")


@pytest.fixture
async def repos(pg_migrated_engine):  # type: ignore[no-untyped-def]
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for uid in ("admin", "anna", "boris"):
        await users.add(make_user(uid, admin=uid == "admin"))
    return PostgresSettingsRepository(sessions), SqlInstanceSettingsRepository(sessions)


async def test__get__nothing_saved__returns_empty_dict(repos) -> None:  # type: ignore[no-untyped-def]
    settings, _ = repos
    with as_actor(_ANNA):
        assert await settings.get() == {}


async def test__save__replaces_previous_user_document(repos) -> None:  # type: ignore[no-untyped-def]
    settings, _ = repos
    with as_actor(_ANNA):
        await settings.save({"theme": "dark", "latex_passes": 4})
        await settings.save({"theme": "light", "default_agent_persona_instructions": "Пиши коротко"})
        assert await settings.get() == {"theme": "light", "default_agent_persona_instructions": "Пиши коротко"}


async def test__save__null_value__round_trips(repos) -> None:  # type: ignore[no-untyped-def]
    settings, _ = repos
    with as_actor(_ANNA):
        await settings.save({"profile_name": None})
        assert await settings.get() == {"profile_name": None}


async def test__get__user_keys_are_isolated_between_users(repos) -> None:  # type: ignore[no-untyped-def]
    settings, _ = repos
    with as_actor(_ANNA):
        await settings.save({"theme": "dark"})
    with as_actor(_BORIS):
        assert await settings.get() == {}
        await settings.save({"theme": "light"})
    with as_actor(_ANNA):
        assert await settings.get() == {"theme": "dark"}


async def test__save__admin_sets_instance_key__every_user_sees_it(repos) -> None:  # type: ignore[no-untyped-def]
    settings, _ = repos
    with as_actor(_ADMIN):
        await settings.save({"max_concurrent_compiles": 7, "theme": "dark"})
    with as_actor(_ANNA):
        assert await settings.get() == {"max_concurrent_compiles": 7}
    with as_actor(_ADMIN):
        assert await settings.get() == {"max_concurrent_compiles": 7, "theme": "dark"}


async def test__save__non_admin_changes_instance_key__forbidden_and_nothing_written(repos) -> None:  # type: ignore[no-untyped-def]
    settings, _ = repos
    with as_actor(_ADMIN):
        await settings.save({"max_concurrent_compiles": 7})
    with as_actor(_ANNA):
        with pytest.raises(IdentityError) as err:
            await settings.save({"max_concurrent_compiles": 99, "theme": "dark"})
        assert err.value.code is IdentityErrorCode.forbidden
        assert await settings.get() == {"max_concurrent_compiles": 7}


async def test__save__non_admin_drops_instance_key__forbidden(repos) -> None:  # type: ignore[no-untyped-def]
    settings, _ = repos
    with as_actor(_ADMIN):
        await settings.save({"compile_image": "tex:1"})
    with as_actor(_ANNA), pytest.raises(IdentityError) as err:
        await settings.save({"theme": "dark"})
    assert err.value.code is IdentityErrorCode.forbidden


async def test__save__non_admin_round_trips_unchanged_instance_keys__allowed(repos) -> None:  # type: ignore[no-untyped-def]
    settings, _ = repos
    with as_actor(_ADMIN):
        await settings.save({"compile_image": "tex:1"})
    with as_actor(_ANNA):
        document = await settings.get()
        await settings.save({**document, "theme": "dark"})
        assert await settings.get() == {"compile_image": "tex:1", "theme": "dark"}


async def test__save__env_sourced_instance_key__is_not_overwritten(repos) -> None:  # type: ignore[no-untyped-def]
    settings, instance = repos
    await instance.set("compile_image", "from-env:1", source=SOURCE_ENV)
    with as_actor(_ADMIN):
        with pytest.raises(IdentityError) as err:
            await settings.save({"compile_image": "typed-by-admin:2"})
        assert err.value.code is IdentityErrorCode.setting_locked
        assert (await settings.get())["compile_image"] == "from-env:1"
        await settings.save({"compile_image": "from-env:1", "theme": "dark"})


async def test__get__auth_keys_of_instance_settings__are_not_exposed(repos) -> None:  # type: ignore[no-untyped-def]
    settings, instance = repos
    await instance.set("auth.registration_mode", "open", source="admin")
    with as_actor(_ANNA):
        assert await settings.get() == {}
        await settings.save({"theme": "dark"})
    assert (await instance.get_all())["auth.registration_mode"] == "open"


async def test__get__without_actor__raises(repos) -> None:  # type: ignore[no-untyped-def]
    from hse_doc_studio.core.access.context import ActorRequired  # noqa: PLC0415

    settings, _ = repos
    with as_actor(None), pytest.raises(ActorRequired):
        await settings.get()


async def test__update_settings_uc__non_admin_changes_theme_on_empty_instance__no_instance_rows(repos) -> None:  # type: ignore[no-untyped-def]
    from hse_doc_studio.use_cases.settings.update_settings import UpdateSettingsInput, UpdateSettingsUC

    settings, _ = repos
    uc = UpdateSettingsUC(settings)
    with as_actor(_ANNA):
        await uc.execute(UpdateSettingsInput(patch={"theme": "dark"}))
        assert (await settings.get())["theme"] == "dark"
    with as_actor(_ADMIN):
        assert not set(await settings.get()) & _INSTANCE_KEYS
