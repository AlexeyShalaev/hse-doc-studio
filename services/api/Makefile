# ============================================================
# OS Detection
# ============================================================
ifeq ($(OS),Windows_NT)
	DETECTED_OS := Windows
else
	UNAME := $(shell uname 2>/dev/null || echo "Unknown")
	ifeq ($(UNAME),Linux)
		DETECTED_OS := Linux
	else ifeq ($(UNAME),Darwin)
		DETECTED_OS := macOS
	else
		DETECTED_OS := Unix
	endif
endif

# ============================================================
# Targets
# ============================================================

.PHONY: fmt check install reinstall-custom-libs run-api test test-unit test-pg test-s3 test-no-server

fmt:  ##@Code Check code with pre-commit
	uv run --extra dev python -m pre_commit run --all-files

check:  ##@Code Lint and type check, read-only (same steps as CI)
	uv run ruff check
	uv run ruff format --check
	uv run mypy hse_doc_studio

install: ##@App Install raw dependencies
	uv sync --all-extras

reinstall-custom-libs: ##@App Reinstall all local custom libraries and sync env
	uv sync --all-extras $(CUSTOM_UV_REINSTALL_ARGS)

run-api:	##@App Run API server
	uv run --extra api python -m hse_doc_studio.api.entrypoint

test:	##@App Test application
	uv run --all-extras pytest tests

test-unit:	##@App Run unit tests only (fast, no coverage)
	uv run --all-extras pytest -m unit --no-cov

# Postgres и MinIO для pg/s3-тестов поднимает `docker compose -f scripts/dev/compose.pg.yml up -d`.
HSE_TEST_PG_DSN ?= postgresql://postgres:postgres@localhost:15432/postgres

test-pg:	##@App Run pg tests (needs Postgres, see scripts/dev/compose.pg.yml)
	HSE_TEST_PG_DSN=$(HSE_TEST_PG_DSN) uv run --all-extras pytest -m pg --no-cov

test-s3:	##@App Run s3 tests (moto in process; MinIO via HSE_TEST_S3_ENDPOINT)
	uv run --all-extras pytest -m s3 --no-cov

test-no-server:	##@App Local mode must pass without the server extra
	uv run --extra api --extra test pytest -m "not pg and not s3" --no-cov
