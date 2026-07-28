# Contributing to hse-doc-studio Backend

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)

### Install dependencies

```bash
make install
```

### Run development server

```bash
make run-api
```

## Code Style

We use **Ruff** for linting and formatting, and **Mypy** for type checking.

```bash
make fmt    # format with pre-commit (ruff + mypy)
```

## Testing

```bash
make test
```

- One behavior per test
- AAA pattern (Arrange → Act → Assert)
- Fixtures for repeated setup
- Use `pytest.mark.parametrize` with `pytest_lazy_fixtures.lf()` to deduplicate tests that differ only by input/output
- Naming: `test__subject__condition__expectedresult`
- `conftest.py` only for fixtures shared across multiple modules; otherwise keep fixtures in local test files

## Commit Messages

We use **Conventional Commits** (single-line only):

```
feat(backend): add project lifecycle use case
fix(compile): handle xelatex timeout
```

## Architecture

- `hse_doc_studio/core/` — Domain entities and protocols (no external deps)
- `hse_doc_studio/use_cases/` — Application business logic
- `hse_doc_studio/infra/` — Filesystem store, Docker runner, DI
- `hse_doc_studio/api/` — FastAPI routers and schemas
