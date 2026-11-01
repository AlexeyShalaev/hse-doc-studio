---
name: backend-add-migration
description: Add an Alembic migration to the server-mode database (autogenerate against a throwaway Postgres, keep a single head, verify upgrade/downgrade and drift).
---

# Skill: Add Alembic Migration

Server mode keeps one SQLAlchemy `MetaData` and one alembic revision chain in `services/api` (`hse_doc_studio/infra/db/migrations/`, `alembic.ini`; миграции лежат в пакете, чтобы попасть в образ). Design and table ownership: `docs/design/persistence-server.md`.

## Prerequisites
- Extra `server` installed (`uv sync --all-extras`), Docker available.
- The foundation slice (engine, `infra/db/migrations/`, `alembic.ini`) is in your branch. Before it, there is nothing to migrate.

## Procedure

1. **Change the ORM model** in `infra/db/orm/` (naming convention is set on `MetaData`, do not name constraints by hand). Table owner decides the module; do not edit another zone's table without agreeing on the contract.

2. **Start a throwaway Postgres** on a free port of your own range and export the DSN:
   ```bash
   docker run -d --rm --name hse-mig-pg -e POSTGRES_PASSWORD=pg -p 19150:5432 postgres:16
   export HSE_STUDIO__DB__DSN=postgresql+asyncpg://postgres:pg@localhost:19150/postgres
   ```

3. **Bring the database to the current head, then autogenerate** (from `services/api`):
   ```bash
   uv run --frozen --all-extras alembic upgrade head
   uv run --frozen --all-extras alembic revision --autogenerate -m "<short_message>"
   ```
   The file lands in `hse_doc_studio/infra/db/migrations/versions/` as `YYYY_MM_DD_HHMM-<id>_<message>.py`.

4. **Review the generated code.** Autogenerate misses data migrations, server defaults changes and renames. Check:
   - `op.f()` is used for index/key names (naming convention);
   - `upgrade()` and `downgrade()` are both correct;
   - expand/contract: a release must work with the schema of the previous one (add nullable or defaulted column first, drop in a later release);
   - tables the app role must not modify (`audit_log`) keep their restricted grants.

5. **Verify**:
   ```bash
   uv run --frozen --all-extras alembic upgrade head
   uv run --frozen --all-extras alembic downgrade -1 && uv run --frozen --all-extras alembic upgrade head
   uv run --frozen --all-extras alembic heads        # exactly one head
   uv run --frozen --all-extras alembic check        # no drift between models and schema
   ```
   Then run the `pg` tests (`HSE_TEST_PG_DSN=... pytest -m pg --no-cov`).

6. **Clean up**: `docker rm -f hse-mig-pg`.

## Common issues
- **Two heads** after a merge: rebase onto the latest chain and set `down_revision` to the real head; never merge-revision silently.
- **Drift in `alembic check`**: a model change without a revision, or a hand-edited migration that disagrees with the models.
- **Port conflict**: pick another port from your range; do not stop containers you did not start.
