# Contributing to hse-doc-studio

Thank you for your interest in contributing! This document covers everything you need to get started.

## Development setup

```bash
git clone https://github.com/AlexeyShalaev/hse-doc-studio.git
cd hse-doc-studio
make install                     # uv sync (backend) + pnpm install (web-app)
uv run --project services/api pre-commit install --install-hooks   # pre-commit + commit-msg hooks (config at repo root)
```

## Running checks

```bash
make check       # ruff lint + format check + mypy (backend), eslint + tsc (web-app)
make test        # full suite of both services
make test-unit   # backend unit tests only (fast)
make fmt-services # autofix: pre-commit (backend), eslint --fix + prettier (web-app)
make hadolint    # lint the Dockerfile with the same config CI uses
```

## Code style

- **Type hints** on all functions and methods, including tests
- **Line length** — 120 characters (ruff enforced)
- **Quotes** — double quotes (ruff enforced)
- **No comments** unless the *why* is non-obvious (workaround, subtle invariant)
- **No `datetime.utcnow()`** — use timezone-aware `datetime.now(UTC)`
- **No `Any`** — avoid unless absolutely necessary

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/) are enforced by pre-commit:

| Prefix | Use for |
|--------|---------|
| `feat:` | New feature or behaviour |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `test:` | Test additions or changes |
| `refactor:` | Code restructure, no behaviour change |
| `perf:` | Performance improvement |
| `chore:` | Build, tooling, CI |

Breaking changes: add `!` after the type (`feat!:`) or include a `BREAKING CHANGE:` footer.

## Pull requests

1. Fork the repository
2. Create a branch from `master`: `git checkout -b feat/DOC-42__my-feature`
3. Make your changes with tests
4. Run `make check && make test-unit` locally
5. Open a PR against `master`

Do **not** edit `CHANGELOG.md` by hand — it is generated from the curated release notes
(see *Releasing* below).

## Architecture principles

This project follows Onion Architecture — dependency direction always points inward:
`api` → `use_cases` → `core`.

- **No infrastructure in domain/application**: `core/` and `use_cases/` must not import from `infra/`
- **Repositories return domain entities**: never leak persistence models out of a repository
- **Use cases depend on protocols**: never on concrete infrastructure classes

Per-service notes:

- [services/api/CONTRIBUTING.md](services/api/CONTRIBUTING.md) — Python FastAPI backend
- [services/web-app/CONTRIBUTING.md](services/web-app/CONTRIBUTING.md) — React TypeScript frontend

## Releasing (maintainers only)

Versioning and tagging are automated via
[Release Please](https://github.com/googleapis/release-please); the release notes are
hand-written.

1. Merge a PR with Conventional Commits into `master`.
2. Release Please opens (or updates) a release PR that bumps the version. Its own commit-derived
   summary is a **draft for you to read**, not the text that ships.
3. **Write the notes by hand in that release PR** — this is the only step that isn't automated:

   ```bash
   git checkout release-please--branches--master   # the branch of the release PR
   make release-notes                              # seeds an empty entry for the new version
   # write one bullet per user-visible change, ru AND en, in release-notes.json
   make changelog                                  # regenerates CHANGELOG.md from it
   ```

   ```json
   {
     "version": "0.2.0",
     "date": "2026-08-01",
     "notes": [{ "ru": "Что изменилось для пользователя", "en": "What changed for the user" }]
   }
   ```

   Newest release first. `make changelog-check` (also a CI step on the release PR) validates the
   shape — both languages, `YYYY-MM-DD` date, ordering, no duplicates — and fails until the entry
   exists and `CHANGELOG.md` matches it. A hand-edited JSON has no type checker behind it, and this
   is what guarantees notes land *before* the tag.

4. Merging that PR creates the `vX.Y.Z` tag and the GitHub Release. `release-please.yml` immediately
   replaces that release's body with your text (`gh release edit --notes-file`), so nothing
   commit-derived is ever what people read.
5. It then dispatches `publish.yml`, which builds the image, smoke-tests it under Compose and pushes
   it to `ghcr.io/alexeyshalaev/hse-doc-studio` (a `GITHUB_TOKEN` push does not trigger workflows on
   its own, hence the explicit dispatch).

Why hand-written notes: the app's About screen shows "what's new" to a student writing a thesis,
in their interface language. Commit subjects (`feat(checks): ...`, English, developer-facing) are
the wrong text for that audience, so `release-notes.json` is the single source of truth. It feeds
three places at once: the app reads it at startup, `CHANGELOG.md` is generated from it, and the
GitHub release body is set from it — which is where an install that hasn't updated yet reads the
notes of the version it's being offered.

The whole repository releases as **one version**: the release PR bumps
`services/api/pyproject.toml`, `hse_doc_studio/__init__.py` and
`services/web-app/package.json` together (see `release-please-config.json`). Version lines carry an
`x-release-please-version` marker — keep it when editing them by hand. The running app reports that
same source version (`GET /system/info`), so tag, changelog and UI can never disagree.
