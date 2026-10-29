# Этап 2: карта владения

Фиксирует до кода, какая зона чем владеет, чтобы срезы не заводили дубли. Расхождение имён решается правкой этой карты и эталонов `contracts/server`, а не кода экранов. Принципы и решения: `docs/design/collaboration.md`.

## 1. Владельцы сущностей

| Зона | Владеет |
|---|---|
| persistence | engine, `DbConfig`, alembic (одна цепочка), `tests/fixtures`, таблицы `projects`, `project_members`, `blobs`, `instance_meta`, `IProjectLocator`, `IObjectStore`, `IBlobStore`, загрузчик манифеста, `S3ArtifactStore`, приём выходов задач, `ISecretCipher` и `KeyRing`, `ProjectVolume.safe_open` |
| identity | `users`, `sessions`, `tokens` (PAT), `orgs`, `groups`, `audit_log`, `invites`, семантика `load_for(actor, project_id)`, `IEgressPolicy`, `client_ip` и `trusted_proxies` |
| jobs | `jobs`, `runners`, `quotas`, API раннера, `QueueJobDispatcher`, планировщик, `BackgroundTaskRunner` |
| admin и frontend | SPA (`/admin`, `/first-run`, вход, аккаунт, проекты) и тонкая часть `/api/admin` поверх use cases других зон |

ACL-поля (владелец, team, `shared_enabled`, персона, роли) живут только в Postgres; `project.json` их не источник. Репозитории APP-scope, многотабличные записи через ambient `IUnitOfWork`.

## 2. Порты

Новые порты этапа 2 объявляет их владелец и только он: `IProjectLocator`, `IObjectStore`, `IBlobStore`, `ISecretCipher`, `IEgressPolicy`, `IUnitOfWork` (persistence); репозитории пользователей, сессий, токенов, организаций, аудита (identity); репозитории задач, раннеров, квот (jobs). Порты этапа 0 (`core/access`, `core/jobs`) не меняются.

## 3. Публичный контракт

Единственный источник форм: `contracts/server`. Ошибки: тело `{detail, code}`, коды из `error_codes.json`.

Колонка «Статус»: **есть** значит маршрут смонтирован в M1, **план** значит это целевой контракт, маршрута пока нет (формы в `contracts/server` могут существовать раньше роутера).

| Назначение | URL | Статус |
|---|---|---|
| состояние входа | `GET /api/v1/session/bootstrap` | есть |
| вход, выход | `POST /auth/login`, `POST /auth/logout` | есть |
| сессия | `GET /auth/session` | план |
| регистрация | `POST /auth/register`, `POST /auth/verify`, `POST /auth/forgot`, `POST /auth/reset`, `POST /auth/verify/resend`, `GET /auth/invitations/{token}` (`InvitationInfo`) | есть |
| OIDC | `GET /auth/oidc/{provider}/start`, `GET /auth/oidc/{provider}/callback` | план |
| мастер | `GET /api/v1/server-setup/status`, `POST .../admin`, `GET .../environment`, `GET .../settings` (действующие значения и `locked_by_env`), `POST .../settings`, `POST .../complete`; после завершения все 404 | есть |
| аккаунт: сессии, пароль, e-mail | `/account/sessions`, `POST /account/password`, `POST /account/email` и `POST /account/email/confirm` (смена e-mail, `ChangeEmailRequest`/`ChangeEmailResponse`) | есть |
| аккаунт: профиль, токены | `/account` (профиль), `/account/tokens` | есть |
| аккаунт: identities | `/account/identities` | план |
| проекты | `GET`, `POST /projects` (`ProjectSummary`, `CreateServerProjectRequest`) | есть |
| участники проекта | `/projects/{id}/members` | план |
| админка | `/api/admin/*`: `users`, `runners`, `runner-tokens`, `settings`, `audit` | есть; `orgs`, `overview` план |
| раннер | `/api/runner/*`: `register`, `poll`, `jobs/{id}/heartbeat|log|complete|blobs|artifacts` | есть |
| здоровье | `GET /health`, `GET /health/live`, `GET /health/ready` (публично только ok/fail, детали по `HSE_STUDIO__OBSERVABILITY__HEALTH_TOKEN` или админу), `GET /metrics` (только с токеном, иначе 404). Экран окружения мастера читает проверки `database`, `s3`, `runners` из реестра здоровья; срезы хранилища и раннеров регистрируют их под этими именами, пока не зарегистрировано, экран показывает «не настроено» | есть |

CSRF: токен привязан к строке сессии, приходит в bootstrap и ответе входа, шлётся в `X-CSRF-Token`; кроме того проверяется `Origin`. Bearer PAT освобождён от CSRF и не управляет токенами.

## 4. Scopes маршрутов

Единый реестр маршрутов; тест полноты сверяет его с `app.routes`.

| Scope | Кто проходит | Отказ |
|---|---|---|
| `public` | любой | |
| `authenticated` | вошедший пользователь | 401 аноним |
| `instance_admin` | админ установки и допущенный хост/IP | 404 не-админу под `/api/admin`, 403 на остальных маршрутах (`guards._enforce_scope`) |
| `org_admin` | админ или владелец организации | 404 не-админу установки |
| `runner_token` | токен раннера (хеш) | 401 |
| `job_token` | HMAC job-токен на задачу | 401 |
| `signed_token` | короткоживущий подписанный токен (ONLYOFFICE, превью) | 401 |
| `local_only` | только `StudioMode.local` | 404 в server |

Для проектных маршрутов дополнительно запись в `api/route_actions.py`. Чужой проект отвечает 404, нехватка роли 403.

## 5. Env-имена

| Переменная | Смысл |
|---|---|
| `HSE_STUDIO__SERVER__PROJECTS_ROOT` | корень томов проектов `projects_root/<project_id>` |
| `HSE_STUDIO__SERVER__PROJECT_RETENTION_DAYS`, `__PROJECT_PURGE_INTERVAL_S` | срок хранения удалённого проекта (по умолчанию 30 суток, 0 выключает стирание) и период проверки |
| `HSE_STUDIO__DB__*`, `HSE_STUDIO__DB__AUTO_MIGRATE` | Postgres; автомиграция под advisory lock (только compose) |
| `HSE_STUDIO__S3__*` | S3-совместимое хранилище |
| `HSE_STUDIO__SECRETS__KEY`, `__KEY_FILE`, `__RETIRED_KEYS` | `KeyRing` для `ISecretCipher` |
| `HSE_STUDIO__AUTH__*`, `__AUTH__ADMIN_EMAIL`, `__AUTH__ADMIN_NAME`, `__AUTH__ADMIN_PASSWORD` / `__AUTH__ADMIN_PASSWORD_FILE`, `__AUTH__SETUP_TOKEN_REQUIRED`, `__AUTH__TRUSTED_PROXIES`, `__AUTH__OIDC__*` | вход, мастер, прокси, OIDC |
| `HSE_STUDIO__AUTH__EXPERIMENTAL`, `__AUTH__EXPERIMENTAL_IN_CONTAINER` | пускает server до финального среза (нужны DSN и ключ секретов); запрещён при публичном bind, а 0.0.0.0 внутри контейнера допускает только подтверждение `EXPERIMENTAL_IN_CONTAINER` (стенд `scripts/dev/server-lite`, порт на loopback хоста) |
| `HSE_STUDIO__OBSERVABILITY__HEALTH_TOKEN`, `__METRICS_TOKEN` | Bearer-токены деталей `/health/ready` и `/metrics` |
| `HSE_STUDIO__ADMIN__ALLOWED_HOSTS`, `__ADMIN__ALLOWED_CIDRS` | ограничение `/admin` по host/IP |
| `HSE_STUDIO__EGRESS__ALLOWLIST` | внутренние узлы (имя, `*.суффикс`, IP, CIDR), к которым разрешено ходить по адресам пользователей; метаданные облака и link-local закрыты всегда |
| `HSE_STUDIO__RUNNER__BOOTSTRAP_TOKEN` | токен регистрации раннеров |
| `HSE_STUDIO__QUOTAS__*` | значения квот по умолчанию (раздел 6) |

## 6. Ключи квот

Уровни: значение установки по умолчанию, затем переопределение организации, затем пользователя. Этап 2 учитывает только первые два ключа; поведение при исчерпании «ждать в очереди».

| Ключ | Смысл |
|---|---|
| `jobs.concurrent` | одновременные задачи пользователя (`HSE_STUDIO__QUOTAS__USER_CONCURRENT`) |
| `jobs.max_duration_s` | максимальная длительность задачи |
| `runner.minutes_month` | минуты раннеров в месяц (этап 6) |
| `storage.bytes` | место в S3 (этап 6) |
| `languagetool.chars_day` | символы LanguageTool в день (этап 6) |
| `onlyoffice.sessions` | одновременные сессии ONLYOFFICE (этап 6) |
| `ai.tokens_month` | токены ИИ в месяц (этап 6) |
