"""PostgresAIProviderRepository: ключ шифртекстом, изоляция владельцев, общие провайдеры установки, фоновые ходы."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from hse_doc_studio.core.access.context import ActorRequired
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind, AIProviderType
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.core.secrets import encrypted_columns
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.ai_providers import AIProviderRow
from hse_doc_studio.infra.db.repositories.ai_providers import PostgresAIProviderRepository
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.runners import SqlRunnerRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

_ANNA = Actor.user("anna", name="Анна")
_BORIS = Actor.user("boris", name="Борис")
_ADMIN = Actor.user("root", name="Админ", is_instance_admin=True)
_T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
_KEY = "sk-very-secret-key"


@dataclass
class World:
    sessions: SessionProvider
    repo: PostgresAIProviderRepository
    cipher: FernetSecretCipher


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for user_id in ("anna", "boris", "root"):
        await users.add(make_user(user_id, admin=user_id == "root"))
    cipher = FernetSecretCipher(KeyFileStore(tmp_path / "k.json", env_key=Fernet.generate_key().decode()))
    return World(sessions, PostgresAIProviderRepository(sessions, cipher), cipher)


def make_provider(name: str = "OpenAI", **changes: object) -> AIProvider:
    provider = AIProvider(
        id=uuid4(),
        name=name,
        type=AIProviderType.openai_compat,
        api_key=_KEY,
        base_url="https://llm.example.test/v1",
        models=["m1", "m2"],
        created_at=_T0,
        ssl_verify=False,
        connect_timeout_s=5.0,
        request_timeout_s=90.0,
    )
    return replace(provider, **changes)


async def test__create_and_get__roundtrips_all_fields_for_the_owner(world: World) -> None:
    provider = make_provider()
    with as_actor(_ANNA):
        await world.repo.create(provider)
        loaded = await world.repo.get(provider.id)
        listed = await world.repo.list_all()

    assert loaded == provider
    assert listed == [provider]


async def test__api_key__is_stored_as_ciphertext_bound_to_the_row(world: World) -> None:
    provider = make_provider()
    with as_actor(_ANNA):
        await world.repo.create(provider)

    async with world.sessions.use() as session:
        stored = (await session.execute(select(AIProviderRow.api_key_enc))).scalar_one()
        dump = (await session.execute(text("SELECT row_to_json(p)::text FROM ai_providers p"))).scalar_one()
    assert stored is not None
    assert stored.startswith("hs1:")
    assert _KEY not in dump
    other = uuid4()
    with pytest.raises(GitSyncError):
        world.cipher.decrypt(stored, aad=f"ai_providers/api_key_enc/{other}")
    assert any(column.label == "ai_providers.api_key_enc" for column in encrypted_columns.all())


async def test__update__blank_key_keeps_the_stored_key(world: World) -> None:
    provider = make_provider()
    with as_actor(_ANNA):
        await world.repo.create(provider)
        await world.repo.update(replace(provider, name="Новое", api_key="", models=["m3"]))
        kept = await world.repo.get(provider.id)
        await world.repo.update(replace(provider, api_key="sk-new"))
        rotated = await world.repo.get(provider.id)

    assert kept is not None
    assert (kept.name, kept.models, kept.api_key) == ("Новое", ["m3"], _KEY)
    assert rotated is not None
    assert rotated.api_key == "sk-new"


async def test__keyless_provider__has_no_ciphertext(world: World) -> None:
    ollama = make_provider("Ollama", type=AIProviderType.ollama, api_key="")
    with as_actor(_ANNA):
        await world.repo.create(ollama)
        loaded = await world.repo.get(ollama.id)

    assert loaded is not None
    assert loaded.api_key == ""
    async with world.sessions.use() as session:
        assert (await session.execute(select(AIProviderRow.api_key_enc))).scalar_one() is None


async def test__isolation__foreign_provider_is_invisible_and_untouchable(world: World) -> None:
    provider = make_provider()
    with as_actor(_ANNA):
        await world.repo.create(provider)

    with as_actor(_BORIS):
        assert await world.repo.list_all() == []
        assert await world.repo.get(provider.id) is None
        assert await world.repo.delete(provider.id) is False
        with pytest.raises(NotFoundError):
            await world.repo.update(replace(provider, name="Взлом"))
    with as_actor(_ANNA):
        loaded = await world.repo.get(provider.id)
    assert loaded is not None
    assert loaded.name == "OpenAI"


async def test__no_actor_or_non_user__is_refused(world: World) -> None:
    with as_actor(None), pytest.raises(ActorRequired):
        await world.repo.list_all()
    with as_actor(Actor.local()), pytest.raises(ActorRequired):
        await world.repo.list_all()


async def test__delete__removes_only_own_provider(world: World) -> None:
    mine, other = make_provider("Моё"), make_provider("Чужое")
    with as_actor(_ANNA):
        await world.repo.create(mine)
    with as_actor(_BORIS):
        await world.repo.create(other)
    with as_actor(_ANNA):
        assert await world.repo.delete(mine.id) is True
        assert await world.repo.delete(mine.id) is False
        assert await world.repo.list_all() == []
    with as_actor(_BORIS):
        assert [p.name for p in await world.repo.list_all()] == ["Чужое"]


async def test__user_delete__cascades_to_their_providers(world: World) -> None:
    with as_actor(_ANNA):
        await world.repo.create(make_provider())
    async with world.sessions.use() as session:
        await session.execute(text("DELETE FROM users WHERE id = 'anna'"))
    async with world.sessions.use() as session:
        assert (await session.execute(select(AIProviderRow.id))).all() == []


async def test__shared_provider__visible_to_everyone_without_key_and_admin_only_to_change(world: World) -> None:
    shared = make_provider("Общий", owner_kind=AIProviderOwnerKind.instance)
    with as_actor(_ANNA), pytest.raises(IdentityError):
        await world.repo.create(shared)
    with as_actor(_ADMIN):
        await world.repo.create(shared)
        as_admin = await world.repo.get(shared.id)

    with as_actor(_ANNA):
        listed = await world.repo.list_all()
        got = await world.repo.get(shared.id)
        assert await world.repo.delete(shared.id) is False
        with pytest.raises(NotFoundError):
            await world.repo.update(replace(shared, name="Взлом"))
    assert as_admin is not None
    assert as_admin.api_key == _KEY
    assert [p.owner_kind for p in listed] == [AIProviderOwnerKind.instance]
    assert got is not None
    assert (got.name, got.api_key) == ("Общий", "")
    async with world.sessions.use() as session:
        assert (await session.execute(select(AIProviderRow.owner_id))).scalar_one() is None

    with as_actor(_ADMIN):
        assert await world.repo.delete(shared.id) is True


async def test__shared_provider__is_listed_after_own_ones(world: World) -> None:
    with as_actor(_ADMIN):
        await world.repo.create(make_provider("Общий", owner_kind=AIProviderOwnerKind.instance, created_at=_T0))
    with as_actor(_ANNA):
        await world.repo.create(replace(make_provider("Личный"), created_at=_T0.replace(hour=13)))
        names = [p.name for p in await world.repo.list_all()]

    assert names == ["Общий", "Личный"]


async def test__unreadable_key__list_survives_and_get_reports_it(world: World, tmp_path: Path) -> None:
    provider = make_provider()
    with as_actor(_ANNA):
        await world.repo.create(provider)
    stranger = PostgresAIProviderRepository(
        world.sessions,
        FernetSecretCipher(KeyFileStore(tmp_path / "other.json", env_key=Fernet.generate_key().decode())),
    )

    with as_actor(_ANNA):
        listed = await stranger.list_all()
        with pytest.raises(GitSyncError):
            await stranger.get(provider.id)
        # Сохранение остальных полей нечитаемый ключ не портит
        await stranger.update(replace(listed[0], name="Новое"))
        recovered = await world.repo.get(provider.id)
    assert [p.api_key for p in listed] == [""]
    assert recovered is not None
    assert (recovered.name, recovered.api_key) == ("Новое", _KEY)


async def test__background_turn__reads_the_provider_of_the_actor_who_started_it(world: World) -> None:
    provider = make_provider()
    with as_actor(_ANNA):
        await world.repo.create(provider)

        async def background_turn() -> AIProvider | None:
            await asyncio.sleep(0)
            return await world.repo.get(provider.id)

        # Задача фонового хода создаётся из запроса и наследует актора через контекст
        loaded = await asyncio.create_task(background_turn())

    assert loaded is not None
    assert loaded.api_key == _KEY


async def test__owner_check__rejects_inconsistent_rows(world: World) -> None:
    async with world.sessions.use() as session:
        for kind, owner in (("user", None), ("instance", "anna"), ("org", "anna")):
            with pytest.raises(Exception, match="ck_ai_providers_owner"):
                async with session.begin_nested():
                    await session.execute(
                        text(
                            "INSERT INTO ai_providers (id, owner_kind, owner_id, name, type, created_at) "
                            "VALUES (:id, :kind, :owner, 'x', 'openai', now())"
                        ),
                        {"id": uuid4(), "kind": kind, "owner": owner},
                    )


async def test__admin_store__shared_provider_is_visible_to_users_without_the_key(world: World) -> None:
    from hse_doc_studio.use_cases.admin.ops_ai_providers import InstanceAiProviderStore  # noqa: PLC0415

    store = InstanceAiProviderStore(world.repo)
    shared = make_provider("Общий Claude", owner_kind=AIProviderOwnerKind.instance, type=AIProviderType.claude)

    with as_actor(_ADMIN):
        await store.save(
            await _as_instance(shared),
            api_key=_KEY,
        )
        assert [p.name for p in await store.list()] == ["Общий Claude"]
        assert await store.reveal_key(shared.id) == _KEY
        await store.save(await _as_instance(shared), clear_key=True)
        assert await store.reveal_key(shared.id) == ""
        await store.save(await _as_instance(shared), api_key=_KEY)
    with as_actor(_ANNA):
        seen = await world.repo.list_all()
    assert [(p.name, p.owner_kind, p.api_key) for p in seen] == [("Общий Claude", AIProviderOwnerKind.instance, "")]


async def _as_instance(provider: AIProvider):  # noqa: ANN202
    from hse_doc_studio.use_cases.admin.ops_ai_providers import InstanceAiProvider  # noqa: PLC0415

    return InstanceAiProvider(
        id=provider.id,
        name=provider.name,
        type=provider.type,
        base_url=provider.base_url,
        models=tuple(provider.models),
        ssl_verify=provider.ssl_verify,
        connect_timeout_s=provider.connect_timeout_s,
        request_timeout_s=provider.request_timeout_s,
        created_at=provider.created_at,
        key_set=False,
    )


async def test__runner_provider__keeps_runner_and_endpoint_through_create_update_and_read(world: World) -> None:
    """Провайдер «через мой раннер» без раннера в строке нарушает ck_ai_providers_runner: поля обязаны доехать."""
    runner_id = uuid4().hex
    await SqlRunnerRepository(world.sessions).add(
        Runner(
            id=runner_id,
            name="MacBook Анны",
            token_hash=uuid4().hex,
            tags=frozenset({"ai", "tex"}),
            concurrency=1,
            resource_class="standard",
            version="0.3.0",
            created_at=_T0,
            owner_kind=RunnerOwnerKind.user,
            owner_id="anna",
        )
    )
    provider = make_provider(
        "Модель за раннером",
        type=AIProviderType.runner,
        api_key="",
        base_url="",
        models=[],
        ssl_verify=True,
        owner_kind=AIProviderOwnerKind.user,
        runner_id=runner_id,
        runner_endpoint="ollama",
    )
    with as_actor(_ANNA):
        await world.repo.create(provider)
        assert await world.repo.get(provider.id) == provider
        renamed = replace(provider, name="Ollama дома", runner_endpoint="vllm", models=["qwen"])
        await world.repo.update(renamed)
        assert await world.repo.list_all() == [renamed]
