# Пользовательская справка (services/user-docs) и съёмка её медиа (tools/docs-studio).
# Подключается из корневого Makefile; пути от корня репозитория.

USER_DOCS_DIR = services/user-docs
DOCS_STUDIO_DIR = tools/docs-studio

.PHONY: user-docs-help user-docs-install user-docs-dev user-docs-build user-docs-check \
	docs-stand-local docs-stand-local-stop docs-stand-local-reset docs-stand-server docs-stand-server-down \
	docs-record docs-media

user-docs-help:
	@echo   make user-docs-dev         - Help site dev server (http://localhost:4321/help/ru/), all articles
	@echo   make user-docs-build       - Build the help per audience to services/user-docs/dist/{user,admin,media}
	@echo   make user-docs-check       - Help vs the app (routes, sources, ru/en parity, media) + broken links
	@echo   make docs-media [SCENARIO=k]  - Stands up + record screenshots and clips (all articles by default)
	@echo   make docs-record [SCENARIO=k] - Record only, stands already running (LANGS=ru THEMES=dark to narrow)
	@echo   make docs-stand-local / docs-stand-server - Recording stands (local :17790, server :8110)

user-docs-install:
	cd $(USER_DOCS_DIR) && pnpm install --frozen-lockfile

user-docs-dev:
	cd $(USER_DOCS_DIR) && pnpm dev

user-docs-build:
	cd $(USER_DOCS_DIR) && pnpm build

user-docs-check:
	cd $(USER_DOCS_DIR) && node scripts/check.mjs && pnpm build && node scripts/check-links.mjs

docs-stand-local:
	@$(DOCS_STUDIO_DIR)/stand/local.sh start

docs-stand-local-stop:
	@$(DOCS_STUDIO_DIR)/stand/local.sh stop

docs-stand-local-reset:
	@$(DOCS_STUDIO_DIR)/stand/local.sh reset

docs-stand-server:
	@$(DOCS_STUDIO_DIR)/stand/server.sh up

docs-stand-server-down:
	@$(DOCS_STUDIO_DIR)/stand/server.sh down

docs-record:
	cd $(DOCS_STUDIO_DIR)/record && pnpm install --frozen-lockfile >/dev/null && pnpm exec playwright install chromium >/dev/null && node run.mjs $(SCENARIO)

# Одна команда: свежий интерфейс и справка, оба стенда, съёмка, локальный стенд гасится.
docs-media:
	FRONT_BUILD=1 HELP_BUILD=1 $(DOCS_STUDIO_DIR)/stand/local.sh start
	$(DOCS_STUDIO_DIR)/stand/server.sh up
	$(MAKE) --no-print-directory docs-record SCENARIO="$(SCENARIO)"; status=$$?; \
	  $(DOCS_STUDIO_DIR)/stand/local.sh stop; exit $$status
