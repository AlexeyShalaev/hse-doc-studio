# Контракт Студии шаблонов

API `/api/v1/pack-studio/*` и `/api/admin/pack-studio*` (`docs/design/template-studio.md`, разделы 3, 4 и 12; срезы T5 и T6). Расхождение сторон ловит `services/api/tests/unit/contract/test_pack_studio_contract.py`: эталоны проверяются строгими моделями `api/schemas/pack_studio.py`, коды ошибок сверяются с `PackStudioErrorCode`. Клиент (срез T8) разбирает те же эталоны схемами zod.

Состав:

- `error_codes.json` закрытый список кодов ошибок Студии шаблонов. Тело ответа `{detail, code, ...}`: `detail` на языке интерфейса, остальные поля по коду (`etag` и `content` у `stale_file`, `path` у `version_released` и `releases_read_only`, `op` и `reason` у `yaml_patch_conflict`, `limit` у `file_too_large` и `workspace_limit`). Сбои git рабочего пространства (клон, выборка, доступ) идут кодами `contracts/git-sync/error_codes.json`, в том числе в поле `error.code` карточки пространства. Коды T6: `fork_required` (поле `can_create`: форк можно создать токеном, только GitHub), `push_denied`, `lint_failed` (`errors`, `warnings`, `findings` с ошибками проверки пака), `merge_conflict` (`files` от папки паков), `workspace_dirty`, `nothing_to_propose`, `branch_name_invalid`, `service_access_*`; `pr_permission_missing` приходит полем `pr_error` ответа «Предложить», а `ci_status_unavailable` полем `reason` статуса проверок, не ошибкой. Коды следующих срезов (`preview_quota` и другие) заняты заранее;
- `fixtures/<Схема>/<вариант>.json` эталонные тела запросов и ответов, по каталогу на схему. Эталон содержит все поля явно, в том числе `null`.

## Маршруты

| Метод и путь | Ответ | Что |
|---|---|---|
| `GET /pack-studio/section` | `PackStudioSection` | раздел включён, задан ли окружением, есть ли право; открыт любому вошедшему |
| `PUT /pack-studio/section` | `PackStudioSection` | только локально: переключатель «Инструменты автора шаблонов» |
| `GET /pack-studio/workspaces` | `PackWorkspaceList` | пространства человека |
| `POST /pack-studio/workspaces` | `PackWorkspace` | `CreatePackWorkspaceRequest`; папка 201 `ready`, git 202 `cloning` (клон в фоне) |
| `GET /pack-studio/workspaces/{id}` | `PackWorkspace` | опрос до `ready` или `failed` (`busy` false) |
| `DELETE /pack-studio/workspaces/{id}` | 204 | у git удаляется клон, у папки только запись |
| `POST /pack-studio/workspaces/{id}/refresh` | 202 `PackWorkspace` | выборка базовой ветки и пересчёт выпущенных; у неудачного клона клон заново |
| `GET /pack-studio/workspaces/{id}/tree` | `PackTree` | паки, шаблоны, версии с `released` и `modified`, файлы с `read_only` |
| `GET /pack-studio/workspaces/{id}/files/{path}` | байты | `ETag`; `X-Pack-Read-Only`, если файл менять нельзя |
| `PUT /pack-studio/workspaces/{id}/files/{path}` | `PackFileVersion` | файл целиком, `If-Match` по желанию |
| `PATCH /pack-studio/workspaces/{id}/files/{path}` | `PackYamlPatchResponse` | `PackYamlPatchRequest`: точечные правки YAML, весь набор или ничего |
| `DELETE /pack-studio/workspaces/{id}/files/{path}` | 204 | файл (`If-Match` по желанию) или папка |
| `GET /pack-studio/workspaces/{id}/git` | `PackGit` | ветка (null: вершина базы без ветки), правки после коммита, отличия от базы, ahead и behind, ссылка compare, если ветка отправлена без PR |
| `GET /pack-studio/workspaces/{id}/git/diff` | `PackDiff` | единый diff от базы (коммиты и правки, новые файлы тоже), обрезан по `max_diff_bytes` |
| `POST /pack-studio/workspaces/{id}/git/branch` | `PackGit` | `PackBranchRequest`: без имени Студия называет ветку сама; новая ветка на текущей вершине (правки остаются), своя прежняя или ветка с сервера только при чистом дереве (`workspace_dirty`) |
| `POST /pack-studio/workspaces/{id}/git/commit` | `PackCommitResponse` | `PackCommitRequest`: «Сохранить версию», автор и коммиттер из профиля, сообщение по conventional commits; без ветки она создаётся |
| `POST /pack-studio/workspaces/{id}/git/propose` | `PackProposeResponse` | `PackProposeRequest`: коммит несохранённого, проверки пака (`lint_failed`), push, PR GitHub или MR GitLab; нет права push: `fork_required`, повтор с `fork` |
| `GET /pack-studio/workspaces/{id}/git/checks` | `PackCiStatus` | статус проверок хостинга по отправленной вершине; опрос раз в 30 с, пока `pending` |
| `POST /pack-studio/workspaces/{id}/git/merge-base` | `PackGit` | выборка базы и слияние в рабочую ветку; конфликт отменяет слияние (`merge_conflict`) |
| `POST /pack-studio/workspaces/{id}/git/start-over` | `PackGit` | `PackStartOverRequest`: дерево на свежую базу без ветки, PR забывается; правки теряются только с `discard` |
| `GET/PUT /api/admin/pack-studio` | `PackStudioAdmin` | админ: включение раздела и список прав |
| `POST /api/admin/pack-studio/grants` | `PackStudioGrant` | `CreatePackStudioGrantRequest`: человеку или группе |
| `DELETE /api/admin/pack-studio/grants/{id}` | 204 | снять право |
| `GET /api/admin/pack-studio/service-access` | `PackServiceAccessList` | служебные доступы репозиториев паков (секрет не отдаётся) |
| `POST /api/admin/pack-studio/service-access` | `PackServiceAccess` | `CreatePackServiceAccessRequest`: токен репозитория уровня установки, один на репозиторий (`service_access_exists`) |
| `DELETE /api/admin/pack-studio/service-access/{id}` | 204 | убрать; пространства на нём теряют доступ |

Пути файлов идут от папки паков пространства (`hse-cs-sse/templates/coursework/versions/2026.1.5/version.yaml`): без `..`, абсолютных путей, обратных слешей, `.git` и символьных ссылок.

Операции git идут под замком пространства: вторая одновременная отвечает `workspace_busy`. Пространство со служебным доступом (`service_access: true` при создании, только сервер) отправляет ветку токеном установки, а коммит подписан человеком; форк ему недоступен (`push_denied`).

Форму меняют так: сначала эталоны, затем модели и клиент, тесты в том же коммите.
