############################
# Stage 1: build frontend
############################
FROM node:25-alpine AS frontend-builder
WORKDIR /app

# Node 22 и pnpm 9.15.4 — ровно то, на чём фронт собирается в ci.yml
# (setup-node node-version: 22, pnpm из "packageManager" в package.json).
# pnpm@latest здесь означал бы 10.x с другим форматом lockfile'а (наш — 9.0).
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate

COPY services/web-app/package.json services/web-app/pnpm-lock.yaml services/web-app/.npmrc ./
COPY services/web-app/patches ./patches
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

COPY services/web-app/ .
ARG VITE_APP_ENV=production
ENV VITE_APP_ENV=${VITE_APP_ENV}
RUN pnpm build

############################
# Stage 2: build backend deps
############################
FROM python:3.14-slim-bookworm AS backend-builder
WORKDIR /app

# pipefail: без него упавший `uv export` даёт пустой requirements.txt, следующий
# `uv pip install -r` проходит успешно и образ уезжает без зависимостей (hadolint DL4006).
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/uv

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential ca-certificates libffi-dev libssl-dev \
  && rm -rf /var/lib/apt/lists/*

COPY services/api/pyproject.toml services/api/uv.lock* ./
RUN /uv/bin/uv export --frozen --no-hashes --extra api | grep -v "^-e \.$" > requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    /uv/bin/uv pip install --system -r requirements.txt

COPY services/api/hse_doc_studio /app/hse_doc_studio

############################
# Stage 3: production image
############################
FROM python:3.14-slim-bookworm AS production
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git \
  && rm -rf /var/lib/apt/lists/*

# Docker CLI (client only — NOT the daemon). The backend shells out to `docker`
# against the HOST daemon via the bind-mounted /var/run/docker.sock to spawn
# sibling containers: the LaTeX/LanguageTool runners AND the detached "updater"
# container used for one-click self-update. We extract just the `docker` binary
# from the official static tarball to avoid pulling in dockerd.
#
# Архитектуру берём из TARGETARCH (его подставляет buildx), а не хардкодим x86_64:
# на Apple Silicon образ должен идти нативным arm64, иначе Docker Desktop крутит
# его через эмуляцию. Имена каталогов у download.docker.com — x86_64/aarch64.
ARG TARGETARCH
ARG DOCKER_CLI_VERSION=29.6.2
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) dockerArch='x86_64' ;; \
      arm64) dockerArch='aarch64' ;; \
      *) echo "неподдерживаемый TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${dockerArch}/docker-${DOCKER_CLI_VERSION}.tgz" \
      -o /tmp/docker.tgz; \
    tar -xzf /tmp/docker.tgz -C /tmp docker/docker; \
    install -m 0755 /tmp/docker/docker /usr/local/bin/docker; \
    rm -rf /tmp/docker /tmp/docker.tgz; \
    docker --version

RUN addgroup --system app && adduser --system --ingroup app \
    --no-create-home --disabled-password --shell /usr/sbin/nologin app

COPY --from=backend-builder /usr/local /usr/local
COPY --from=backend-builder /app /app

# Frontend built assets served as static files by FastAPI
COPY --from=frontend-builder --chown=app:app /app/dist /app/static

# Пак шаблонов документов — то, из чего создаётся проект. Вне монорепы settings.packs_dir
# падает на дефолт /app/packs (см. api/config.py), поэтому кладём пак именно туда.
COPY --chown=app:app packs /app/packs

# Курируемые заметки о релизах («Что нового»). Лежат в корне репозитория, поэтому
# в образ едут отдельным COPY — settings.release_notes_file вне монорепы падает на
# дефолт /app/release-notes.json. Что файл реально доехал, проверяет смоук в publish.yml.
COPY --chown=app:app release-notes.json /app/release-notes.json

# Дата сборки — единственная метаданная релиза, которой НЕТ в исходниках: версию
# бампит release-please в __init__.py, а вот момент сборки знает только CI
# (publish.yml передаёт --build-arg). Пусто при локальной сборке — «О программе»
# тогда просто не показывает дату.
ARG HSE_STUDIO_BUILT=""

# Порт задаётся ЗДЕСЬ, а не только в compose. Иначе образ противоречит сам себе:
# `EXPOSE` и HEALTHCHECK ниже говорят про 8000, а приложение по умолчанию слушает
# 17240, и совпадает это ровно при запуске из compose, который порт
# переопределяет. Запущенный одной командой `docker run` образ оказывался вечно
# «unhealthy» — а на статус здоровья опирается пересоздание контейнера
# (обновление версии и мастер настройки), и оно откатывалось бы всегда.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONPATH=/app \
    HSE_STUDIO__SERVER__PORT=8000 \
    HSE_STUDIO__STATIC_DIR=/app/static \
    HSE_STUDIO__PACKS_DIR=/app/packs \
    HSE_STUDIO__BUILT=${HSE_STUDIO_BUILT}

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "hse_doc_studio.api.entrypoint"]


############################
# Stage 4: test image
############################
# Единственный образ в репозитории, поэтому прогон тестов в контейнере
# (scripts/tests/tests.compose.yml -> make run-tests-docker) живёт здесь же,
# а не в отдельном Dockerfile: иначе рецепт снова начнёт расходиться.
FROM backend-builder AS test
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN /uv/bin/uv export --frozen --no-hashes --all-extras | grep -v "^-e \.$" > requirements-test.txt \
 && /uv/bin/uv pip install --system --no-cache -r requirements-test.txt
COPY services/api/tests /app/tests
# Настройки pytest и покрытия берутся из /app/pyproject.toml, который положила
# стадия backend-builder ([tool.pytest.ini_options], [tool.coverage.run]).
CMD ["pytest", "/app/tests"]
