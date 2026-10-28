# Docker and Makefile Workflow

Day-to-day backend work needs no Docker: `uv` and `pytest` are enough. Docker is for the server-mode stack (Postgres, S3, runners) and for project tooling (TeX images).

## Commands

From the repo root (see `make help`):
- `make install`, `make check`, `make test`, `make test-unit`: install, lint/type-check, tests.
- `make docs-lint`, `make docs-build`: site and docs gates.

From `services/api`:
- `make run-api`: run the API (local mode by default).
- `make fmt` / `make check`: format, ruff, mypy.
- `make test` / `make test-unit`: tests; server-mode targets (`test-pg`, `test-no-server`) arrive with the test-infrastructure slice.

## Dev infrastructure

`scripts/dev/` holds compose files for auxiliary services. Postgres and S3 for server-mode work run from a compose file there (the stand `scripts/dev/server-lite`: api in `server` + `AUTH__EXPERIMENTAL` and Postgres, `make server-lite-up`, then `server-lite-seed` for three demo users; the api port is published on the host loopback only). Rules:
- Use throwaway containers on dedicated ports for tests; never reuse the ports of containers that are already running on the machine; remove them afterwards.
- Test infrastructure ports differ from dev ports so both can run at once.
- Configuration comes from `HSE_STUDIO__*` environment variables, nested with double underscores (for example `HSE_STUDIO__DB__DSN`). Secrets (DB password, `SECRETS__KEY`) come from env or files, never from the repository.

## Migrations

Alembic runs through `uv run alembic` against a database reachable by DSN; there is no `.env.tools` and no image-based generator. See skill `backend-add-migration`. There is one revision chain and one head; CI fails on two heads.

## Server stack (compose)

The api runs as a single replica (Kubernetes: `replicas: 1`, `strategy: Recreate`). Compose may auto-migrate at start under an advisory lock; Helm uses a pre-upgrade migration job as the only mechanism.
