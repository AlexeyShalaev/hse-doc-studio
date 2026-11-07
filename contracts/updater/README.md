# Контракт апдейтера

Протокол между api и сервисом-апдейтером серверной установки (`/api/updater/v1`, docs/design/auto-update.md, раздел 4). Две стороны читают одни и те же файлы:

- `services/api/tests/unit/contract/test_updater_contract.py` проверяет эталоны строгими моделями `api/schemas/server_update.py` и разбор ответов клиентом апдейтера;
- исполнитель (`infra/update/server_updater`) использует ключи `PollResponse.run` как есть.

Каталоги `fixtures/<Схема>/<вариант>.json`: `PollRequest`, `PollResponse`, `EventRequest`, `EventResponse` и `ImageDigest` (файл `image-digest.json`, который `publish.yml` прикладывает к релизу GitHub). Подлинность: заголовок `Authorization: Bearer <HSE_STUDIO__SERVER_UPDATE__UPDATER_TOKEN>`. Доставка событий «хотя бы раз»: повтор `seq` игнорируется, события после конца запуска тоже.

Поле `capabilities` запроса `PollRequest` (необязательное, список строк) сообщает, что умеет апдейтер: `downgrade` значит, что он сверяет head образа с ревизией базы и поэтому ему можно поручить `PollResponse.run.kind = "downgrade"` (откат на выбранную версию). Апдейтер без поля такие запуски не получает.
