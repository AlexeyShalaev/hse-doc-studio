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

| Назначение | URL |
|---|---|
| состояние входа | `GET /api/v1/session/bootstrap` |
| вход, выход, сессия | `POST /auth/login`, `POST /auth/logout`, `GET /auth/session` |
| регистрация | `POST /auth/register`, `POST /auth/verify`, `POST /auth/forgot`, `POST /auth/reset`, `POST /auth/verify/resend`, `GET /auth/invitations/{token}` (`InvitationInfo`) |
| OIDC | `GET /auth/oidc/{provider}/start`, `GET /auth/oidc/{provider}/callback` |
| мастер | `GET /api/v1/server-setup/status`, `POST .../admin`, `POST .../settings`, `POST .../complete` |
| аккаунт | `/account` (профиль, пароль), `/account/sessions`, `/account/tokens`, `/account/identities` |
| проекты | `GET`, `POST /projects` (`ProjectSummary`, `CreateServerProjectRequest`), `/projects/{id}/members` |
| админка | `/api/admin/*`: `users`, `orgs`, `runners`, `settings`, `audit`, `overview` |
| раннер | `/api/runner/*`: `register`, `poll`, `jobs/{id}/heartbeat|log|complete|blobs|artifacts` |
| здоровье | `GET /health` (только ok/fail), детали админу |

CSRF: токен привязан к строке сессии, приходит в bootstrap и ответе входа, шлётся в `X-CSRF-Token`; кроме того проверяется `Origin`. Bearer PAT освобождён от CSRF и не управляет токенами.

## 4. Scopes маршрутов

Единый реестр маршрутов; тест полноты сверяет его с `app.routes`.

| Scope | Кто проходит | Отказ |
|---|---|---|
| `public` | любой | |
| `authenticated` | вошедший пользователь | 401 аноним |
| `instance_admin` | админ установки и допущенный хост/IP | 404 не-админу |
| `org_admin` | админ или владелец организации | 404 чужому, 403 при нехватке роли |
| `runner_token` | токен раннера (хеш) | 401 |
| `job_token` | HMAC job-токен на задачу | 401 |
| `signed_token` | короткоживущий подписанный токен (ONLYOFFICE, превью) | 401 |
| `local_only` | только `StudioMode.local` | 404 в server |

Для проектных маршрутов дополнительно запись в `api/route_actions.py`. Чужой проект отвечает 404, нехватка роли 403.

## 5. Env-имена

| Переменная | Смысл |
|---|---|
| `HSE_STUDIO__SERVER__PROJECTS_ROOT` | корень томов проектов `projects_root/<project_id>` |
| `HSE_STUDIO__DB__*`, `HSE_STUDIO__DB__AUTO_MIGRATE` | Postgres; автомиграция под advisory lock (только compose) |
| `HSE_STUDIO__S3__*` | S3-совместимое хранилище |
| `HSE_STUDIO__SECRETS__KEY`, `__KEY_FILE`, `__RETIRED_KEYS` | `KeyRing` для `ISecretCipher` |
| `HSE_STUDIO__AUTH__*`, `__AUTH__ADMIN_EMAIL`, `__AUTH__SETUP_TOKEN_REQUIRED`, `__AUTH__TRUSTED_PROXIES`, `__AUTH__OIDC__*` | вход, мастер, прокси, OIDC |
| `HSE_STUDIO__AUTH__EXPERIMENTAL` | пускает server до финального среза; запрещён при публичном bind |
| `HSE_STUDIO__ADMIN__ALLOWED_HOSTS`, `__ADMIN__ALLOWED_CIDRS` | ограничение `/admin` по host/IP |
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
