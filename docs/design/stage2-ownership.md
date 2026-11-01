# Этап 2: карта владения

Фиксирует до кода, какая зона чем владеет, чтобы срезы не заводили дубли. Расхождение имён решается правкой этой карты и эталонов `contracts/server`, а не кода экранов. Принципы и решения: `docs/design/collaboration.md`.

## 1. Владельцы сущностей

| Зона | Владеет |
|---|---|
| persistence | engine, `DbConfig`, alembic (одна цепочка), `tests/fixtures`, таблицы `projects`, `project_members`, `blobs`, `instance_meta`, `IProjectLocator`, `IObjectStore`, `IBlobStore`, загрузчик манифеста, `S3ArtifactStore`, приём выходов задач, `ISecretCipher` и `KeyRing`, `ProjectVolume.safe_open` |
| identity | `users`, `sessions`, `tokens` (PAT), `orgs`, `groups`, `audit_log`, `invites`, семантика `load_for(actor, project_id)`, `IEgressPolicy`, `client_ip` и `trusted_proxies` |
| jobs | `jobs`, `runners`, `quotas`, API раннера, `QueueJobDispatcher`, планировщик, `BackgroundTaskRunner` |
| admin и frontend | SPA (`/admin`, `/first-run`, вход, аккаунт, проекты) и тонкая часть `/api/admin` поверх use cases других зон |

Известное ограничение: связка OpenPGP (`data_dir/gnupg`, `GpgKeyring`) одна на установку, это не по пользователю. Записи о ключах привязаны к владельцу в базе, но секретные и загруженные открытые ключи лежат в общей связке. Раздельные связки (`data_dir/users/<хеш>/gnupg`) потребуют актор-зависимого `GpgKeyring` и для раннера, это не сделано. Резервная копия `data_dir` обязана включать `gnupg/` и `users/**` (роли агента).

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
| OIDC | `GET /auth/oidc/{provider}/start`, `GET /auth/oidc/{provider}/callback` | есть |
| мастер | `GET /api/v1/server-setup/status`, `POST .../admin`, `GET .../environment`, `GET .../settings` (действующие значения и `locked_by_env`), `POST .../settings`, `POST .../complete`; после завершения все 404 | есть |
| аккаунт: сессии, пароль, e-mail | `/account/sessions`, `POST /account/password`, `POST /account/email` и `POST /account/email/confirm` (смена e-mail, `ChangeEmailRequest`/`ChangeEmailResponse`) | есть |
| аккаунт: профиль, токены | `/account` (профиль), `/account/tokens` | есть |
| аккаунт: способы входа | `GET /account/identities` (`AccountIdentity`: только привязанные внешние входы), `GET /account/identities/{provider}/link` (переход в браузере), `DELETE /account/identities/{provider}` | есть |
| проекты | `GET`, `POST /projects` (`ProjectSummary`, `CreateServerProjectRequest`) | есть |
| импорт из локальной Студии | `POST /api/v1/projects/import` (multipart `file`, zip папки проекта; `ProjectImportResult`; отказы `{detail, code}` с кодами `import_archive_invalid`, `import_archive_unsafe`, `import_no_project`, `import_project_newer` (422), `import_too_large` (413), `import_unavailable` (503)); CLI `hse-doc-studio server import --data-dir ... --user ... [--dry-run]` (настройки и ИИ-провайдеры) и `server import-project ... --user ...` | есть; git-доступы, ключи подписи и роли агента не переносятся |
| участники проекта | `PUT\|DELETE /projects/{id}/members/{user\|group}:{id}` (`ProjectMember`, `SetProjectMemberRequest`) | есть; список участников для панели «Доступ» (`GET /projects/{id}/members`, `ProjectAccessEntry`, любой участник проекта) и подбор людей и групп (`GET .../members/candidates?q=`, `ProjectAccessCandidate`, только владелец): видны группы и люди общих организаций (у проекта организации только она) и те, кому владелец уже открывал свои проекты, по всей установке не перебрать |
| организации и группы | `/orgs`, `/orgs/{slug}` (`Org`), `/orgs/{slug}/members` (`OrgMember`), `POST /orgs/{slug}/leave`, `/orgs/{slug}/groups` и `/groups/{id}`, `/groups/{id}/members` (`Group`, `GroupMember`); не участнику 404, мало роли 403; создание организации только админом установки или по настройке `orgs.users_can_create` | есть |
| жизненный цикл данных | `DELETE /api/admin/users/{id}` (только отключённый, не единственный владелец проектов и организаций; журнал обезличивается), `GET /api/v1/account/export`, `GET /api/admin/settings/retention` (только чтение) | есть |
| админка | `/api/admin/*`: `users`, `runners`, `runner-tokens`, `settings` (в том числе `settings/signing`), `audit`, `queue`, `quotas`, `services`, `storage`, `ai-providers` | есть, в том числе `orgs`, `settings/instance`, `settings/build`; `overview` план |
| личные раннеры | `/api/v1/account/runners*`, `/api/v1/account/runner-tokens*` (свои раннеры и личные токены регистрации, область `authenticated`, чужой id 404), протокол раннера `/api/runner/v1/announce|offline|deregister` (токен раннера); админ видит личные раннеры в `/api/admin/runners`, может приостановить и отозвать, но не сменить токен (403) | есть |
| админка: организации (SPA) | `GET\|POST /api/admin/orgs` (`AdminOrg` с `my_role`, `CreateAdminOrgRequest`), `GET\|DELETE /orgs/{slug}`, `/orgs/{slug}/members[/{user_id}]` (`AdminOrgMember`, `AddAdminOrgMemberRequest`, `UpdateAdminOrgMemberRequest`), `/orgs/{slug}/groups[/{id}]` (`AdminGroup`, `CreateAdminGroupRequest`, `UpdateAdminGroupRequest`); коды `org_has_projects`, `already_member`, `slug_taken`, `user_not_found`. Управляет админ установки без членства (ему всё доступно, включая роль владельца), последний владелец остаётся, организацию с проектами не удалить; создатель организации становится её владельцем; группа принимает только участников организации (`member_ids` заменяет состав целиком). Перенос проекта между владельцами остаётся этапом 3 | есть |
| организации человека (SPA) | `GET /api/v1/account/orgs`, `DELETE /api/v1/account/orgs/{slug}/membership` (`MyOrg`: роль, названия своих групп, `sole_owner`; только свои организации); выйти из организации умеет и `POST /orgs/{slug}/leave` | есть |
| настройки установки (SPA) | `GET\|PUT /api/admin/settings/instance` (название, адрес, ссылка на документацию), `GET\|PUT /api/admin/settings/build` (предел сборки, срок хранения результатов); у остальных настроек значения из окружения помечены `locked`. Окружение: `AUTH__PUBLIC_URL`, `SERVER__INSTANCE_NAME`, `SERVER__DOCS_URL`, `JOBS__BUILD_TIMEOUT_S`, `JOBS__ARTIFACT_RETENTION_DAYS`, `JOBS__PERSONAL_RUNNERS_ENABLED`, `JOBS__PERSONAL_RUNNER_WAIT_S`, `JOBS__PERSONAL_RUNNERS_MAX_PER_USER` (личные раннеры: разрешены ли, окно ожидания личного раннера, предел раннеров на человека; ключи `runners.*`); запись заблокированного ключа даёт `409 setting_locked` | есть |
| раннер | `/api/runner/*`: `register`, `poll`, `jobs/{id}/heartbeat|log|complete|blobs|artifacts` | есть |
| здоровье | `GET /health`, `GET /health/live`, `GET /health/ready` (публично только ok/fail, детали по `HSE_STUDIO__OBSERVABILITY__HEALTH_TOKEN` или админу), `GET /metrics` (только с токеном, иначе 404). Экран окружения мастера читает проверки `database`, `s3`, `runners` из реестра здоровья; срезы хранилища и раннеров регистрируют их под этими именами, пока не зарегистрировано, экран показывает «не настроено». Проверка `runners` необязательная: без онлайн-раннера она даёт причину `no_runners` или `no_online_runner`, но `/health/ready` остаётся зелёным | есть |

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
| `HSE_STUDIO__OBSERVABILITY__HEALTH_TOKEN`, `__METRICS_TOKEN` | Bearer-токены деталей `/health/ready` и `/metrics` |
| `HSE_STUDIO__ADMIN__ALLOWED_HOSTS`, `__ADMIN__ALLOWED_CIDRS` | ограничение `/admin` по host/IP |
| `HSE_STUDIO__EGRESS__ALLOWLIST` | внутренние узлы (имя, `*.суффикс`, IP, CIDR), к которым разрешено ходить по адресам пользователей; метаданные облака и link-local закрыты всегда |
| `HSE_STUDIO__RUNNER__BOOTSTRAP_TOKEN` | токен регистрации раннеров |
| `HSE_STUDIO__SHARING__LINKS_ENABLED`, `__SHARING__MAX_LINK_ROLE`, `__SHARING__GUEST_SESSION_DAYS` | ссылки доступа к проектам (трек links): разрешены ли, предел роли по ссылке, срок гостевой сессии |
| `HSE_STUDIO__AUTH__PROJECT_INVITES_ALLOW_SIGNUP` | приглашение в проект даёт право регистрации в режиме invite (ключ читает трек invites, страница админки в links) |
| `HSE_STUDIO__QUOTAS__*` | значения квот по умолчанию (раздел 6) |
| `HSE_STUDIO__GIT_REMOTE__ENABLED`, `__MAX_PUSH_BYTES`, `__MAX_CONCURRENT_PER_USER`, `__TIMEOUT_S`, `__LOCK_WAIT_S` | сервер как git-remote (трек gitremote): git по HTTPS на `/git/<project_id>.git`, предел тела push, одновременных запросов git на человека, срок процесса git и ожидание замка папки при приёме push |
| `HSE_STUDIO__JOBS__RELAY_PICKUP_S`, `__RELAY_MAX_REQUEST_BYTES`, `__RELAY_MAX_RESPONSE_BYTES`, `__RELAY_MAX_PENDING_PER_USER`, `__RELAY_MAX_DURATION_S`, `__RELAY_MAX_PENDING_BYTES_PER_USER`, `__RELAY_MAX_PENDING_TOTAL`, `__RELAY_MAX_PENDING_BYTES_TOTAL` | ретрансляция ИИ через личный раннер: ожидание раннера, пределы запроса и ответа, одновременных на человека, потолок длительности, бюджет памяти api под тела на человека и на процесс |

Трек invites (совместная работа, завершение): `HSE_STUDIO__AUTH__PROJECT_INVITES_ALLOW_SIGNUP` (по умолчанию `true`) разрешает регистрацию по приглашению в проект в режиме `invite` (S12). Таблицы `project_invitations`, `access_requests`, `project_transfers`, `notifications` (ревизия `cf_01_collab_finish`) принадлежат треку invites: `infra/db/repositories/{project_invitations,access_requests,project_transfers,notifications,project_cards}.py`, `use_cases/projects/{invitations,access_requests,transfer}.py`, `use_cases/notifications/*`, провайдер `infra/di/providers/server_invitations.py`.

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
