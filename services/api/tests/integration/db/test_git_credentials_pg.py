"""Git-доступы в Postgres: владелец, шифртекст, привязка к проекту и адресу, роли и аудит использования."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import structlog
from cryptography.fernet import Fernet
from hse_doc_studio.core.access.context import ActorRequired
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteUrl, parse_remote_url
from hse_doc_studio.core.identity.entities import AuditQuery
from hse_doc_studio.core.secrets import encrypted_columns
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.git_credentials import GitCredentialRow, GitRemoteBindingRow
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.repositories.auth import SqlAuditLog
from hse_doc_studio.infra.db.repositories.git_credentials import (
    AUDIT_BIND,
    AUDIT_UNBIND,
    AUDIT_USE,
    PostgresCredentialAccess,
    PostgresCredentialUsage,
    PostgresGitCredentialRepository,
    PostgresGitRemoteBindings,
)
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.projects.acl_flags import AclFlagsCache
from hse_doc_studio.infra.secrets.fernet_cipher import FernetSecretCipher
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

_ANNA = Actor.user("anna", name="Анна")
_BORIS = Actor.user("boris", name="Борис")
_CAROL = Actor.user("carol", name="Карина")
_DAN = Actor.user("dan", name="Даниил")
_TOKEN = "ghp_CANARYtokenValue1234567890abcdef"
_NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
_REMOTE = parse_remote_url("https://github.com/hse/course.git")


@dataclass
class World:
    sessions: SessionProvider
    repo: PostgresGitCredentialRepository
    bindings: PostgresGitRemoteBindings
    access: PostgresCredentialAccess
    usage: PostgresCredentialUsage
    audit: SqlAuditLog
    cipher: FernetSecretCipher

    async def project(self, *, members: dict[str, str] | None = None, owner: str = "anna") -> UUID:
        project_id = uuid4()
        async with self.sessions.use() as session:
            session.add(
                ProjectRow(
                    id=project_id,
                    name=f"Проект {str(project_id)[:4]}",
                    owner_user_id=owner,
                    workspace_path=str(project_id),
                    kind="paper",
                    lang="ru",
                )
            )
            await session.flush()
            for user, role in (members or {}).items():
                session.add(
                    ProjectMemberRow(project_id=project_id, principal_kind="user", principal_id=user, role=role)
                )
        return project_id

    async def credential(self, actor: Actor = _ANNA, *, host: str = "github.com") -> UUID:
        credential = GitCredential(
            id=uuid4(),
            kind=GitCredentialKind.pat,
            label="Рабочий токен",
            host=host,
            username=None,
            status=CredentialStatus.unverified,
            created_at=_NOW,
            token_family="ghp",
        )
        with as_actor(actor):
            await self.repo.add(credential, Secret(_TOKEN))
        return credential.id

    async def audit_actions(self) -> list[tuple[str, str | None]]:
        return [(e.action, e.actor_id) for e in reversed(await self.audit.query(AuditQuery(limit=100)))]


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for user in ("anna", "boris", "carol", "dan"):
        await users.add(make_user(user))
    cipher = FernetSecretCipher(KeyFileStore(tmp_path / "k.json", env_key=Fernet.generate_key().decode()))
    audit = SqlAuditLog(sessions)
    return World(
        sessions,
        PostgresGitCredentialRepository(sessions, cipher),
        PostgresGitRemoteBindings(sessions, audit),
        PostgresCredentialAccess(sessions, cipher, PostgresProjectAclRepository(sessions, AclFlagsCache()), audit),
        PostgresCredentialUsage(sessions),
        audit,
        cipher,
    )


async def _bind(world: World, project_id: UUID, credential_id: UUID, remote: RemoteUrl = _REMOTE) -> None:
    with as_actor(_ANNA):
        await world.bindings.bind(project_id, credential_id, remote)


async def _secret(
    world: World, actor: Actor | None, credential_id: UUID, project_id: UUID | None, remote: RemoteUrl
) -> str:
    with as_actor(actor):
        return (await world.access.get_secret(credential_id, project_id=project_id, remote=remote)).reveal()


async def test__repository__owner_roundtrip_keeps_the_secret_only_encrypted(world: World) -> None:
    credential_id = await world.credential()

    with as_actor(_ANNA):
        listed = await world.repo.list()
        secret = await world.repo.get_secret(credential_id)
    async with world.sessions.use() as session:
        row = (await session.execute(select(GitCredentialRow))).scalar_one()

    assert [c.id for c in listed] == [credential_id]
    assert secret.reveal() == _TOKEN
    assert _TOKEN not in row.secret_enc
    assert any(column.label == "git_credentials.secret_enc" for column in encrypted_columns.all())


async def test__repository__ciphertext_moved_to_another_record__is_refused(world: World) -> None:
    first = await world.credential()
    second = await world.credential()
    async with world.sessions.use() as session:
        a = await session.get(GitCredentialRow, first)
        b = await session.get(GitCredentialRow, second)
        assert a is not None
        assert b is not None
        b.secret_enc = a.secret_enc

    with as_actor(_ANNA), pytest.raises(GitSyncError) as raised:
        await world.repo.get_secret(second)

    assert raised.value.code is GitErrorCode.secrets_unavailable


async def test__repository__another_user__sees_changes_and_deletes_nothing(world: World) -> None:
    credential_id = await world.credential()

    with as_actor(_BORIS):
        assert await world.repo.list() == []
        assert await world.repo.get(credential_id) is None
        assert await world.repo.delete(credential_id) is False
        with pytest.raises(NotFoundError):
            await world.repo.get_secret(credential_id)
        with pytest.raises(NotFoundError):
            await world.repo.update(
                GitCredential(
                    id=credential_id,
                    kind=GitCredentialKind.pat,
                    label="Чужой",
                    host="github.com",
                    username=None,
                    status=CredentialStatus.ok,
                    created_at=_NOW,
                )
            )
    with as_actor(_ANNA):
        kept = await world.repo.get(credential_id)
    assert kept is not None
    assert kept.label == "Рабочий токен"


@pytest.mark.parametrize("actor", [None, Actor.local(), Actor.guest("link-1")])
async def test__repository__no_user_actor__raises_actor_required(world: World, actor: Actor | None) -> None:
    with as_actor(actor), pytest.raises(ActorRequired):
        await world.repo.list()


async def test__repository__update_without_secret_keeps_it_and_mark_works_for_the_runner(world: World) -> None:
    credential_id = await world.credential()
    with as_actor(_ANNA):
        current = await world.repo.get(credential_id)
        assert current is not None
        await world.repo.update(GitCredential(**{**current.__dict__, "label": "Новое имя"}))

    await world.repo.mark(credential_id, CredentialStatus.auth_failed, used_at=_NOW)

    with as_actor(_ANNA):
        stored = await world.repo.get(credential_id)
        secret = await world.repo.get_secret(credential_id)
    assert stored is not None
    assert (stored.label, stored.status, stored.last_used_at) == ("Новое имя", CredentialStatus.auth_failed, _NOW)
    assert secret.reveal() == _TOKEN


async def test__user_deleted__credentials_and_bindings_go_with_them(world: World) -> None:
    project_id = await world.project(owner="boris")
    credential_id = await world.credential()
    await _bind(world, project_id, credential_id)

    async with world.sessions.use() as session:
        await session.execute(delete(UserRow).where(UserRow.id == "anna").execution_options(synchronize_session=False))
        credentials = (await session.execute(select(func.count()).select_from(GitCredentialRow))).scalar_one()
        bindings = (await session.execute(select(func.count()).select_from(GitRemoteBindingRow))).scalar_one()

    assert (credentials, bindings) == (0, 0)


async def test__bind__foreign_credential__is_not_found(world: World) -> None:
    project_id = await world.project()
    credential_id = await world.credential(_BORIS)

    with as_actor(_ANNA), pytest.raises(NotFoundError):
        await world.bindings.bind(project_id, credential_id, _REMOTE)


async def test__bind__credential_for_another_host__is_refused_and_nothing_is_stored(world: World) -> None:
    project_id = await world.project()
    credential_id = await world.credential(host="gitlab.com")

    with as_actor(_ANNA), pytest.raises(GitSyncError) as raised:
        await world.bindings.bind(project_id, credential_id, _REMOTE)

    assert raised.value.code is GitErrorCode.credential_host_mismatch
    assert await world.bindings.get(project_id) is None


async def test__bind__again__replaces_the_binding_and_unbind_removes_it(world: World) -> None:
    project_id = await world.project()
    first = await world.credential()
    second = await world.credential()
    await _bind(world, project_id, first)
    await _bind(world, project_id, second, parse_remote_url("https://github.com/hse/other.git"))

    binding = await world.bindings.get(project_id)
    assert binding is not None
    assert (binding.credential_id, binding.scheme, binding.host, binding.port, binding.bound_by) == (
        second,
        "https",
        "github.com",
        None,
        "anna",
    )
    with as_actor(_ANNA):
        await world.bindings.unbind(project_id)
    assert await world.bindings.get(project_id) is None
    assert [a for a, _ in await world.audit_actions()] == [AUDIT_BIND, AUDIT_BIND, AUDIT_UNBIND]


async def test__access__editor_of_the_bound_project__uses_the_secret_and_the_use_is_audited(world: World) -> None:
    project_id = await world.project(members={"boris": "editor"})
    credential_id = await world.credential()
    await _bind(world, project_id, credential_id)

    secret = await _secret(world, _BORIS, credential_id, project_id, _REMOTE)

    assert secret == _TOKEN
    with as_actor(_BORIS):
        found = await world.access.get(credential_id, project_id=project_id)
    assert found is not None
    events = await world.audit.query(AuditQuery(action_prefix=AUDIT_USE))
    assert [(e.actor_id, e.target) for e in events] == [("boris", str(credential_id))]
    assert events[0].details["via"] == "binding"
    assert events[0].details["project_id"] == str(project_id)


async def test__access__owner__uses_his_own_credential_and_it_is_audited_too(world: World) -> None:
    credential_id = await world.credential()

    assert await _secret(world, _ANNA, credential_id, None, _REMOTE) == _TOKEN

    events = await world.audit.query(AuditQuery(action_prefix=AUDIT_USE))
    assert [(e.actor_id, e.details["via"]) for e in events] == [("anna", "owner")]


@pytest.mark.parametrize("role", ["reader", "reviewer"])
async def test__access__reader_of_the_bound_project__is_refused_without_an_audit_event(world: World, role: str) -> None:
    project_id = await world.project(members={"carol": role})
    credential_id = await world.credential()
    await _bind(world, project_id, credential_id)

    with pytest.raises(NotFoundError):
        await _secret(world, _CAROL, credential_id, project_id, _REMOTE)
    with as_actor(_CAROL):
        assert await world.access.get(credential_id, project_id=project_id) is None

    assert await world.audit.query(AuditQuery(action_prefix=AUDIT_USE)) == []


async def test__access__not_a_member_or_not_bound__is_refused(world: World) -> None:
    bound = await world.project(members={"boris": "editor"})
    unbound = await world.project(members={"boris": "editor"})
    credential_id = await world.credential()
    await _bind(world, bound, credential_id)

    with pytest.raises(NotFoundError):
        await _secret(world, _DAN, credential_id, bound, _REMOTE)
    with pytest.raises(NotFoundError):
        await _secret(world, _BORIS, credential_id, unbound, _REMOTE)
    with pytest.raises(NotFoundError):
        await _secret(world, _BORIS, credential_id, None, _REMOTE)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/hse/course.git",
        "https://github.com:8443/hse/course.git",
        "ssh://git@github.com/hse/course.git",
        "http://github.com/hse/course.git",
    ],
)
async def test__access__another_host_port_or_scheme__is_refused_even_for_an_editor(world: World, url: str) -> None:
    project_id = await world.project(members={"boris": "editor"})
    credential_id = await world.credential()
    await _bind(world, project_id, credential_id)
    remote = parse_remote_url(url, allow_http=True)

    with pytest.raises(NotFoundError):
        await _secret(world, _BORIS, credential_id, project_id, remote)

    assert await world.audit.query(AuditQuery(action_prefix=AUDIT_USE)) == []


async def test__access__after_unbind__the_editor_loses_the_credential(world: World) -> None:
    project_id = await world.project(members={"boris": "editor"})
    credential_id = await world.credential()
    await _bind(world, project_id, credential_id)
    assert await _secret(world, _BORIS, credential_id, project_id, _REMOTE) == _TOKEN

    with as_actor(_ANNA):
        await world.bindings.unbind(project_id)

    with pytest.raises(NotFoundError):
        await _secret(world, _BORIS, credential_id, project_id, _REMOTE)


async def test__access__background_without_actor__only_through_a_binding(world: World) -> None:
    project_id = await world.project()
    credential_id = await world.credential()

    with pytest.raises(NotFoundError):
        await _secret(world, None, credential_id, project_id, _REMOTE)
    await _bind(world, project_id, credential_id)
    assert await _secret(world, None, credential_id, project_id, _REMOTE) == _TOKEN

    events = await world.audit.query(AuditQuery(action_prefix=AUDIT_USE))
    assert [e.actor_id for e in events] == [None]


@pytest.mark.parametrize("actor", [Actor.local(), Actor.guest("link-1")])
async def test__access__local_or_guest_actor__is_refused(world: World, actor: Actor) -> None:
    project_id = await world.project()
    credential_id = await world.credential()
    await _bind(world, project_id, credential_id)

    with pytest.raises(NotFoundError):
        await _secret(world, actor, credential_id, project_id, _REMOTE)


async def test__access__the_token_never_reaches_the_audit_or_the_logs(world: World) -> None:
    project_id = await world.project(members={"boris": "editor"})
    credential_id = await world.credential()

    with structlog.testing.capture_logs() as logs:
        await _bind(world, project_id, credential_id)
        await _secret(world, _BORIS, credential_id, project_id, _REMOTE)
        with as_actor(_ANNA):
            await world.repo.list()
            await world.repo.delete(credential_id)

    events = await world.audit.query(AuditQuery(limit=100))
    assert events
    assert _TOKEN not in json.dumps([e.details for e in events], default=str)
    assert _TOKEN not in json.dumps(logs, default=str)


async def test__usage__owner_sees_the_projects_of_his_credentials_only(world: World) -> None:
    project_id = await world.project()
    credential_id = await world.credential()
    await _bind(world, project_id, credential_id)

    with as_actor(_ANNA):
        mine = await world.usage.by_credential()
    with as_actor(_BORIS):
        theirs = await world.usage.by_credential()

    assert [u.project_id for u in mine[credential_id]] == [project_id]
    assert theirs == {}


async def test__credential_deleted__its_bindings_go_away(world: World) -> None:
    project_id = await world.project()
    credential_id = await world.credential()
    await _bind(world, project_id, credential_id)

    with as_actor(_ANNA):
        assert await world.repo.delete(credential_id) is True

    assert await world.bindings.get(project_id) is None
