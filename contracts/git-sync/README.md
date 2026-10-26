# Контракт Git-синхронизации

Общие файлы бэкенда и фронтенда. Расхождение сторон ловят два теста, которые читают одни и те же файлы:

- `services/api/tests/unit/contract/test_git_sync_contract.py` проверяет эталоны моделями `api/schemas/git_sync.py` и сверяет коды ошибок с `GitErrorCode`;
- `services/web-app/src/entities/git-sync/api/contract.test.ts` разбирает те же эталоны схемами zod и сверяет коды с константой TS и ключами `errors:code.*` в ru и en.

Состав:

- `error_codes.json` закрытый список кодов ошибок (тело ответа `{detail, code}`);
- `fixtures/<Схема>/<вариант>.json` эталонные тела запросов и ответов, по каталогу на схему; каталог без схемы в обоих тестах считается ошибкой;
- `url_cases.json` векторы разбора адреса репозитория для `parse_remote_url` (Python) и `parseRemoteUrl` (TypeScript);
- `providers.json` каталог git-провайдеров (github, gitlab, gitea, bitbucket, other): правила определения по хосту, шаблоны адресов API, шаблоны ссылок на выпуск токена и добавление ключа, права токена, способ проверки токена. Копии лежат в `services/api/hse_doc_studio/core/git_sync/providers.json` и `services/web-app/src/entities/git-remote/model/providers.json`, оба теста требуют побайтного совпадения; меняют сначала этот файл, затем копируют;
- `provider_cases.json` векторы каталога для `core/git_sync/providers.py` и `entities/git-remote/model/providerCatalog.ts`, `providerLinks.ts`: определение провайдера, корень сайта и API, пути установки, очистка текста и кодирование, ссылки на токен и ключи, оценка прав токена;
- настройки серверов и проверка токена: `GET` и `PUT /git/host-settings` (`GitHostSettings`, `UpdateGitHostSettingsRequest`: отсутствующее поле оставляет значение, `null` сбрасывает) и `POST /git/credentials/{id}/check` (`GitCredentialCheck`); отказ сервера приходит ошибкой с кодом (`auth_failed`, `token_expired`, `tls_untrusted_ca`), а не телом ответа;
- `profile_cases.json` векторы проверки имени и e-mail автора для `core/vcs/author` (Python) и `validateProfile` (TypeScript); коды ошибок поля в ответе 422: `name_required`, `name_too_long`, `name_invalid`, `email_required`, `email_too_long`, `email_invalid`.

Форму меняют так: сначала эталоны, затем обе стороны и оба набора тестов в одном коммите. Эталон содержит все поля ответа явно, в том числе `null`.
