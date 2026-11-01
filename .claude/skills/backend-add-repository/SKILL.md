---
name: backend-add-repository
description: Add a new repository for a domain entity — protocol in core/, ORM model, Postgres implementation, migration, contract tests.
---

# Skill: Add Repository

Procedure for adding a new repository for a domain entity.

## Procedure

1. **Define Protocol**:
   In `core/<entity>/repositories.py`:
   ```python
   class NounRepository(Protocol):
       async def create(self, entity: Noun) -> Noun: ...
       async def get_by_id(self, id: UUID) -> Noun | None: ...
   ```

2. **Define ORM Model**:
   In `infra/db/orm/<entity>.py`:
   ```python
   class NounDB(BaseTable):
       __tablename__ = "nouns"
       id: Mapped[UUID] = mapped_column(primary_key=True)
       ...
   ```

3. **Implement Repository** (APP-scope: hold the sessionmaker provider, not a session; see `.claude/rules/backend-repositories.md`):
   In `infra/db/repositories/<entity>.py`:
   ```python
   class SqlNounRepository:
       def __init__(self, sessions: SessionProvider) -> None:
           self._sessions = sessions

       async def create(self, entity: Noun) -> Noun:
           async with self._sessions.use() as session:
               row = NounDB(...)
               session.add(row)
               await session.flush()
               return self._to_entity(row)
   ```
   The owner of per-user data comes from `current_actor()` (`ActorRequired` when absent). No commit/refresh in the repository.

4. **Register in DI**:
   Provide it with `Scope.APP` in the server provider (`infra/di`). Do not add it to a UoW: `IUnitOfWork` only opens the ambient transaction.

5. **Generate Migration**:
   Follow skill `backend-add-migration` (`uv run alembic`, one head).

6. **Add Tests**:
   Extend or add the contract suite in `tests/contract/` (Json, InMemory, Postgres) and a two-actor isolation test; Postgres cases use marker `pg`.
