# Testing Strategy

Local mode needs no external service: JSON persistence runs against `tmp_path`. Server mode adds Postgres and S3, which are exercised at a separate, explicitly marked level. Design of the data layer: `docs/design/persistence-server.md`.

## Three levels

| Level | Where | What runs | Needs |
|---|---|---|---|
| unit | `tests/unit/` | pure logic, fakes (`tests/fakes/`), no I/O beyond `tmp_path` | nothing |
| contract + integration | `tests/contract/`, `tests/integration/` | one port suite over every implementation (Json, InMemory); real FastAPI app with local container | nothing |
| pg / s3 | any dir, marker `pg` or `s3` | real Postgres (template DB with migrations applied), S3 via moto or MinIO, server container | `HSE_TEST_PG_DSN`, extra `server` |

Without `HSE_TEST_PG_DSN` the `pg` tests are skipped, never failed. The local mode must also pass in an environment without the `server` extra (separate CI job, `make test-no-server`).

## Test structure
```
tests/
├── conftest.py       # applies unit/integration markers by directory; registers tests/fixtures/* as pytest_plugins
├── fixtures/         # shared fixtures: app/DI container, pg (template DB), s3, two_actors
├── fakes/            # InMemory implementations of ports (owner taken from current_actor())
├── contract/         # PortContract base and per-port suites parametrised by implementation
├── factories/        # make_*() builders for domain entities and API payloads
├── unit/
└── integration/
```

## Markers
- `unit` / `integration` are applied automatically by directory.
- `pg`, `s3`: need the corresponding service; mark explicitly (or via the fixture module).
- Strict markers are on: register new ones in `pyproject.toml`.

## Contract suites
- A port with several implementations gets one `PortContract` subclass; the implementations are parameters, so Json, InMemory and Postgres prove the same behaviour.
- Every per-user port also has an isolation test with the `two_actors` helper: data written as actor A is invisible to actor B.
- A fake that diverges from the real implementation is a bug in the fake; the contract suite is what keeps them honest.

## Async hygiene
- `asyncio_mode = "auto"`; no manual `@pytest.mark.asyncio`.
- Slices that convert a sync port to async run the suite with `-W error::RuntimeWarning` (a never-awaited coroutine must fail the test).
- A test that touches the ambient transaction must not leak it: use the fixtures, do not open a `begin()` without closing it.

## Naming conventions
- Files: `test_*.py`
- Functions: `test__subject__condition__expectedresult` (no test classes, except contract base classes)

## Style
- One behavior per test; AAA (Arrange, Act, Assert)
- Fixtures for repeated setup; `pytest.mark.parametrize` with `pytest_lazy_fixtures.lf()` to deduplicate input/output variations
- `conftest.py` only for fixtures shared across modules
- Builders live in `tests/factories/` as plain `make_*()` functions, not ORM factory classes
- A timing test that fails once under machine load is not a defect until it fails alone

## Example
```python
async def test__get_by_id__other_actor__returns_none(repo, two_actors):
    owner, stranger = two_actors
    with as_actor(owner):
        saved = await repo.create(make_user())
    with as_actor(stranger):
        assert await repo.get_by_id(saved.id) is None
```

## Running tests (from `services/api`)
- **Everything**: `uv run --all-extras pytest tests`
- **A scope**: `uv run --all-extras pytest tests/unit/core --no-cov`
- **By marker**: `uv run --all-extras pytest -m unit tests`
- **With Postgres**: `HSE_TEST_PG_DSN=postgresql://... uv run --all-extras pytest -m pg --no-cov` (or `make test-pg`)
- Add `--frozen` when the lockfile must stay untouched.
