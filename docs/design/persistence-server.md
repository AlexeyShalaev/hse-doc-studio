# Этап 2: персистентность серверного режима

Что где хранится в режиме `server`, как устроены репозитории и транзакции, кто владеет таблицами. Принципы и решения: `docs/design/collaboration.md` (разделы 4, 17, 18), карта владельцев: `docs/design/stage2-ownership.md`. Локальный режим не меняется: JSON-репозитории и `data_dir` остаются как есть.

## 1. Где что лежит

Исходники проекта остаются файлами на томе `projects_root/<project_id>`. В Postgres уходит всё, что не нужно слиянию git и что принадлежит пользователю или установке. В S3 уходят большие и неизменяемые данные.

| Данные | Local | Server |
|---|---|---|
| исходники проекта, `.hse-studio/project.json`, `signatures.json`, `forms/`, `history.json`, git-стор, `hse-sync.json`, журнал обновления шаблона | папка проекта | том `projects_root/<project_id>` (без изменений) |
| список проектов (`IProjectIndexRepository`) | `data_dir/projects.json` | таблица `projects` |
| владелец, участники, роль, team, `shared_enabled`, персона | поля `project.json` | `projects`, `project_members` (единственный источник; файл только подсказка, БД перезаписывает его) |
| настройки (`ISettingsRepository`) | `data_dir/config.json` | `user_settings` и `instance_settings` по реестру `SettingScope` |
| ИИ-провайдеры, персоны агента | `ai_providers.json`, `agent_personas.json` | таблицы, ключ провайдера шифртекстом |
| подписи (`ISigningIdentityRepository`) | `signing_identities.json`, `signing_keys/` | таблица, закрытый ключ шифртекстом, только если админ разрешил |
| git-доступы и настройки хостов | `git/credentials.json`, `host_settings.json`, `known_hosts` | таблицы, секреты шифртекстом `hs1:<key_id>:<токен>` с AAD |
| проверка обновлений | `update-check.json` | ключ `instance_settings` (самообновление выключено) |
| записи сборок (`ICompileRepository`) | `.hse-studio/compiles/<uuid>.json` | таблица, последние 50 на документ |
| чаты агента (`IChatRepository`) | `.hse-studio/chats/<sid>/` | таблицы |
| записи сдачи | `.hse-studio/submissions/` | таблица, архив пакета в S3 |
| архив PDF сборок | `.hse-studio/pdf-archive/` | S3 (`IArtifactStore`), последние 5 на документ |
| блобы входа задач и выходы | не нужны (раннер читает папку) | S3 (`IBlobStore`, ключ sha256) |
| очередь задач, раннеры, квоты | в памяти (`LocalJobDispatcher`) | таблицы `jobs`, `runners`, `quotas` |
| пользователи, сессии, токены, организации, группы, приглашения, аудит | нет | таблицы identity |
| шрифты, доверенные корни, gnupg, кэши цепочек, секрет ONLYOFFICE | `data_dir` | `data_dir` (файлы уровня установки) |
| шаблоны (`packs/`), `release-notes.json` | поставка | поставка (только чтение) |

В серверном режиме отключаются `IFilesystemBrowser`, `connect_project`, `move_project`.

## 2. Владение таблицами

| Зона | Таблицы и порты |
|---|---|
| persistence | `instance_meta`, `projects`, `project_members`, `blobs`, `user_settings`, `instance_settings`, провайдеры, персоны, подписи, git-данные, чаты, записи сборок и сдачи; `IProjectLocator`, `IObjectStore`, `IBlobStore`, `IUnitOfWork`, `ISecretCipher`, `ProjectVolume.safe_open` |
| identity | `users`, `credentials`, `sessions`, `tokens`, `orgs`, `groups`, `invites`, `audit_log`; семантика `load_for(actor, project_id)` |
| jobs | `jobs`, `runners`, `quotas`, API раннера |

Чужую таблицу читают и пишут только через порт владельца. Миграции одна цепочка alembic, один head (см. скилл `backend-add-migration`).

## 3. Репозитории

- Репозиторий APP-scope: живёт столько же, сколько контейнер, и держит `async_sessionmaker`, а не сессию. Каждый метод открывает короткую транзакцию (`sessionmaker.begin()`), как запись JSON-файла сегодня. Request-scope репозиториев нет: иначе APP-сервис получил бы репозиторий с мёртвой сессией.
- Протокол живёт в `core/`, реализация `Postgres*` в `infra/`. Репозиторий возвращает доменные сущности, ORM наружу не выходит.
- Порты, переезжающие в БД, становятся `async` отдельным поведенчески нейтральным PR (по очереди: locator, settings, chats, providers, signing) и проверяются `pytest -W error::RuntimeWarning`.
- Владелец записи берётся из `current_actor()`. Нет актора в серверном режиме это `ActorRequired`, а не молчаливый системный пользователь. Фоновые пути пересобирают `Actor(kind=user, source=job)` из `actor_id` задачи; `system_actor` допустим только в методах из allow-list (скан, восстановление, GC).

## 4. Ambient UoW

Запись в несколько таблиц (проект плюс владелец плюс аудит, пользователь плюс пароль плюс токен, запись сборки плюс постановка задачи) идёт в одной транзакции:

```python
async with uow.begin():
    await projects.create(project)
    await members.add_owner(project.id, actor.user_id)
    await audit.record(...)
```

`IUnitOfWork` (`core/uow.py`) только открывает и закрывает границу. Открытая транзакция кладётся в `ContextVar`; репозиторий использует её, если она жива, иначе открывает свою. Закрытая транзакция помечается флагом `closed`, поэтому фоновая задача, унаследовавшая контекст, не возьмёт мёртвую сессию. UoW не создаёт репозитории и не прячет их за атрибутами.

Правила: use case открывает `uow.begin()` сам, коммит только выходом из блока, вложенный `begin()` присоединяется к внешней транзакции, побочные эффекты вне БД (файлы, S3, письма) выполняются после выхода из блока.

## 5. Тесты

Три уровня, все гоняются на одном наборе портов:

1. unit: чистая логика на фейках (`tests/fakes`, InMemory-реализации с владельцем из `current_actor()`).
2. контрактные наборы (`tests/contract`, `PortContract`): один набор параметризован по реализациям (Json, InMemory, Postgres); тест изоляции двух пользователей через `two_actors`.
3. pg и s3 (маркер `pg`, `HSE_TEST_PG_DSN`, шаблонная БД с миграциями; S3 через moto или MinIO): реальная схема, миграции, транзакции.

Без DSN тесты с маркером `pg` пропускаются, а локальный режим обязан работать без extra `server` (отдельная CI-задача). Подробности: `.claude/rules/backend-testing.md`.

## 6. Порядок срезов

Фундамент: конфиг-пакет и зависимости (S2-02), БД и ambient UoW (S2-03), тестовая инфраструктура (S2-04). Затем проекты и том, данные пользователя, чаты и записи сборок, git-данные, S3 и блобы, квоты диска. Конвертации sync в async идут строго по одному PR. Точный список и зависимости: план этапа 2.

## 7. Миграции и запуск

Одна цепочка alembic в `hse_doc_studio/infra/db/migrations` (внутри пакета, чтобы попасть в образ), один `MetaData` с naming convention в `infra/db/base.py`. Команды: `hse-doc-studio db upgrade|current|check`. При `HSE_STUDIO__DB__AUTO_MIGRATE=true` api мигрирует сам под `pg_advisory_lock`, иначе при ревизии не на head старт отказывает с `db_outdated` (`infra/db/migrator.ensure_db_current`). Откат только для разработки, в проде миграции идут вперёд.

## 8. Секреты в базе

Один `ISecretCipher` (`infra/secrets`) на всё: токены git, OIDC, SMTP, ключи ИИ и подписи. Шифртекст привязан к ячейке: `column_aad(таблица, колонка, id)`, перенос в другую запись не расшифруется. Каждая таблица с секретом регистрирует колонки в `core/secrets.encrypted_columns`; по реестру работает `hse-doc-studio secrets reencrypt [--dry-run]`. Старая привязка читается через `legacy_aad`, пишется всегда новая.

Ключ в server обязателен и только из окружения: `HSE_STUDIO__SECRETS__KEY` или `__KEY_FILE` (Fernet), файла в данных нет, без ключа старт отказывает. Ключи HMAC (job-token, setup-токен) выводятся из него через HKDF с назначением (`KeyRing.derive`).

Смена ключа: задать новый `KEY`, старый перенести в `__RETIRED_KEYS` (через запятую), перезапустить, выполнить `secrets reencrypt`, после нулевого счётчика нечитаемых старый ключ можно убрать. Потеря ключа необратима: секреты в базе не прочитать, их вводят заново. Храните ключ отдельно от резервной копии базы.
