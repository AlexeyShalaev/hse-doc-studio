# Repository Pattern Standards

Repositories handle persistence. Two families exist and both follow the same port discipline:

- **Local mode** (default): synchronous JSON-file repositories in `infra/persistence/` (`data_dir` and the project folder). They stay as they are.
- **Server mode** (stage 2): `Sql*` repositories in `infra/db/repositories/`, async, behind the same protocols once a port has been converted. Design: `docs/design/persistence-server.md`.

## Core Principles

1. Repositories MUST return domain entities, NEVER ORM models.
2. Protocols live in `core/` (`core/repositories.py` or the owning package); implementations in `infra/`.
3. SQL implementations are prefixed with `Sql` (`SqlUserRepository`; the older project locator and ACL repositories keep `Postgres*`, do not add new ones); JSON ones keep the `Json*` naming of their neighbours.
4. Repositories are **APP-scope**: one instance per container, holding an `async_sessionmaker`, never a session. A request-scoped repository injected into an APP-scope service ends up with a dead session.
5. Each method runs in its own short transaction (`async with sessionmaker.begin()`), unless an ambient transaction is alive (see UoW below).
6. Only the use case decides that several writes are atomic. A repository NEVER calls `commit()`, `rollback()` or `refresh()` itself.
7. `use_cases` and `core` never import `sqlalchemy` or `infra` (the layer ratchet enforces it; allowlists only shrink).
8. The owner of per-user data comes from `current_actor()`, not from a method argument. No actor in server mode raises `ActorRequired`. `system_actor` is allowed only in allow-listed methods (scan, recovery, GC); background paths rebuild `Actor(kind=user, source=job)` from the job's `actor_id`.
9. ACL fields (owner, team, `shared_enabled`, persona, roles) live only in the database; `project.json` is a non-authoritative hint and the database value overwrites it.

## Protocol and implementation

```python
# core/users/repositories.py
class IUserRepository(Protocol):
    async def create(self, email: str, name: str) -> User: ...
    async def get_by_id(self, user_id: UUID) -> User | None: ...
    async def update(self, user: User) -> User: ...
```

```python
# infra/db/repositories/user.py
class SqlUserRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions  # wraps async_sessionmaker + ambient transaction

    @staticmethod
    def _to_entity(row: UserDB) -> User:
        return User(id=row.id, email=row.email, name=row.name, created_at=row.created_at)

    async def get_by_id(self, user_id: UUID) -> User | None:
        async with self._sessions.use() as session:
            row = await session.get(UserDB, user_id)
            return self._to_entity(row) if row else None

    async def update(self, user: User) -> User:
        async with self._sessions.use() as session:
            row = await session.get(UserDB, user.id)
            if row is None:
                raise UserNotFoundError(user.id)
            row.email, row.name = user.email, user.name
            await session.flush()
            return self._to_entity(row)
```

`SessionProvider.use()` yields the ambient session when a transaction is open and a fresh `sessionmaker.begin()` session otherwise. Always convert with `_to_entity` before leaving the `async with`; lazy attributes of a closed session must never leak.

## Ambient UoW

Multi-table writes use `IUnitOfWork` (`core/uow.py`). It only opens a transaction boundary; it does NOT create or expose repositories.

```python
# use_cases/projects/create.py
async def execute(self, ...) -> Project:
    async with self._uow.begin():
        project = await self._projects.create(...)
        await self._members.add_owner(project.id, actor.user_id)
        await self._audit.record(...)
    return project
```

- The open transaction lives in a `ContextVar`; repositories join it when alive.
- A finished transaction is flagged `closed`, so a background task that inherited the context never reuses a dead session.
- A nested `begin()` joins the outer one; commit happens only when the outermost block exits.
- Side effects outside the database (files, S3, mail, events) run after the block exits.

## Incorrect patterns

- Returning ORM models or omitting `_to_entity`.
- Naming a SQL implementation just `Repository`.
- `session.commit()` or `session.refresh()` inside a repository.
- Storing a session on the repository instance, or registering a repository in `Scope.REQUEST`.
- A UoW exposing `uow.users` style attributes or building repositories.
- Reading the owner from a request body instead of `current_actor()`.
- Importing `sqlalchemy` in `core/` or `use_cases/`.
- A `sync` method that does blocking database I/O. Ports that move to the database become `async` in their own behaviour-neutral PR, checked with `pytest -W error::RuntimeWarning`.

## Updates

Prefer accepting the entity and updating all fields (`update(user)`), or a narrow typed method for a partial change (`set_email(user_id, email)`). Do not pass untyped `**kwargs`.

## Contract tests

Every port with more than one implementation has a contract suite in `tests/contract/` parametrised over Json, InMemory and Postgres, plus an isolation test of two actors (see `backend-testing.md`).

## Checklist

- [ ] Protocol in `core/`, implementation in `infra/`, no ORM in the return types
- [ ] APP-scope, sessionmaker held, session per call or ambient
- [ ] No commit/rollback/refresh inside
- [ ] Owner from `current_actor()`, `ActorRequired` when absent
- [ ] Multi-table writes go through `IUnitOfWork.begin()` in the use case
- [ ] Migration added (skill `backend-add-migration`), one alembic head
- [ ] Contract test and two-actor isolation test
