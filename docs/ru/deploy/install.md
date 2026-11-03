---
title: Установка сервера
description: Развёртывание общего сервера через docker compose или Helm и первый запуск с созданием администратора.
tags:
  - Развёртывание
  - Docker
  - Kubernetes
---

# Установка сервера

<p class="hds-lede">Два способа: docker compose на одной машине и Helm-чарт для Kubernetes. Оба поднимают api, Postgres, S3 и раннер.</p>

## Что подготовить

- домен и TLS-терминатор (обратный прокси) с адресом вида `https://studio.example.org`;
- машину с Docker для api и отдельную, лучше выделенную, для раннера: сокет Docker равен root на хосте;
- два секрета: пароль Postgres и ключ шифрования секретов (Fernet), см. [потеря ключа](operations.md).

## docker compose

Файлы лежат в репозитории, в `deploy/server`.

```bash
cd deploy/server
cp .env.example .env              # заполните обязательные значения, подсказки внутри файла
sudo mkdir -p /var/lib/hse-runner # каталог данных раннера
sudo chown 10001:10001 /var/lib/hse-runner # владелец: пользователь app образа
docker compose up -d
docker compose --profile services up -d   # добавить LanguageTool и ONLYOFFICE
```

Профиль `services` поднимает реплики, но подключает их к api только `LANGUAGETOOL_REPLICAS` и `OFFICE_EDITOR_REPLICAS` в `.env` (готовые значения в комментариях `.env.example`). Пока списки пусты, проверка текста и редактор офисных файлов недоступны. В Helm адреса задаются в `services.languagetoolReplicas` и `services.officeEditorReplicas`.

Обязательные значения в `.env`:

| Переменная | Зачем |
|---|---|
| `PUBLIC_URL` | внешний адрес: по схеме выбирается `Secure` у cookie, адрес входит в допустимые Origin |
| `POSTGRES_PASSWORD` | пароль базы |
| `SECRETS_KEY` | Fernet-ключ шифрования секретов в базе |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` | доступ к MinIO и имя закрытого бакета; те же ключи открывают консоль MinIO |
| `RUNNER_BOOTSTRAP_TOKEN` | одноразовый токен регистрации первого раннера |
| `TRUSTED_PROXIES` | адреса вашего обратного прокси списком JSON, по ним определяется адрес клиента |

Каталог раннера (`RUNNER_DATA_DIR`) монтируется по одному и тому же пути на хосте и в контейнере, чтобы соседние контейнеры сборки видели файлы. Владелец каталога: пользователь `app` образа (uid 10001).

### Консоль и метрики MinIO

Хранилище работает на образе `pgsty/minio` (форк MinIO с возвращённой веб-консолью; в upstream-образах с Docker Hub консоли управления больше нет). Тег закреплён по версии (`RELEASE.2026-08-04T00-00-00Z`), клиент `mc` лежит в том же образе, поэтому `minio-init` использует его же.

- Консоль: `http://127.0.0.1:19001` на хосте (`MINIO_CONSOLE_BIND`, `MINIO_CONSOLE_PORT`). Вход: `S3_ACCESS_KEY` и `S3_SECRET_KEY` из `.env` (учётка администратора MinIO). Там видны бакеты, пользователи и метрики. Порт слушает только loopback: с другой машины используйте SSH-туннель `ssh -L 19001:127.0.0.1:19001 host` или обратный прокси с аутентификацией и поддержкой WebSocket. Наружу без прокси его не открывайте.
- Порт S3 (9000) наружу не публикуется, api ходит к нему по внутренней сети compose.
- Метрики Prometheus: `/minio/v2/metrics/cluster` (также `/node`, `/bucket`, `/resource`) на порту 9000. По умолчанию `MINIO_PROMETHEUS_AUTH_TYPE=public`: токен не нужен, а порт доступен только внутри сети compose. Скрейпить можно Prometheus, подключённым к этой сети: `static_configs: [{targets: ["minio:9000"]}]`, `metrics_path: /minio/v2/metrics/cluster`. Разовая проверка: `docker compose exec minio curl -s localhost:9000/minio/v2/metrics/cluster | head`. Если скрейп идёт через сеть хоста, задайте `MINIO_PROMETHEUS_AUTH_TYPE=jwt`, получите токен `docker compose exec minio mc admin prometheus generate local` и передайте его в `bearer_token` задания Prometheus.

### Обратный прокси

Раннер держит запрос опроса до 25 секунд. Задайте read-timeout не меньше 60 секунд и отключите буферизацию ответов. Для nginx: `proxy_read_timeout 75s; proxy_buffering off; client_max_body_size 512m;`. Лимит тела должен покрывать и загрузку файлов (до 256 МиБ), и импорт проекта.

По умолчанию api публикуется на `127.0.0.1` (`BIND_ADDRESS` в `.env`): прокси должен работать на том же хосте, иначе задайте адрес явно. Раннер один на хост и каталог данных, `--scale runner=N` не поддерживается: токен регистрации одноразовый.

Загрузка проекта идёт большим телом. Задайте `client_max_body_size` не меньше `HSE_STUDIO__SERVER__PROJECT_IMPORT_MAX_BYTES` плюс около 1 МБ (по умолчанию `client_max_body_size 501m;`). Само api обрывает слишком большое тело ответом 413 до записи во временный файл.

## Kubernetes

Чарт лежит в `deploy/helm/hse-doc-studio`: api (одна реплика, стратегия Recreate), Job миграций перед обновлением, раннер, ingress, Secret, PVC. Postgres и S3 подключаются внешние. Секреты лучше держать в своём Secret (`secrets.existingSecret`), а не в values. Подробности и ограничения: README чарта. Раннер в кластере собирает TeX подом на задачу (`runner.executor: kubernetes`), без `docker.sock`: см. «Раннеры».

## Первый запуск

1. Откройте `PUBLIC_URL`. Пока администратора нет, Студия показывает мастер первого запуска.
2. Если сервер слушает не только loopback, задан внешний `PUBLIC_URL` или доверенные прокси, мастер просит токен установки. Он печатается в журнале api: `docker compose logs api | grep -i setup`.
3. Создайте администратора, выберите режим регистрации и при необходимости настройте почту.
4. В админке откройте раздел раннеров и убедитесь, что раннер зарегистрирован и берёт задачи.

Без мастера администратора можно создать из окружения: `HSE_STUDIO__AUTH__ADMIN_EMAIL` и `HSE_STUDIO__AUTH__ADMIN_PASSWORD` (или `..._PASSWORD_FILE`). Создание идемпотентно: пароль уже существующего администратора не меняется. Это рекомендуемый путь для автоматизации.

Настройки, заданные в окружении (режим регистрации, домены, пароль, одобрение), побеждают значения из базы и в админке показываются как заблокированные.

## Проверка

- `GET /health` отвечает `ok` или `fail`, без деталей.
- `GET /health/ready` с `Authorization: Bearer <HEALTH_TOKEN>` отдаёт детали проверок. Без токена детали видит только администратор.
- `/metrics` отвечает 404, пока не задан `METRICS_TOKEN`.
- Схема базы: `hse-doc-studio db check` (код 1, если база не на последней ревизии).

## Ограничение доступа к админке

`HSE_STUDIO__ADMIN__ALLOWED_HOSTS` и `HSE_STUDIO__ADMIN__ALLOWED_CIDRS` сужают, откуда открывается `/admin`. Если заданы оба списка, запрос должен пройти оба.
