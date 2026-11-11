"""Удаление человека и выгрузка его данных против настоящего Postgres."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import AgentPersona
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.lifecycle import pseudonym_for
from hse_doc_studio.core.mail.journal import MailCause, MailStatus
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.auth import SqlAuditLog
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.lifecycle import SqlUserLifecycle
from hse_doc_studio.infra.db.repositories.mail_log import SqlMailLogRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from hse_doc_studio.infra.persistence.agent_persona import JsonAgentPersonaRepository, user_data_folder
from hse_doc_studio.use_cases.admin.lifecycle import DeleteUserUC
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.contract.test_mail_log_contract import make_entry

pytestmark = pytest.mark.pg

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


async def _exec(engine: AsyncEngine, sql: str, **params: object) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


async def _count(engine: AsyncEngine, sql: str, **params: object) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(sql), params)).scalar_one())


class _World:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessions = SessionProvider(create_sessionmaker(engine))
        self.users = SqlUserRepository(self.sessions)
        self.audit = SqlAuditLog(self.sessions)
        self.lifecycle = SqlUserLifecycle(self.sessions)
        self.mail_log = SqlMailLogRepository(self.sessions)
        self.delete = DeleteUserUC(self.users, self.lifecycle, self.audit, SqlUnitOfWork(self.sessions))
        self.admin = Actor.user("boss", is_instance_admin=True)

    async def user(self, user_id: str, *, disabled: bool = True) -> None:
        user = make_user(user_id)
        await self.users.add(user)
        if disabled:
            await _exec(self.engine, "UPDATE users SET status = 'disabled' WHERE id = :u", u=user_id)

    async def seed_personal_data(self, user_id: str) -> None:
        e = self.engine
        await _exec(
            e,
            "INSERT INTO api_tokens (id, user_id, name, token_hash, prefix, scopes, created_at) "
            "VALUES (:i, :u, 'cli', :h, 'hse_', ARRAY['api'], now())",
            i=f"t-{user_id}",
            u=user_id,
            h=f"hash-{user_id}",
        )
        await _exec(
            e,
            "INSERT INTO sessions (id_hash, user_id, csrf_token, created_at, last_seen_at, expires_at) "
            "VALUES (:h, :u, 'c', now(), now(), now() + interval '1 day')",
            h=f"s-{user_id}",
            u=user_id,
        )
        await _exec(e, "INSERT INTO user_settings (user_id, key, value) VALUES (:u, 'k', '1')", u=user_id)
        await _exec(
            e,
            "INSERT INTO mail_outbox (id, kind, to_email, link, created_at, expires_at) "
            "VALUES (:i, 'verify', :m, 'x', now(), now() + interval '1 day')",
            i=f"m-{user_id}",
            m=make_user(user_id).email,
        )


async def test__delete__personal_data_and_secrets_erased(pg_migrated_engine: AsyncEngine) -> None:
    w = _World(pg_migrated_engine)
    await w.user("boss", disabled=False)
    await w.user("u1")
    await w.seed_personal_data("u1")
    await w.seed_personal_data("u1x") if False else None

    await w.delete.execute(w.admin, "u1")

    e = pg_migrated_engine
    assert await _count(e, "SELECT count(*) FROM users WHERE id = 'u1'") == 0
    for table in ("api_tokens", "sessions", "user_settings"):
        assert await _count(e, f"SELECT count(*) FROM {table} WHERE user_id = 'u1'") == 0
    assert await _count(e, "SELECT count(*) FROM mail_outbox") == 0
    assert await _count(e, "SELECT count(*) FROM users WHERE id = 'boss'") == 1


async def test__delete__names_quotas_and_personas_erased(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> None:
    w = _World(pg_migrated_engine)
    w.lifecycle = SqlUserLifecycle(w.sessions, tmp_path)
    w.delete = DeleteUserUC(w.users, w.lifecycle, w.audit, SqlUnitOfWork(w.sessions))
    await w.user("boss", disabled=False)
    await w.user("u1")
    await w.user("u2", disabled=False)
    project = uuid.uuid4()
    await _exec(
        pg_migrated_engine,
        "INSERT INTO projects (id, name, owner_user_id, workspace_path, kind, lang) "
        "VALUES (:p, 'p', 'u2', '/x', 'thesis', 'ru')",
        p=project,
    )
    await _exec(
        pg_migrated_engine,
        "INSERT INTO compile_records (id, project_id, doc_id, engine, status, actor_id, actor_name, started_at) "
        "VALUES (:i, :p, 'd', 'xelatex', 'ok', 'u1', 'Иван Петров', now())",
        i=uuid.uuid4(),
        p=project,
    )
    await _exec(
        pg_migrated_engine,
        "INSERT INTO quotas (owner_kind, owner_id, resource, period, hard_limit) VALUES "
        "('user', 'u1', 'compile', 'day', 5), ('user', 'u2', 'compile', 'day', 5)",
    )
    folder = user_data_folder(tmp_path, "u1")
    persona = AgentPersona(id=uuid.uuid4(), label="Строгий", description="", instruction="секрет", created_at=NOW)
    JsonAgentPersonaRepository(folder).create(persona)
    exported = await w.lifecycle.export("u1")
    assert [p["instruction"] for p in exported["agent_personas"]] == ["секрет"]  # type: ignore[union-attr, index]

    await w.delete.execute(w.admin, "u1")

    e = pg_migrated_engine
    assert await _count(e, "SELECT count(*) FROM compile_records WHERE actor_name IS NOT NULL") == 0
    assert await _count(e, "SELECT count(*) FROM compile_records") == 1
    assert await _count(e, "SELECT count(*) FROM quotas WHERE owner_id = 'u1'") == 0
    assert await _count(e, "SELECT count(*) FROM quotas WHERE owner_id = 'u2'") == 1
    assert not folder.exists()


async def test__delete__audit_anonymized_not_erased(pg_migrated_engine: AsyncEngine) -> None:
    w = _World(pg_migrated_engine)
    await w.user("boss", disabled=False)
    await w.user("u1")
    await w.audit.record("auth.login", actor_id="u1", details={"ip": "10.0.0.1", "method": "password"})
    await w.audit.record("admin.user_disabled", actor_id="boss", target="u1", details={"email": "u1@example.org"})

    await w.delete.execute(w.admin, "u1")

    pseudonym = pseudonym_for("u1")
    assert (
        await _count(pg_migrated_engine, "SELECT count(*) FROM audit_log WHERE actor_id = 'u1' OR target = 'u1'") == 0
    )
    login = (await w.audit.list(action="auth.login"))[0]
    disabled = (await w.audit.list(action="admin.user_disabled"))[0]
    assert (login.actor_id, dict(login.details)) == (pseudonym, {"method": "password"})
    assert (disabled.actor_id, disabled.target, dict(disabled.details)) == ("boss", pseudonym, {})
    deleted = (await w.audit.list(action="admin.user_deleted"))[0]
    assert deleted.target == pseudonym


async def test__delete__sole_project_owner_blocked_until_projects_gone(pg_migrated_engine: AsyncEngine) -> None:
    w = _World(pg_migrated_engine)
    await w.user("boss", disabled=False)
    await w.user("u1")
    project = uuid.uuid4()
    await _exec(
        pg_migrated_engine,
        "INSERT INTO projects (id, name, owner_user_id, workspace_path, kind, lang) "
        "VALUES (:p, 'p', 'u1', '/x', 'thesis', 'ru')",
        p=project,
    )

    with pytest.raises(IdentityError) as err:
        await w.delete.execute(w.admin, "u1")
    assert err.value.code is IdentityErrorCode.user_has_projects
    assert await _count(pg_migrated_engine, "SELECT count(*) FROM users WHERE id = 'u1'") == 1

    await _exec(pg_migrated_engine, "DELETE FROM projects WHERE id = :p", p=project)
    await w.delete.execute(w.admin, "u1")
    assert await _count(pg_migrated_engine, "SELECT count(*) FROM users WHERE id = 'u1'") == 0


async def test__delete__sole_org_owner_blocked_but_shared_ownership_allowed(pg_migrated_engine: AsyncEngine) -> None:
    w = _World(pg_migrated_engine)
    await w.user("boss", disabled=False)
    await w.user("u1")
    await w.user("u2", disabled=False)
    await _exec(pg_migrated_engine, "INSERT INTO orgs (id, slug, name) VALUES ('o1', 'o1', 'O1')")
    await _exec(pg_migrated_engine, "INSERT INTO org_members (org_id, user_id, role) VALUES ('o1', 'u1', 'owner')")

    assert (await w.lifecycle.blockers("u1")).orgs == 1

    await _exec(pg_migrated_engine, "INSERT INTO org_members (org_id, user_id, role) VALUES ('o1', 'u2', 'owner')")
    assert (await w.lifecycle.blockers("u1")).orgs == 0
    await w.delete.execute(w.admin, "u1")

    assert await _count(pg_migrated_engine, "SELECT count(*) FROM org_members WHERE org_id = 'o1'") == 1


async def test__delete__direct_project_grant_removed(pg_migrated_engine: AsyncEngine) -> None:
    w = _World(pg_migrated_engine)
    await w.user("boss", disabled=False)
    await w.user("u1")
    await w.user("u2", disabled=False)
    project = uuid.uuid4()
    await _exec(
        pg_migrated_engine,
        "INSERT INTO projects (id, name, owner_user_id, workspace_path, kind, lang) "
        "VALUES (:p, 'p', 'u2', '/x', 'thesis', 'ru')",
        p=project,
    )
    await _exec(
        pg_migrated_engine,
        "INSERT INTO project_members (project_id, principal_kind, principal_id, role) "
        "VALUES (:p, 'user', 'u1', 'editor')",
        p=project,
    )

    await w.delete.execute(w.admin, "u1")

    assert await _count(pg_migrated_engine, "SELECT count(*) FROM project_members") == 0


async def test__delete__mail_to_the_person_erased_and_his_calls_lose_the_actor(pg_migrated_engine: AsyncEngine) -> None:
    w = _World(pg_migrated_engine)
    await w.user("boss", disabled=False)
    await w.user("u1")
    by_id = await w.mail_log.add(make_entry("old-address@example.org", to_user_id="u1"))
    by_address = await w.mail_log.add(make_entry("U1@Example.Test"))
    invited_by_u1 = await w.mail_log.add(make_entry("guest@example.org", cause=MailCause.user, actor_user_id="u1"))
    other = await w.mail_log.add(make_entry("boss@example.test", to_user_id="boss", actor_user_id="boss"))

    await w.delete.execute(w.admin, "u1")

    assert await w.mail_log.get(by_id) is None
    assert await w.mail_log.get(by_address) is None
    kept = await w.mail_log.get(invited_by_u1)
    assert kept is not None
    assert (kept.to_email, kept.actor_user_id) == ("guest@example.org", None)
    untouched = await w.mail_log.get(other)
    assert untouched is not None
    assert untouched.actor_user_id == "boss"


async def test__export__lists_mail_to_the_person_without_parameters(pg_migrated_engine: AsyncEngine) -> None:
    w = _World(pg_migrated_engine)
    await w.user("u1", disabled=False)
    await w.mail_log.add(make_entry("u1@example.test", template="reset_password", subject="Сброс пароля"))
    await w.mail_log.add(make_entry("someone@example.org", minutes=1, to_user_id="u1", status=MailStatus.failed))
    await w.mail_log.add(make_entry("guest@example.org", minutes=2, actor_user_id="u1"))

    data = await w.lifecycle.export("u1")

    mail = data["mail"]
    assert [(m["to_email"], m["status"]) for m in mail] == [  # type: ignore[union-attr, index]
        ("someone@example.org", "failed"),
        ("u1@example.test", "sent"),
    ]
    assert mail[1] == {  # type: ignore[index]
        "at": "2026-11-11T12:00:00+00:00",
        "template": "reset_password",
        "lang": "ru",
        "to_email": "u1@example.test",
        "subject": "Сброс пароля",
        "status": "sent",
        "reason": None,
    }


async def test__export__contains_own_data_without_secrets(pg_migrated_engine: AsyncEngine) -> None:
    w = _World(pg_migrated_engine)
    await w.user("u1", disabled=False)
    await w.seed_personal_data("u1")
    await w.audit.record("auth.login", actor_id="u1")

    data = await w.lifecycle.export("u1")

    assert data["profile"]["id"] == "u1"  # type: ignore[index]
    assert [t["name"] for t in data["api_tokens"]] == ["cli"]  # type: ignore[index, union-attr]
    assert data["settings"] == {"k": 1}
    assert [a["action"] for a in data["audit"]] == ["auth.login"]  # type: ignore[union-attr]
    flat = repr(data)
    assert "hash-u1" not in flat
    assert "s-u1" not in flat


async def test__every_foreign_key_to_users__cascades_so_new_secret_tables_cannot_outlive_a_user(
    pg_migrated_engine: AsyncEngine,
) -> None:
    query = """
        SELECT c.conrelid::regclass::text AS tbl, c.confdeltype::text
        FROM pg_constraint c
        WHERE c.contype = 'f' AND c.confrelid = 'users'::regclass
    """
    async with pg_migrated_engine.connect() as conn:
        rules = dict((await conn.execute(text(query))).all())

    # projects.owner_user_id намеренно RESTRICT: владелец проекта сначала меняется (DeleteUserUC проверяет это).
    wrong = {t: k for t, k in rules.items() if k not in ("c", "n") and t != "projects"}
    assert wrong == {}
    assert rules["projects"] == "r"
