# Testing Strategy

This service has no SQL database — persistence is JSON-file-based, wired through a real
Dishka DI container backed by `tmp_path`. Because of that, **integration is cheap here**:
hitting the real FastAPI app end-to-end also exercises the real use case and the real
JSON repo, in one process, in milliseconds. Default to integration; reach for a unit test
only when integration genuinely can't cover the case.

## Test Structure

Tests mirror the source tree, grouped by folder/subfolder for navigation:
```
tests/
├── conftest.py           # only pytest_plugins wiring + collection hooks — no test logic
├── fixtures/              # shared fixture modules, registered via pytest_plugins
├── factories/              # plain builder functions for domain objects + API payloads
├── unit/                  # mirrors hse_doc_studio/** 1:1
│   ├── core/
│   ├── infra/
│   └── use_cases/
└── integration/
    └── api/                # one folder per API resource, mirrors api/routers/v1/*
        ├── projects/
        ├── documents/
        └── ...
```

## When to reach for `unit/` instead of `integration/`

Only when at least one of these is true:
- **Pure logic** with many branches/edge cases that are awkward to drive through HTTP
  (parsers, resolvers, value objects, template rendering helpers).
- **A real external dependency has to be faked at the boundary** because it can't run in
  CI/dev without heavy infra: Docker (`DockerCompileExecutor`, `LanguageToolContainerManager`),
  real subprocess/`docker` CLI calls (`infra/docker/cli.py`), the real AI provider SDKs.
  Fake at the narrowest seam available (an injected `httpx.Client`, a Protocol, a free
  function via `monkeypatch`/`pytest-mock`) — not with a network-level trick.
- The use case exposes a **private helper** not reachable end-to-end at all.

Everything else goes through `tests/fixtures/app.py`'s `test_app` (a real `httpx.AsyncClient`
over the real FastAPI app + DI container) under `tests/integration/api/<resource>/`.

## Markers

`unit`/`integration` markers are applied **automatically** by `tests/conftest.py`'s
`pytest_collection_modifyitems`, based on whether a test lives under `tests/unit/` or
`tests/integration/` — don't add `@pytest.mark.unit`/`@pytest.mark.integration` by hand.

## Naming Conventions

- **Files**: `test_*.py`, one file per source module (`hse_doc_studio/a/b.py` →
  `tests/unit/a/test_b.py`). A file may cover more than its one obvious module when several
  tests share a cross-cutting subject (e.g. a small invariant shared by a family of sibling
  tool files) — prefer this over a pile of near-empty files, but don't let it become a
  junk drawer.
- **Functions**: `test__<subject>__<condition>__<expected_result>` (double-underscore
  separated). The subject is what's actually being exercised — a function, a use case, a
  class method — not the test file's name.
- **One behavior per test.** A test that chains several use case calls just to reach the
  interesting state (e.g. create → rename → delete) should be split: each behavior gets
  its own test, arranging its own precondition directly rather than depending on a prior
  test's side effect or assertion.
- **AAA**: Arrange → Act → Assert, separated by blank lines. Comments only where the
  *why* isn't obvious from the code (a workaround, a non-obvious invariant).

## Best Practices

- **Fixtures for repeated setup.** `conftest.py` is for fixtures shared across *multiple
  modules* — a fixture used by only one file belongs in that file, not promoted upward.
  A subfolder-local `conftest.py` (e.g. `tests/unit/use_cases/chat/conftest.py`) is the
  right place for fixtures shared only within that subfolder.
- **Factories**: plain builder functions in `tests/factories/` (`make_project`,
  `make_document`, `make_check_rule`, ...) build domain dataclasses; `project_api_payload`-style
  helpers build raw API request bodies. Reuse these instead of hand-rolling dataclasses
  inline. (No `factory_boy`/ORM-style factories — the domain models are plain/frozen
  dataclasses with nested tuples and dicts that don't compose well with that pattern; a
  builder function stays simpler.)
- **`pytest.mark.parametrize` + `pytest_lazy_fixtures.lf()`**: use to dedupe tests that
  differ only by input/output, including cases where each variant needs a differently
  set-up fixture (`lf("fixture_name")` inside the parametrize list).
- **`cases.py`**: for a scenario matrix with many combinations (e.g. many check-engine
  rule/input/expected-result combos), declare the data as a module-level list of
  `pytest.param(..., id=...)` in a `cases.py` next to the tests, and keep the test body
  itself generic — decouples case *data* from test *logic*.
- **Async**: `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed.
- **Libraries available**: `pytest-lazy-fixtures` (parametrize dedup), `pytest-mock`
  (`mocker` fixture — prefer over raw `unittest.mock.patch` for new tests), `pytest-httpx`
  (mock outbound HTTP — AI provider calls, LanguageTool's injected `httpx.Client`),
  `faker` (realistic random test data), `freezegun` (pin `datetime.now()`), `dirty-equals`
  (partial/structural assertions on API JSON responses — ignore volatile fields like
  timestamps/generated ids without hand-rolling comparisons), `pytest-timeout` (global
  30s ceiling via `--timeout=30` in `addopts` — a real safety net, not decoration: a test
  that spawns a thread/process and never joins it can silently degrade every test that
  runs afterward in the same session; if you add code that can legitimately run long,
  make sure whatever's left behind is *idle*, e.g. blocked on a wait rather than busy-spinning).

## Running Tests

- **Local**: `uv run --all-extras pytest tests` (or scope to a path, e.g.
  `uv run --all-extras pytest tests/unit/core`).
- **Fast iteration**: add `--no-cov` to skip coverage instrumentation.
- **Single service**: `uv run pytest tests` (see also `Makefile`'s `test` target).
