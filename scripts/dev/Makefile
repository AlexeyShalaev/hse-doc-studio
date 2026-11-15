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

.PHONY: dev-help ensure-network run-services stop-all-services clean-volumes dev pack-studio server-lite-up server-lite-seed server-lite-down server-lite-reset server-lite-credentials e2e-install e2e-m1 e2e-landing e2e-mobile e2e-passkeys e2e-runner-install e2e-model-servers e2e-pack-studio server-lite-runner-up server-lite-runner-down e2e-signing-route e2e-pdf-comments server-stack-build server-stack-up server-stack-down e2e-full

dev-help:
	@echo.
	@echo === Development Environment Commands ===
	@echo.
	@echo   make dev               - Start backend + frontend dev servers (local, no Docker)
	@echo   make pack-studio       - Pack Studio from sources over packs/ of this checkout (http://localhost:3001/pack-studio)
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
	@echo   make e2e-landing       - Run the landing page e2e (guest, phone, links, Open Graph, switch-off) against the same stand
	@echo   make e2e-mobile        - Run the phone layout e2e (360/390 px, sheets, touch targets, no horizontal scroll) against the same stand
	@echo   make e2e-passkeys      - Run the passkey e2e (virtual WebAuthn authenticator) against the same stand
	@echo   make e2e-signing-route - Run the signing route e2e (starts a shared fake-TeX runner, stops it afterwards)
	@echo   make e2e-pdf-comments  - Run the PDF preview comments e2e (same fake-TeX runner, stops it afterwards)
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

# ---- Студия шаблонов из исходников (docs/design/template-studio.md, D3, срез T19) ----
# Профиль standalone: api из исходников и Vite, рабочее пространство над packs/ этой рабочей копии, каталог паков
# Студии тот же packs/. Свои порты и каталог данных, чтобы жить рядом с `make dev` и установленной Студией.
# Предпросмотр собирается в контейнере TeX через локальный Docker (образ как у локальной Студии), PR уходит токеном
# из Настроек, «Доступы git».
PACK_STUDIO_DATA ?= $(CURDIR)/.pack-studio
PACK_STUDIO_API_PORT ?= 17261
PACK_STUDIO_WEB_PORT ?= 3001
PACK_STUDIO_TEX_IMAGE ?= texlive/texlive:latest

pack-studio:
	@echo "Pack Studio: http://localhost:$(PACK_STUDIO_WEB_PORT)/pack-studio (packs: $(CURDIR)/packs, data: $(PACK_STUDIO_DATA))"
ifeq ($(OS),Windows_NT)
	powershell -NoProfile -Command "$$env:HSE_STUDIO__DATA_DIR='$(PACK_STUDIO_DATA)'; $$env:HSE_STUDIO__SERVER__PORT='$(PACK_STUDIO_API_PORT)'; $$env:HSE_STUDIO__PACK_STUDIO__STANDALONE='true'; $$env:HSE_STUDIO__PACK_STUDIO__STANDALONE_FOLDER='$(CURDIR)'; $$env:HSE_STUDIO__COMPILE__IMAGE='$(PACK_STUDIO_TEX_IMAGE)'; $$env:VITE_DEV_PROXY_TARGET='http://localhost:$(PACK_STUDIO_API_PORT)'; $$a=Start-Process -PassThru -NoNewWindow make -ArgumentList '-C','services/api','run-api'; $$w=Start-Process -PassThru -NoNewWindow pnpm -ArgumentList '--dir','services/web-app','dev','--port','$(PACK_STUDIO_WEB_PORT)','--strictPort'; Wait-Process -Id $$a.Id,$$w.Id"
else
	HSE_STUDIO__DATA_DIR="$(PACK_STUDIO_DATA)" HSE_STUDIO__SERVER__PORT=$(PACK_STUDIO_API_PORT) \
	  HSE_STUDIO__PACK_STUDIO__STANDALONE=true HSE_STUDIO__PACK_STUDIO__STANDALONE_FOLDER="$(CURDIR)" \
	  HSE_STUDIO__COMPILE__IMAGE=$(PACK_STUDIO_TEX_IMAGE) \
	  $(MAKE) -C services/api run-api & \
	VITE_DEV_PROXY_TARGET=http://localhost:$(PACK_STUDIO_API_PORT) \
	  pnpm --dir services/web-app dev --port $(PACK_STUDIO_WEB_PORT) --strictPort & \
	wait
endif

# ---- Стенд server-lite: api в режиме server (experimental) + Postgres, без раннера и S3 ----
SERVER_LITE_DIR = $(DEV_SCRIPTS_DIR)/server-lite
SERVER_LITE_ENV = $(SERVER_LITE_DIR)/.env
# Имя проекта compose можно сменить, чтобы держать рядом второй стенд (порт задаёт SERVER_LITE_PORT в .env).
SERVER_LITE_PROJECT ?= hse-doc-studio-server-lite
SERVER_LITE_COMPOSE = $(DOCKER_COMPOSE) -p $(SERVER_LITE_PROJECT) -f $(SERVER_LITE_DIR)/compose.yml --env-file $(SERVER_LITE_ENV)

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
	$(SERVER_LITE_COMPOSE) --profile seed --profile runner down

# Общий раннер с поддельным TeX (fake_tex_runner.py): собранный PDF и проверка подписей без образа TeX Live.
# Пока он запущен, сборки всех людей стенда идут на нём, поэтому сценарии «стенд без раннеров» идут до него.
server-lite-runner-up: $(SERVER_LITE_ENV)
	$(SERVER_LITE_COMPOSE) --profile runner up --build -d --no-deps runner

server-lite-runner-down: $(SERVER_LITE_ENV)
	$(SERVER_LITE_COMPOSE) --profile runner stop runner

server-lite-reset: $(SERVER_LITE_ENV)
	@echo WARNING: This will remove the stand data and its secrets!
	@echo Type 'yes' to confirm:
	@$(SHELL) -c 'read confirm && [ "$$confirm" = "yes" ]' || (echo "Cancelled." && exit 1)
	$(SERVER_LITE_COMPOSE) --profile seed --profile runner down --volumes --remove-orphans
	rm -f $(SERVER_LITE_ENV)

# ---- Приёмочные e2e M1 (Playwright) против поднятого и залитого стенда ----
# Стенд: make server-lite-up server-lite-seed. Свой Chrome вместо загрузки Chromium: make e2e-m1 E2E_CHANNEL=chrome.
e2e-install:
	cd e2e && pnpm install --frozen-lockfile && pnpm exec playwright install chromium

e2e-m1: $(SERVER_LITE_ENV)
	@. $(SERVER_LITE_ENV); cd e2e && \
	  E2E_BASE_URL=http://localhost:$${SERVER_LITE_PORT:-8100} E2E_SEED_PASSWORD=$$SERVER_LITE_SEED_PASSWORD \
	  pnpm exec playwright test --project=m1 --project=local-studio

# Лендинг на корне: гость, телефон, ссылки как раньше, Open Graph и выключение админом (нужен пароль админа).
e2e-landing: $(SERVER_LITE_ENV)
	@. $(SERVER_LITE_ENV); cd e2e && \
	  E2E_BASE_URL=http://localhost:$${SERVER_LITE_PORT:-8100} E2E_SEED_PASSWORD=$$SERVER_LITE_SEED_PASSWORD \
	  E2E_ADMIN_PASSWORD=$$SERVER_LITE_ADMIN_PASSWORD E2E_ADMIN_EMAIL=$${SERVER_LITE_ADMIN_EMAIL:-admin@example.org} \
	  pnpm exec playwright test --project=landing

# Телефон: вход, список проектов, шторки, зоны касания, без горизонтальной прокрутки (360x740, 390x844, планшет).
# Часть файлов: make e2e-mobile E2E_MOBILE_FILES="/mobile-admin.spec.ts /sidebar-overflow.spec.ts" (так делит CI).
E2E_MOBILE_FILES ?=
e2e-mobile: $(SERVER_LITE_ENV)
	@. $(SERVER_LITE_ENV); cd e2e && \
	  E2E_BASE_URL=http://localhost:$${SERVER_LITE_PORT:-8100} E2E_SEED_PASSWORD=$$SERVER_LITE_SEED_PASSWORD \
	  E2E_ADMIN_PASSWORD=$$SERVER_LITE_ADMIN_PASSWORD E2E_ADMIN_EMAIL=$${SERVER_LITE_ADMIN_EMAIL:-admin@example.org} \
	  pnpm exec playwright test --project=mobile $(E2E_MOBILE_FILES)

# Серверы моделей в админке на подменённом API (Docker не нужен).
e2e-model-servers: $(SERVER_LITE_ENV)
	@. $(SERVER_LITE_ENV); cd e2e && \
	  E2E_BASE_URL=http://localhost:$${SERVER_LITE_PORT:-8100} E2E_SEED_PASSWORD=$$SERVER_LITE_SEED_PASSWORD \
	  E2E_ADMIN_PASSWORD=$$SERVER_LITE_ADMIN_PASSWORD E2E_ADMIN_EMAIL=$${SERVER_LITE_ADMIN_EMAIL:-admin@example.org} \
	  pnpm exec playwright test --project=model-servers

# Студия шаблонов: включение в админке и экраны на подменённом API пространств (git на стенде не нужен).
e2e-pack-studio: $(SERVER_LITE_ENV)
	@. $(SERVER_LITE_ENV); cd e2e && \
	  E2E_BASE_URL=http://localhost:$${SERVER_LITE_PORT:-8100} E2E_SEED_PASSWORD=$$SERVER_LITE_SEED_PASSWORD \
	  E2E_ADMIN_PASSWORD=$$SERVER_LITE_ADMIN_PASSWORD E2E_ADMIN_EMAIL=$${SERVER_LITE_ADMIN_EMAIL:-admin@example.org} \
	  pnpm exec playwright test --project=pack-studio

# Passkey с виртуальным аутентификатором Chrome на том же стенде (нужен ещё пароль админа для сброса ключей).
e2e-passkeys: $(SERVER_LITE_ENV)
	@. $(SERVER_LITE_ENV); cd e2e && \
	  E2E_BASE_URL=http://localhost:$${SERVER_LITE_PORT:-8100} E2E_SEED_PASSWORD=$$SERVER_LITE_SEED_PASSWORD \
	  E2E_ADMIN_PASSWORD=$$SERVER_LITE_ADMIN_PASSWORD E2E_ADMIN_EMAIL=$${SERVER_LITE_ADMIN_EMAIL:-admin@example.org} \
	  pnpm exec playwright test --project=passkeys

# Команды установки раннера у токена на том же стенде (нужен пароль админа).
e2e-runner-install: $(SERVER_LITE_ENV)
	@. $(SERVER_LITE_ENV); cd e2e && \
	  E2E_BASE_URL=http://localhost:$${SERVER_LITE_PORT:-8100} \
	  E2E_ADMIN_PASSWORD=$$SERVER_LITE_ADMIN_PASSWORD E2E_ADMIN_EMAIL=$${SERVER_LITE_ADMIN_EMAIL:-admin@example.org} \
	  pnpm exec playwright test --project=runner-install

# Маршрут подписания (автор, научрук картинкой, академрук готовой подписью gpg; возврат; версия на подписи):
# поднимает общий раннер с поддельным TeX и гасит его после прогона, чем бы тот ни кончился. Нужен gpg на хосте.
e2e-signing-route: $(SERVER_LITE_ENV)
	@$(MAKE) --no-print-directory server-lite-runner-up
	@. $(SERVER_LITE_ENV); cd e2e && \
	  E2E_BASE_URL=http://localhost:$${SERVER_LITE_PORT:-8100} \
	  E2E_ADMIN_PASSWORD=$$SERVER_LITE_ADMIN_PASSWORD E2E_ADMIN_EMAIL=$${SERVER_LITE_ADMIN_EMAIL:-admin@example.org} \
	  pnpm exec playwright test --project=signing-route; \
	  status=$$?; cd .. && $(MAKE) --no-print-directory server-lite-runner-down; exit $$status

# Комментарии из превью PDF: тот же раннер с поддельным TeX (печатает строки исходника и кладёт SyncTeX).
e2e-pdf-comments: $(SERVER_LITE_ENV)
	@$(MAKE) --no-print-directory server-lite-runner-up
	@. $(SERVER_LITE_ENV); cd e2e && \
	  E2E_BASE_URL=http://localhost:$${SERVER_LITE_PORT:-8100} \
	  E2E_ADMIN_PASSWORD=$$SERVER_LITE_ADMIN_PASSWORD E2E_ADMIN_EMAIL=$${SERVER_LITE_ADMIN_EMAIL:-admin@example.org} \
	  pnpm exec playwright test --project=pdf-comments; \
	  status=$$?; cd .. && $(MAKE) --no-print-directory server-lite-runner-down; exit $$status

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
