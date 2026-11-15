# Контракт Студии шаблонов

API `/api/v1/pack-studio/*` и `/api/admin/pack-studio*` (`docs/design/template-studio.md`, разделы 3, 4, 6 и 12; срезы T5 и T7). Расхождение сторон ловит `services/api/tests/unit/contract/test_pack_studio_contract.py`: эталоны проверяются строгими моделями `api/schemas/pack_studio.py`, коды ошибок сверяются с `PackStudioErrorCode`. Клиент (срез T8) разбирает те же эталоны схемами zod.

Состав:

- `error_codes.json` закрытый список кодов ошибок Студии шаблонов. Тело ответа `{detail, code, ...}`: `detail` на языке интерфейса, остальные поля по коду (`etag` и `content` у `stale_file`, `path` у `version_released` и `releases_read_only`, `op` и `reason` у `yaml_patch_conflict`, `limit` у `file_too_large`, `workspace_limit` и `preview_quota`, `field`, `value` и `reason` у `preview_invalid`, `reason` у `version_unreadable`). Сбои git рабочего пространства (клон, выборка, доступ) идут кодами `contracts/git-sync/error_codes.json`, в том числе в поле `error.code` карточки пространства. Коды следующих срезов (`push_denied`, `fork_required` и другие) заняты заранее;
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
| `GET /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/preview` | `PackPreviewOptions` | документы версии, переключатели комбинаций, наборы данных, комбинация по умолчанию |
| `POST /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/preview` | `PackPreviewStart` | `StartPackPreviewRequest`: 202 и сборки в `queued`; 200, если все взяты из кэша |
| `GET /pack-studio/workspaces/{id}/previews/{build_id}` | `PackPreviewBuild` | опрос до `succeeded`, `failed` или `cancelled` |
| `DELETE /pack-studio/workspaces/{id}/previews/{build_id}` | `PackPreviewBuild` | отмена идущей сборки |
| `GET /pack-studio/workspaces/{id}/previews/{build_id}/pdf` | байты PDF | только у `succeeded`, иначе 409 `preview_not_ready` |
| `GET /pack-studio/workspaces/{id}/previews/{build_id}/log` | текст | журнал: `[render]` предупреждения рендера, вывод latexmk, объяснение неудачи |
| `GET /pack-studio/workspaces/{id}/previews/{build_id}/anchors` | JSON | якоря мест подписей (`anchors.json` сборки), если `has_anchors` |
| `GET/PUT /api/admin/pack-studio` | `PackStudioAdmin` | админ: включение раздела и список прав |
| `POST /api/admin/pack-studio/grants` | `PackStudioGrant` | `CreatePackStudioGrantRequest`: человеку или группе |
| `DELETE /api/admin/pack-studio/grants/{id}` | 204 | снять право |

## Предпросмотр

`{pack}`, `{template}`, `{version}` это имена папок, как в дереве (`hse-cs-sse/coursework/2026.1.7`). Комбинация это словарь `{переключатель: значение}`, все значения строки: `lang`, `kind`, `staffing` (`solo`, `team2`, `team3`), `supervisor` (`university`, `company`, `none`), `co_supervisor` и `academic_supervisor` (`yes`, `no`), `nda` (если у версии есть NDA) и `meta.<поле>` для первых пяти полей select и bool. Недостающие значения берутся из набора данных (`lang`, `kind`, `staffing` в файле примера), затем по умолчанию; ответ всегда несёт полную комбинацию.

Наборы данных: файлы `<пак>/templates/<шаблон>/examples/<id>.yaml` (правятся обычными `PUT .../files/...`, вне каталога версии: выпуска не требуют) и автонаборы `auto:normal`, `auto:long` (строки втрое длиннее), `auto:empty` (только обязательные при создании поля). Файл, который не разобран, приходит с `error`, собрать по нему нельзя.

Сборка: `status` `queued` (рендер синтетического проекта и очередь), `running` (раннер взял задачу), затем `succeeded`, `failed` или `cancelled`. `key` это ключ кэша: тот же ключ значит тот же PDF, `cached: true` значит, что задачи не было. Коды `error.code`: `render_failed` (шаблон пака упал или превысил предел), `interrupted` (процесс перезапустился посреди сборки), `pdf_missing` и коды сборки проекта (`build_failed`, `font_missing`, `image_missing`, `docker_unavailable`, `no_runners`, `quota_exceeded` и другие). Новая сборка того же документа в том же наборе и комбинации отменяет прежнюю; идущих сборок у человека не больше `HSE_STUDIO__PACK_STUDIO__PREVIEW_MAX_CONCURRENT` (429 `preview_quota`).

Пути файлов идут от папки паков пространства (`hse-cs-sse/templates/coursework/versions/2026.1.5/version.yaml`): без `..`, абсолютных путей, обратных слешей, `.git` и символьных ссылок.

Форму меняют так: сначала эталоны, затем модели и клиент, тесты в том же коммите.
