---
name: backend-run-tests
description: Run backend tests — local pytest only (no DB/Docker test infra needed), troubleshooting port conflicts and slow/hanging tests.
---

# Skill: Run Tests

Guidelines for executing tests for `hse-doc-studio`.

This service has no SQL database and no Redis/Kafka — persistence is JSON-file-based
against `tmp_path`, and the DI container is wired up per-test in
`tests/fixtures/app.py`/`tests/conftest.py`. There is no Docker-based test-infra step:
everything runs locally via `uv run pytest`.

## Running tests

- **Prerequisites**: dependencies installed via `uv` (`uv sync --all-extras` from
  `services/api`).
- **Run everything**:
  ```bash
  uv run --all-extras pytest tests
  ```
- **Run a scope** (much faster while iterating):
  ```bash
  uv run --all-extras pytest tests/unit/core --no-cov
  uv run --all-extras pytest tests/integration/api/projects --no-cov
  ```
- **Run by marker** — `unit`/`integration` markers are applied automatically by
  `tests/conftest.py` based on directory (`tests/unit/**` vs `tests/integration/**`), no
  manual `@pytest.mark.unit` needed:
  ```bash
  uv run --all-extras pytest -m unit tests
  ```
- **Skip coverage** for faster local iteration: add `--no-cov` (coverage + `--cov-fail-under`
  are on by default via `addopts`).

## Troubleshooting

- **Asyncio**: `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed, `async def
  test_...` just works.
- **A test hangs / the full suite stalls partway through**: this project runs the whole
  `tests/` tree in one pytest process, so a test that spawns a background thread/process
  and doesn't join it leaves a live thread competing for the GIL for the rest of the run —
  it can make a *later*, unrelated test look slow or timed-out even though that later test
  is innocent. `--timeout=30` (via `pytest-timeout`) is set globally so a real hang fails
  loudly with a thread-dump instead of hanging forever; if you see a timeout, check
  `tests/unit/infra/checks/test_python_engine.py`'s timeout test for the pattern to follow
  (a bounded loop / a blocking wait, never `while True` or a busy CPU spin) before assuming
  it's a fluke.
- **A test touches real OS state it shouldn't** (`shutil.which`, real subprocess/docker,
  real network): that's a boundary that should be faked (see `.claude/rules/backend-testing.md`),
  not a flake to retry around.
