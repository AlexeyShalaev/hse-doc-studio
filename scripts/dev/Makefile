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

.PHONY: dev-help ensure-network run-services stop-all-services clean-volumes dev

dev-help:
	@echo.
	@echo === Development Environment Commands ===
	@echo.
	@echo   make dev               - Start backend + frontend dev servers (local, no Docker)
	@echo   make run-services      - Start the API in Docker
	@echo   make stop-all-services - Stop all Docker services
	@echo   make clean-volumes     - Stop services and remove volumes (DESTRUCTIVE)
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
