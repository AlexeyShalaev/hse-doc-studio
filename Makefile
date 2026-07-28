# hse-doc-studio Main Makefile
# Root entry point for all project commands

.DEFAULT_GOAL := help

# Глобальный пользовательский PYTHONPATH (указывает на системный Python)
# ломает запуски внутри venv («SRE module mismatch») — обнуляем для всех целей.
export PYTHONPATH :=

# Include scripts Makefile
include scripts/Makefile

.PHONY: help docs-serve docs-build

help:
	@echo.
	@echo ==========================================
	@echo   hse-doc-studio Project Management
	@echo ==========================================
	@echo.
	@$(MAKE) -s scripts-help
	@echo.
	@echo ==========================================
	@echo   Development and Tests
	@echo ==========================================
	@echo.
	@echo   make install               - Install dependencies of every service
	@echo   make fmt-services          - Format all services (make fmt in each service dir)
	@echo   make check                 - Lint + type check, read-only (same steps as CI)
	@echo   make test                  - Run the full test suite of every service
	@echo   make test-unit             - Backend unit tests only (fast)
	@echo   make hadolint              - Lint every Dockerfile with the CI .hadolint.yaml
	@echo.
	@echo ==========================================
	@echo   Release
	@echo ==========================================
	@echo.
	@echo   make release-notes         - Seed an empty release-notes.json entry for the current version
	@echo   make changelog             - Regenerate CHANGELOG.md from the curated release notes
	@echo   make changelog-check       - Verify the current version has notes and CHANGELOG.md matches
	@echo.
	@echo ==========================================
	@echo   Documentation
	@echo ==========================================
	@echo.
	@echo   make docs-serve            - Serve the Russian site locally (http://localhost:8000)
	@echo   make docs-serve-en         - Serve the English site locally
	@echo   make docs-build            - Build both language sites to site/ (ru) + site/en/
	@echo   make docs-lint             - Lint docs content (classes, dates, pack numbers)
	@echo.
	@echo ==========================================
	@echo   Demo media (docs screenshots and reel)
	@echo ==========================================
	@echo.
	@echo   make demo-up               - Isolated demo backend on :17777 (synthetic data)
	@echo   make shots                 - Screenshot matrix ru/en x light/dark to docs/ru/assets/shots
	@echo   make reel                  - Promo reel x4 variants to docs/ru/assets/reel
	@echo.

.PHONY: install fmt-services check test test-unit hadolint changelog changelog-check release-notes

install:
	$(MAKE) -C services/api install
	$(MAKE) -C services/web-app install

fmt-services:
	$(MAKE) -C services/api fmt
	$(MAKE) -C services/web-app fmt

# Ровно те же шаги, что и в .github/workflows/ci.yml — CI не должен приносить сюрпризов.
check:
	$(MAKE) -C services/api check
	$(MAKE) -C services/web-app lint
	$(MAKE) -C services/web-app typecheck

test:
	$(MAKE) -C services/api test
	$(MAKE) -C services/web-app test

test-unit:
	$(MAKE) -C services/api test-unit

# CHANGELOG.md — производный файл: источник заметок в release-notes.json
# (двуязычный, его же читает приложение при старте). Скрипту хватает stdlib,
# поэтому venv не нужен — тот же вызов работает и в CI, и на голой системе.
changelog:
	python scripts/gen_changelog.py

changelog-check:
	python scripts/gen_changelog.py --check

# Заготовка записи под версию из __init__.py — её бампит release-please в релизном
# PR, там же дописываем текст (ru + en) и прогоняем `make changelog`.
release-notes:
	python scripts/gen_changelog.py --new

# Тот же .hadolint.yaml, что и в CI (deploy-smoke.yml). Dockerfile в репозитории один.
hadolint:
	docker run --rm -i -v "$(CURDIR)/.hadolint.yaml:/.hadolint.yaml:ro" hadolint/hadolint hadolint --config /.hadolint.yaml --failure-threshold warning - < deploy/all-in-one/Dockerfile

# Сайт двуязычный, всё живёт в docs/: конфиги + docs/ru + docs/en + overrides,
# сборка — в docs/site (RU) и docs/site/en (EN). «Что нового» генерируется из
# release-notes.json; общие ассеты копируются docs/ru → docs/en скриптом
# scripts/docs/sync_shared.py (docs/ru — единственный источник правды).
# Порядок сборки важен: RU с --clean, EN без — иначе EN затёрла бы docs/site.
.PHONY: docs-gen docs-lint docs-serve-en

docs-gen:
	python scripts/gen_changelog.py --site ru --out docs/ru/whatsnew/index.md
	python scripts/gen_changelog.py --site en --out docs/en/whatsnew/index.md
	python scripts/docs/sync_shared.py

docs-lint: docs-gen
	python scripts/docs/lint_docs.py

docs-serve: docs-gen
	uv run --group docs zensical serve -f docs/zensical.toml

docs-serve-en: docs-gen
	uv run --group docs zensical serve -f docs/zensical.en.toml -a localhost:8001

docs-build: docs-gen
	python scripts/docs/lint_docs.py
	uv run --group docs zensical build --clean -f docs/zensical.toml
	uv run --group docs zensical build -f docs/zensical.en.toml

# Демо-материалы сайта: изолированный стенд + скриншоты/ролик (tools/demo/README.md).
.PHONY: demo-up shots reel

demo-up:
	bash tools/demo/run-demo.sh

shots:
	cd tools/demo && node screenshots/capture.mjs

reel:
	cd tools/demo && node reel/gen-assets.mjs && node reel/record.mjs && bash reel/compose.sh
