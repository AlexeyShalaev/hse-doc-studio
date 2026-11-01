# Docker compose command
DOCKER_COMPOSE = docker compose

# Base paths (relative to project root)
DEV_SCRIPTS_DIR = scripts/dev
DEV_ENV_FILE = $(DEV_SCRIPTS_DIR)/.env
DEV_NETWORK_NAME = hse-doc-studio-network

# .env не коммитится (шаблон — .env.example). Передаём --env-file только когда файл реально
# есть: иначе `docker compose` падает с «couldn't find env file», и стенд не поднимается
# на чистом клоне. Без .env все переменные берут дефолты из compose-файлов.
DEV_ENV_FLAG = $(if $(wildcard $(DEV_ENV_FILE)),--env-file $(DEV_ENV_FILE),)

# Services compose files (automatically include all .compose.yml files from services directory)
SERVICES_COMPOSE_DIR = $(DEV_SCRIPTS_DIR)/services
SERVICES_COMPOSE_FILES = $(wildcard $(SERVICES_COMPOSE_DIR)/*.compose.yml)
SERVICES_COMPOSE_FLAGS = $(foreach f,$(SERVICES_COMPOSE_FILES),-f $(f))

# OS detection for redirection
ifeq ($(OS),Windows_NT)
	DEV_NULL = NUL
else
	DEV_NULL = /dev/null
endif

.PHONY: dev-help ensure-network run-services stop-all-services clean-volumes dev server-lite-up server-lite-seed server-lite-down server-lite-reset server-lite-credentials e2e-install e2e-m1 server-stack-build server-stack-up server-stack-down e2e-full

dev-help:
	@echo.
	@echo === Development Environment Commands ===
	@echo.
	@echo   make dev               - Start backend + frontend dev servers (local, no Docker)
	@echo   make run-services      - Start the API in Docker
	@echo   make stop-all-services - Stop all Docker services
	@echo   make clean-volumes     - Stop services and remove volumes (DESTRUCTIVE)
	@echo   make server-lite-up    - Server-mode stand (api + Postgres, experimental) on 127.0.0.1:8100
	@echo   make server-lite-seed  - Demo data for the stand: 3 users with projects
	@echo   make server-lite-credentials - Print stand logins and passwords
	@echo   make server-lite-down  - Stop the stand, keep its data
	@echo   make server-lite-reset - Stop the stand and erase its data (DESTRUCTIVE)
	@echo   make e2e-install       - Install Playwright and Chromium for the stand acceptance tests
	@echo   make e2e-m1            - Run the M1 acceptance e2e against a seeded stand (screenshots in e2e/screenshots)
	@echo   make server-stack-build - Build the image with the server extra for the full stack
	@echo   make server-stack-up   - Full server stack (deploy/server: api, runner, Postgres, MinIO) on 127.0.0.1:17251
	@echo   make e2e-full          - Run the full smoke e2e against that stack (wizard, builds, queue, runner loss)
	@echo   make server-stack-down - Stop the full stack and erase its data
	@echo.
	@echo Note: the frontend has no dev container - a container would serve a production
	@echo       build without HMR. Use 'make dev' (Vite) while working on the UI.
	@echo.
	@echo Examples:
	@echo   make run-services                                - Start everything with the 'all' profile
	@echo   make run-services PROFILES=api  - Start the API only
	@echo.

ensure-network:
	@docker network inspect $(DEV_NETWORK_NAME) > $(DEV_NULL) 2>&1 || docker network create $(DEV_NETWORK_NAME)

# Start all services (or specific ones via PROFILES=)
run-services: ensure-network
ifeq ($(PROFILES),)
	$(DOCKER_COMPOSE) \
		-p hse-doc-studio-dev \
		-f $(DEV_SCRIPTS_DIR)/infra.compose.yml \
		$(SERVICES_COMPOSE_FLAGS) \
		$(DEV_ENV_FLAG) \
		--profile all \
		up --build -d \
		--remove-orphans
else
	$(DOCKER_COMPOSE) \
		-p hse-doc-studio-dev \
		-f $(DEV_SCRIPTS_DIR)/infra.compose.yml \
		$(SERVICES_COMPOSE_FLAGS) \
		$(DEV_ENV_FLAG) \
		$(foreach p,$(PROFILES),--profile $(p)) \
		up --build -d \
		--remove-orphans
endif

# Stop all services
stop-all-services:
	$(DOCKER_COMPOSE) \
		-p hse-doc-studio-dev \
		-f $(DEV_SCRIPTS_DIR)/infra.compose.yml \
		$(SERVICES_COMPOSE_FLAGS) \
		$(DEV_ENV_FLAG) \
		--profile all \
		down

# Stop services and remove volumes (DESTRUCTIVE)
clean-volumes:
	@echo WARNING: This will remove all volumes and data!
	@echo Type 'yes' to confirm:
	@$(SHELL) -c 'read confirm && [ "$$confirm" = "yes" ]' || (echo "Cancelled." && exit 1)
	$(DOCKER_COMPOSE) \
		-p hse-doc-studio-dev \
		-f $(DEV_SCRIPTS_DIR)/infra.compose.yml \
		$(SERVICES_COMPOSE_FLAGS) \
		$(DEV_ENV_FLAG) \
		--profile all \
		down --volumes --remove-orphans

# Local development without Docker
dev:
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -Command "$$a=Start-Process -PassThru -NoNewWindow make -ArgumentList '-C','services/api','run-api'; $$w=Start-Process -PassThru -NoNewWindow make -ArgumentList '-C','services/web-app','dev'; Wait-Process -Id $$a.Id,$$w.Id"
else
	$(MAKE) -C services/api run-api & $(MAKE) -C services/web-app dev & wait
endif

# ---- Стенд server-lite: api в режиме server (experimental) + Postgres, без раннера и S3 ----
SERVER_LITE_DIR = $(DEV_SCRIPTS_DIR)/server-lite
SERVER_LITE_ENV = $(SERVER_LITE_DIR)/.env
SERVER_LITE_COMPOSE = $(DOCKER_COMPOSE) -p hse-doc-studio-server-lite -f $(SERVER_LITE_DIR)/compose.yml --env-file $(SERVER_LITE_ENV)

# Секреты стенда создаются один раз и лежат в server-lite/.env (не коммитится); ключ Fernet: 32 случайных байта base64url.
$(SERVER_LITE_ENV):
	@umask 077; { \
	  echo "SERVER_LITE_PG_PASSWORD=$$(openssl rand -hex 16)"; \
	  echo "SERVER_LITE_SECRETS_KEY=$$(openssl rand 32 | openssl base64 -A | tr '+/' '-_')"; \
	  echo "SERVER_LITE_ADMIN_PASSWORD=admin-$$(openssl rand -hex 6)"; \
	  echo "SERVER_LITE_SEED_PASSWORD=demo-$$(openssl rand -hex 6)"; \
	} > $(SERVER_LITE_ENV); chmod 600 $(SERVER_LITE_ENV)
	@echo "Created $(SERVER_LITE_ENV)"

server-lite-up: $(SERVER_LITE_ENV)
	$(SERVER_LITE_COMPOSE) up --build -d --wait
	@$(MAKE) --no-print-directory server-lite-credentials

server-lite-seed: $(SERVER_LITE_ENV)
	$(SERVER_LITE_COMPOSE) --profile seed run --rm --build seed

server-lite-credentials: $(SERVER_LITE_ENV)
	@. $(SERVER_LITE_ENV); echo "Stand: http://localhost:$${SERVER_LITE_PORT:-8100}"; \
	  echo "Admin: $${SERVER_LITE_ADMIN_EMAIL:-admin@example.org} / $$SERVER_LITE_ADMIN_PASSWORD"; \
	  echo "Demo users (after server-lite-seed): anna@example.org, boris@example.org, victor@example.org / $$SERVER_LITE_SEED_PASSWORD"

server-lite-down: $(SERVER_LITE_ENV)
	$(SERVER_LITE_COMPOSE) --profile seed down

server-lite-reset: $(SERVER_LITE_ENV)
	@echo WARNING: This will remove the stand data and its secrets!
	@echo Type 'yes' to confirm:
	@$(SHELL) -c 'read confirm && [ "$$confirm" = "yes" ]' || (echo "Cancelled." && exit 1)
	$(SERVER_LITE_COMPOSE) --profile seed down --volumes --remove-orphans
	rm -f $(SERVER_LITE_ENV)

# ---- Приёмочные e2e M1 (Playwright) против поднятого и залитого стенда ----
# Стенд: make server-lite-up server-lite-seed. Свой Chrome вместо загрузки Chromium: make e2e-m1 E2E_CHANNEL=chrome.
e2e-install:
	cd e2e && pnpm install --frozen-lockfile && pnpm exec playwright install chromium

e2e-m1: $(SERVER_LITE_ENV)
	@. $(SERVER_LITE_ENV); cd e2e && \
	  E2E_BASE_URL=http://localhost:$${SERVER_LITE_PORT:-8100} E2E_SEED_PASSWORD=$$SERVER_LITE_SEED_PASSWORD \
	  pnpm exec playwright test --project=m1

# ---- Полный смоук на стенде deploy/server (api, раннер, Postgres, MinIO) ----
# Образ с extra server собирает make server-stack-build (тег ci), затем server-stack-up и e2e-full.
SERVER_STACK = $(DEV_SCRIPTS_DIR)/server-stack/stack.sh

server-stack-build:
	$(SERVER_STACK) build

server-stack-up:
	$(SERVER_STACK) up

server-stack-down:
	$(SERVER_STACK) down

e2e-full:
	@eval "$$($(SERVER_STACK) env)"; cd e2e && pnpm exec playwright test --project=full
