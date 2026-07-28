# Testing Strategy

`hse-doc-studio` has no SQL database, Redis, or Kafka — persistence is JSON-file-based
against `tmp_path`. There is no Docker-based test infra: everything runs locally via `uv run pytest`.

## Test structure
```
tests/
├── conftest.py       # applies unit/integration markers by directory; registers tests/fixtures/* as pytest_plugins
├── fixtures/          # fixtures shared across many modules (e.g. test_app / DI container)
├── factories/          # make_*() builder functions for domain entities and API payloads
├── unit/               # unit tests (mock external deps)
└── integration/        # integration tests (real FastAPI app + JSON persistence against tmp_path, no Docker)
```

## Markers
- `@pytest.mark.unit` / `@pytest.mark.integration` are applied automatically by `tests/conftest.py`
  based on directory — no manual marking needed.

## Naming conventions
- Files: `test_*.py`
- Functions: `test__subject__condition__expectedresult` (no test classes)

## Style
- One behavior per test
- AAA pattern (Arrange → Act → Assert)
- Fixtures for repeated setup
- Use `pytest.mark.parametrize` with `pytest_lazy_fixtures.lf()` to deduplicate tests that differ only by input/output
- `conftest.py` only for fixtures shared across multiple modules; otherwise keep fixtures in local test files
- Data builders live in `tests/factories/` as plain `make_*()` functions, not ORM factory classes

## Example unit test
```python
async def test__check_model_access__service_has_no_access_to_model__raises_model_not_allowed(
    permissions_repo, service_with_single_model_access
):
    with pytest.raises(ModelNotAllowedError):
        await permissions_repo.check_model_access(
            model_name="not-allowed-model",
            service_id=service_with_single_model_access,
        )
```

## Running tests
- **Everything**: `uv run --all-extras pytest tests` (from `services/api`)
- **A scope** (faster while iterating): `uv run --all-extras pytest tests/unit/core --no-cov`
- **By marker**: `uv run --all-extras pytest -m unit tests`
