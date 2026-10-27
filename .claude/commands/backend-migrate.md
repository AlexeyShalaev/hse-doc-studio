---
description: Add a new Alembic migration for the server-mode database.
---

# /migrate command

**Purpose**: Add an Alembic migration to the single revision chain of `services/api`.

**Usage**: follow skill `backend-add-migration` (throwaway Postgres, `uv run alembic revision --autogenerate`, no `.env.tools`).

**Rules**:
- Check for naming conventions (`op.f()`).
- Verify `upgrade` and `downgrade`, exactly one head, `alembic check` without drift.
