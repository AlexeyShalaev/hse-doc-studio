"""Доверие к git-серверам в Postgres: запись только админом, материализация файлов для git, совпадение файла с базой."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.git_sync.entities import ScannedHostKey
from hse_doc_studio.core.git_sync.host_keys import key_fingerprint
from hse_doc_studio.core.git_sync.host_settings import GitHostSettings
from hse_doc_studio.core.git_sync.providers import ApiDetection, GitProvider
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.git_trust import GitKnownHostRow
from hse_doc_studio.infra.db.repositories.git_trust import PostgresGitHostSettingsRepository, PostgresKnownHostsStore
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.git_sync.host_settings_repository import JsonGitHostSettingsRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.fixtures.actors import as_actor
from tests.unit.core.git_sync.test_host_keys import GITHUB_ED25519, GITHUB_FINGERPRINT

pytestmark = pytest.mark.pg

_ANNA = Actor.user("anna", name="Анна")
_ADMIN = Actor.user("root", name="Админ", is_instance_admin=True)
_OTHER_KEY = "AAAAC3NzaC1lZDI1NTE5AAAAIGk1Zq6mYQdkYxjqU4tUq0h8Y1m7X6uQ0mHk2m9o3a4B"
_HOST = "git.hse.local"


@dataclass
class World:
    sessions: SessionProvider
    settings: PostgresGitHostSettingsRepository
    hosts: PostgresKnownHostsStore
    runtime: Path


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    await users.add(make_user("anna"))
    await users.add(make_user("root", admin=True))
    runtime = tmp_path / "runtime"
    return World(
        sessions,
        PostgresGitHostSettingsRepository(sessions, runtime),
        PostgresKnownHostsStore(sessions, runtime),
        runtime,
    )


def _key(blob: str = GITHUB_ED25519) -> ScannedHostKey:
    return ScannedHostKey("ssh-ed25519", blob, key_fingerprint(blob))


def _trusted() -> GitHostSettings:
    return GitHostSettings(_HOST, 8443, provider_override=GitProvider.gitlab, ca_pem="CA-PEM\n", pinned_pem="PIN-PEM\n")


async def test__save__roundtrips_all_fields(world: World) -> None:
    settings = GitHostSettings(
        _HOST,
        8443,
        provider_override=GitProvider.gitlab,
        ca_pem="CA",
        pinned_fingerprint="SHA256:abc",
        pinned_pem="PIN",
        detected=ApiDetection(GitProvider.gitlab, "17.3.1", "https://git.hse.local:8443/api/v4"),
    )
    with as_actor(_ADMIN):
        await world.settings.save(settings)

    with as_actor(_ANNA):
        assert await world.settings.get(_HOST, 8443) == settings
        assert await world.settings.list() == [settings]


async def test__save__trust_fields_by_a_regular_user__forbidden(world: World) -> None:
    with as_actor(_ANNA), pytest.raises(IdentityError):
        await world.settings.save(_trusted())
    with as_actor(_ADMIN):
        await world.settings.save(_trusted())

    with as_actor(_ANNA), pytest.raises(IdentityError):
        await world.settings.save(GitHostSettings(_HOST, 8443))
    with as_actor(_ANNA), pytest.raises(IdentityError):
        await world.settings.save(GitHostSettings(_HOST, 8443, provider_override=GitProvider.gitlab, ca_pem="EVIL"))
    assert (await world.settings.get(_HOST, 8443)) == _trusted()


async def test__save__detection_cache__may_be_refreshed_by_anyone(world: World) -> None:
    detected = ApiDetection(GitProvider.gitea, "1.22", "https://git2.hse.local/api/v1")
    with as_actor(_ANNA):
        await world.settings.save(GitHostSettings("git2.hse.local", None).with_detection(detected))
    with as_actor(_ADMIN):
        await world.settings.save(_trusted())
    with as_actor(_ANNA):
        await world.settings.save(_trusted().with_detection(detected))
        await world.settings.save(GitHostSettings("git2.hse.local", None))
    assert (await world.settings.get(_HOST, 8443)) == _trusted().with_detection(detected)
    assert await world.settings.get("git2.hse.local", None) is None


async def test__save__without_actor__only_the_detection_cache(world: World) -> None:
    with pytest.raises(IdentityError):
        await world.settings.save(_trusted())
    await world.settings.save(GitHostSettings(_HOST, None).with_detection(ApiDetection(GitProvider.gitlab, None, None)))


async def test__materialize__file_matches_the_database_and_is_private(world: World) -> None:
    with as_actor(_ADMIN):
        await world.settings.save(_trusted())
    assert world.settings.trust_file(_HOST, 8443) is None

    await world.settings.materialize()

    path = world.settings.trust_file(_HOST, 8443)
    assert path is not None
    assert path.read_text() == "CA-PEM\nPIN-PEM\n"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700


async def test__materialize__is_identical_to_the_json_repository(world: World, tmp_path: Path) -> None:
    json_repo = JsonGitHostSettingsRepository(tmp_path / "json")
    await json_repo.save(_trusted())
    with as_actor(_ADMIN):
        await world.settings.save(_trusted())
    await world.settings.materialize()

    pg_file = world.settings.trust_file(_HOST, 8443)
    json_file = json_repo.trust_file(_HOST, 8443)
    assert pg_file is not None
    assert json_file is not None
    assert pg_file.read_bytes() == json_file.read_bytes()


async def test__materialize__changed_and_removed_records__reach_the_file_before_the_next_command(world: World) -> None:
    with as_actor(_ADMIN):
        await world.settings.save(_trusted())
        await world.settings.materialize()
        path = world.settings.trust_file(_HOST, 8443)
        assert path is not None

        await world.settings.save(GitHostSettings(_HOST, 8443, ca_pem="NEW\n"))
        await world.settings.materialize()
        assert path.read_text() == "NEW\n"

        path.write_text("tampered")
        await world.settings.materialize()
        assert path.read_text() == "NEW\n"

        await world.settings.save(GitHostSettings(_HOST, 8443))
        await world.settings.materialize()
    assert world.settings.trust_file(_HOST, 8443) is None
    assert not path.exists()


async def test__known_hosts__trust_and_forget_need_the_admin(world: World) -> None:
    with as_actor(_ANNA):
        with pytest.raises(IdentityError):
            await world.hosts.trust(_HOST, None, [_key()])
        assert await world.hosts.list() == []
    with as_actor(_ADMIN):
        await world.hosts.trust(_HOST, None, [_key()])
    with as_actor(_ANNA):
        found = await world.hosts.find(_HOST, None)
        assert found is not None
        assert found.fingerprints_sha256 == (GITHUB_FINGERPRINT,)
        with pytest.raises(IdentityError):
            await world.hosts.forget(_HOST, None)
    assert await world.hosts.find(_HOST, None) is not None


async def test__known_hosts__port_22_and_no_port_are_one_entry_and_replace_drops_old_keys(world: World) -> None:
    other = _key(_OTHER_KEY)
    with as_actor(_ADMIN):
        await world.hosts.trust(_HOST, 22, [_key()])
        await world.hosts.trust(_HOST, None, [_key()])
        await world.hosts.trust(_HOST, 2222, [other])
        assert [(h.host, h.port) for h in await world.hosts.list()] == [(_HOST, None), (_HOST, 2222)]

        await world.hosts.trust(_HOST, None, [other], replace=True)
        replaced = await world.hosts.find(_HOST, None)
        await world.hosts.forget(_HOST, 2222)
    assert replaced is not None
    assert replaced.fingerprints_sha256 == (other.fingerprint_sha256,)
    assert [(h.host, h.port) for h in await world.hosts.list()] == [(_HOST, None)]


async def test__known_hosts__invalid_keys_are_skipped(world: World) -> None:
    with as_actor(_ADMIN):
        await world.hosts.trust(_HOST, None, [ScannedHostKey("ssh-ed25519", "not base64!", "SHA256:x"), _key()])
    async with world.sessions.use() as session:
        assert len((await session.execute(select(GitKnownHostRow))).scalars().all()) == 1


async def test__known_hosts_file__matches_the_database_and_follows_removals(world: World) -> None:
    with as_actor(_ADMIN):
        await world.hosts.trust(_HOST, None, [_key()])
        await world.hosts.trust("git.other", 2222, [_key(_OTHER_KEY)])
        await world.hosts.materialize()
        path = world.hosts.file_path()
        lines = path.read_text().splitlines()
        assert [line.split()[0] for line in lines] == ["[git.other]:2222", _HOST]
        assert lines[1].split()[1:3] == ["ssh-ed25519", GITHUB_ED25519]
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

        await world.hosts.forget(_HOST, None)
        assert _HOST in path.read_text()
        await world.hosts.materialize()
    assert _HOST not in path.read_text().replace("git.other", "")
    assert len(path.read_text().splitlines()) == 1


async def test__known_hosts_file__empty_store__empty_file(world: World) -> None:
    await world.hosts.materialize()
    assert world.hosts.file_path().read_text() == ""
