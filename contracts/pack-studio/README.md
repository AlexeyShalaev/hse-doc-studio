# Контракт Студии шаблонов

API `/api/v1/pack-studio/*` и `/api/admin/pack-studio*` (`docs/design/template-studio.md`, разделы 3, 4, 5.5-5.8, 6 и 12; срезы T5, T6, T7, T9 и T13). Расхождение сторон ловит `services/api/tests/unit/contract/test_pack_studio_contract.py`: эталоны проверяются строгими моделями `api/schemas/pack_studio.py`, коды ошибок сверяются с `PackStudioErrorCode`. Клиент (срез T8) разбирает те же эталоны схемами zod.

Состав:

- `error_codes.json` закрытый список кодов ошибок Студии шаблонов. Тело ответа `{detail, code, ...}`: `detail` на языке интерфейса, остальные поля по коду (`etag` и `content` у `stale_file`, `path` у `version_released` и `releases_read_only`, `op` и `reason` у `yaml_patch_conflict`, `limit` у `file_too_large`, `workspace_limit` и `preview_quota`, `field`, `value` и `reason` у `preview_invalid`, `reason` у `version_unreadable`, `place_invalid`, `model_invalid` и `submission_invalid`). Сбои git рабочего пространства (клон, выборка, доступ) идут кодами `contracts/git-sync/error_codes.json`, в том числе в поле `error.code` карточки пространства. Коды T6: `fork_required` (поле `can_create`: форк можно создать токеном, только GitHub), `push_denied`, `lint_failed` (`errors`, `warnings`, `findings` с ошибками проверки пака), `merge_conflict` (`files` от папки паков), `workspace_dirty`, `nothing_to_propose`, `branch_name_invalid`, `service_access_*`; `pr_permission_missing` приходит полем `pr_error` ответа «Предложить», а `ci_status_unavailable` полем `reason` статуса проверок, не ошибкой. Коды T10: `version_not_found`, `version_taken` (`version`, `suggested`, у выпуска `released_in_base`), `version_number_invalid` (`reason`), `version_not_modified`, `class_softer_than_changes` (`minimum`, `chosen`), `lint_failed` у выпуска (находки линтера версии). Коды следующих срезов заняты заранее;
- `fixtures/<Схема>/<вариант>.json` эталонные тела запросов и ответов, по каталогу на схему. Эталон содержит все поля явно, в том числе `null`.

## Маршруты

| Метод и путь | Ответ | Что |
|---|---|---|
| `GET /pack-studio/section` | `PackStudioSection` | раздел включён, задан ли окружением, есть ли право; открыт любому вошедшему |
| `PUT /pack-studio/section` | `PackStudioSection` | только локально: переключатель «Инструменты автора шаблонов» |
| `GET /pack-studio/workspaces` | `PackWorkspaceList` | пространства человека |
| `GET /pack-studio/official` | `PackOfficial` | срез T22: официальный репозиторий установки (null: кнопки нет) и уже созданное официальное пространство |
| `POST /pack-studio/official/workspace` | `PackWorkspace` | `OpenPackOfficialRequest`: `{credential_id}`, только свой доступ git; 200 уже созданное, 202 новое (клон в фоне); `official_unavailable` |
| `POST /pack-studio/workspaces` | `PackWorkspace` | `CreatePackWorkspaceRequest`; папка 201 `ready`, git 202 `cloning` (клон в фоне) |
| `GET /pack-studio/workspaces/{id}` | `PackWorkspace` | опрос до `ready` или `failed` (`busy` false) |
| `DELETE /pack-studio/workspaces/{id}` | 204 | у git удаляется клон, у папки только запись |
| `POST /pack-studio/workspaces/{id}/refresh` | 202 `PackWorkspace` | выборка базовой ветки и пересчёт выпущенных; у неудачного клона клон заново |
| `GET /pack-studio/workspaces/{id}/tree` | `PackTree` | паки, шаблоны, версии с `released` и `modified`, файлы с `read_only` |
| `GET /pack-studio/workspaces/{id}/files/{path}` | байты | `ETag`; `X-Pack-Read-Only`, если файл менять нельзя |
| `PUT /pack-studio/workspaces/{id}/files/{path}` | `PackFileVersion` | файл целиком, `If-Match` по желанию |
| `PATCH /pack-studio/workspaces/{id}/files/{path}` | `PackYamlPatchResponse` | `PackYamlPatchRequest`: точечные правки YAML, весь набор или ничего |
| `DELETE /pack-studio/workspaces/{id}/files/{path}` | 204 | файл (`If-Match` по желанию) или папка |
| `POST /pack-studio/workspaces/{id}/lint` | `PackLint` | `PackLintRequest`: файл версии даёт `pack_lint` всей версии и схемы её манифестов, `pack.yaml`, `template.yaml`, `releases.yaml` схему файла, прочее `scope: none`; находки с файлом и строкой для редактора (срез T8) |
| `GET /pack-studio/workspaces/{id}/hints?path=` | `PackEditorHints` | автодополнение: поля анкеты версии файла и макросы `\hse...` её динамических инклудов (срез T8) |
| `GET /pack-studio/workspaces/{id}/git` | `PackGit` | ветка (null: вершина базы без ветки), правки после коммита, отличия от базы, ahead и behind, ссылка compare, если ветка отправлена без PR |
| `GET /pack-studio/workspaces/{id}/git/diff` | `PackDiff` | единый diff от базы (коммиты и правки, новые файлы тоже), обрезан по `max_diff_bytes` |
| `POST /pack-studio/workspaces/{id}/git/branch` | `PackGit` | `PackBranchRequest`: без имени Студия называет ветку сама; новая ветка на текущей вершине (правки остаются), своя прежняя или ветка с сервера только при чистом дереве (`workspace_dirty`) |
| `POST /pack-studio/workspaces/{id}/git/commit` | `PackCommitResponse` | `PackCommitRequest`: «Сохранить версию», автор и коммиттер из профиля, сообщение по conventional commits; без ветки она создаётся |
| `POST /pack-studio/workspaces/{id}/git/propose` | `PackProposeResponse` | `PackProposeRequest`: коммит несохранённого, проверки пака (`lint_failed`), push, PR GitHub или MR GitLab; нет права push: `fork_required`, повтор с `fork` |
| `GET /pack-studio/workspaces/{id}/git/checks` | `PackCiStatus` | статус проверок хостинга по отправленной вершине; опрос раз в 30 с, пока `pending` |
| `POST /pack-studio/workspaces/{id}/git/merge-base` | `PackGit` | выборка базы и слияние в рабочую ветку; конфликт отменяет слияние (`merge_conflict`) |
| `POST /pack-studio/workspaces/{id}/git/start-over` | `PackGit` | `PackStartOverRequest`: дерево на свежую базу без ветки, PR забывается; правки теряются только с `discard` |
| `GET /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/preview` | `PackPreviewOptions` | документы версии, переключатели комбинаций, наборы данных, комбинация по умолчанию |
| `POST /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/preview` | `PackPreviewStart` | `StartPackPreviewRequest`: 202 и сборки в `queued`; 200, если все взяты из кэша |
| `GET /pack-studio/workspaces/{id}/previews/{build_id}` | `PackPreviewBuild` | опрос до `succeeded`, `failed` или `cancelled` |
| `DELETE /pack-studio/workspaces/{id}/previews/{build_id}` | `PackPreviewBuild` | отмена идущей сборки |
| `GET /pack-studio/workspaces/{id}/previews/{build_id}/pdf` | байты PDF | только у `succeeded`, иначе 409 `preview_not_ready` |
| `GET /pack-studio/workspaces/{id}/previews/{build_id}/log` | текст | журнал: `[render]` предупреждения рендера, вывод latexmk, объяснение неудачи |
| `GET /pack-studio/workspaces/{id}/previews/{build_id}/anchors` | JSON | якоря мест подписей (`anchors.json` сборки), если `has_anchors` |
| `GET /pack-studio/workspaces/{id}/templates/{pack}/{template}/versions` | `PackVersionOptions` | мастер «Новая версия» (срез T10): версии шаблона, база по умолчанию (последняя выпущенная), номера по классам |
| `POST /pack-studio/workspaces/{id}/templates/{pack}/{template}/versions` | 201 `PackVersionCreated` | `CreatePackVersionRequest`: копия базы в черновик `beta` (номер явно или по классу); занятый номер `version_taken` с `suggested` |
| `GET /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/state` | `PackVersionState` | живой класс по классификатору с причинами, номера по классам, заметки и их черновик из отчёта; у выпущенной `modified` и `move_to` |
| `PUT /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/notes` | `PackVersionState` | `PackVersionNotesRequest`: `changes`, `breaking_changes`, `release.note` точечными правками |
| `POST /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/renumber` | `PackVersionMoved` | `PackRenumberRequest`: черновик на другой номер, не мягче минимума (`class_softer_than_changes`) |
| `POST /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/move-edits` | `PackVersionMoved` | `PackMoveEditsRequest`: правки изменённой выпущенной версии в новый черновик, у git каталог к базе (`restored`) |
| `POST /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/release` | `PackRelease` | `PackReleaseRequest`: `status: stable`, `released_at`, `release.kind`, по желанию `default_version`, запись в `releases.yaml`; у git сначала выборка базы, номер выпущен там: `version_taken` с `released_in_base` |
| `GET /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/signatures?build_id=` | `PackSignatures` | каталог слотов версии с записями мест и меток даты, ETag манифеста; с `build_id` рамки документа сборки по её якорям (срез T9) |
| `PATCH /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/signatures` | `PackSignatures` | `PackSignaturesPatchRequest` с `If-Match` по ETag `version.yaml`: правки мест точечными правками YAML, весь набор или ничего; выпущенная версия `version_released`, невыполнимая правка `place_invalid` |
| `GET /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/model` | `PackVersionModel` | срезы T11 и T12: модель версии для форм (манифест версии и `doc.yaml` документов как данные с ETag, файлы документов по языкам, где печатается поле, находки лоадера и схемы) |
| `PATCH /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/model` | `PackVersionModel` | `PackModelPatchRequest` с `If-Match` по ETag файла `file`: точечные правки одного манифеста, весь набор или ничего; правка с новой находкой лоадера или схемы `model_invalid` |
| `POST /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/model/actions` | `PackVersionModel` | `PackModelActionRequest` с `If-Match` по ETag `version.yaml`: переименовать поле, добавить или удалить документ, перевести файлы документа; `changed` перечисляет записанные и удалённые файлы |
| `GET /pack-studio/workspaces/{id}/doc-library` | `PackDocLibrary` | документы-заготовки: последняя версия каждого шаблона пространства |
| `GET /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/submission` | `PackSubmission` | профили сдачи версии с записями `items`, `extra_items`, `signing_slots` по индексам YAML, каталог слотов, анкеты, порядок версии и встроенный, ETag манифеста (срез T13) |
| `PATCH /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/submission` | `PackSubmission` | `PackSubmissionPatchRequest` с `If-Match` по ETag `version.yaml`: правки формы точечными правками YAML, весь набор или ничего; выпущенная версия `version_released`, правка, которую лоадер или схема не поймут, `submission_invalid` |
| `POST /pack-studio/workspaces/{id}/versions/{pack}/{template}/{version}/submission/routes` | `PackSubmissionRoutes` | `PackSubmissionRoutesRequest` (набор и переключатели предпросмотра): «Маршрут в этой комбинации» каждого профиля; незнакомый переключатель `preview_invalid` |
| `GET/PUT /api/admin/pack-studio` | `PackStudioAdmin` | админ: включение раздела и список прав |
| `POST /api/admin/pack-studio/grants` | `PackStudioGrant` | `CreatePackStudioGrantRequest`: человеку или группе |
| `DELETE /api/admin/pack-studio/grants/{id}` | 204 | снять право |
| `GET /api/admin/pack-studio/service-access` | `PackServiceAccessList` | служебные доступы репозиториев паков (секрет не отдаётся) |
| `POST /api/admin/pack-studio/service-access` | `PackServiceAccess` | `CreatePackServiceAccessRequest`: токен репозитория уровня установки, один на репозиторий (`service_access_exists`) |
| `DELETE /api/admin/pack-studio/service-access/{id}` | 204 | убрать; пространства на нём теряют доступ |
| `POST /api/admin/pack-studio/service-access/{id}/check` | `PackServiceAccessCheck` | аккаунт токена, области, право push, проблемы кодами (`token_rejected`, `cannot_push`, `provider_unsupported`); только чтение |
| `GET /api/admin/pack-studio/official` | `PackStudioOfficialAdmin` | срез T22: официальный репозиторий из окружения установки (null: кнопки нет), только для чтения |

## Предпросмотр

`{pack}`, `{template}`, `{version}` это имена папок, как в дереве (`hse-cs-sse/coursework/2026.1.7`). Комбинация это словарь `{переключатель: значение}`, все значения строки: `lang`, `kind`, `staffing` (`solo`, `team2`, `team3`), `supervisor` (`university`, `company`, `none`), `co_supervisor` и `academic_supervisor` (`yes`, `no`), `nda` (если у версии есть NDA) и `meta.<поле>` для первых пяти полей select и bool. Недостающие значения берутся из набора данных (`lang`, `kind`, `staffing` в файле примера), затем по умолчанию; ответ всегда несёт полную комбинацию.

Наборы данных: файлы `<пак>/templates/<шаблон>/examples/<id>.yaml` (правятся обычными `PUT .../files/...`, вне каталога версии: выпуска не требуют) и автонаборы `auto:normal`, `auto:long` (строки втрое длиннее), `auto:empty` (только обязательные при создании поля). Файл, который не разобран, приходит с `error`, собрать по нему нельзя.

Сборка: `status` `queued` (рендер синтетического проекта и очередь), `running` (раннер взял задачу), затем `succeeded`, `failed` или `cancelled`. `key` это ключ кэша: тот же ключ значит тот же PDF, `cached: true` значит, что задачи не было. Коды `error.code`: `render_failed` (шаблон пака упал или превысил предел), `interrupted` (процесс перезапустился посреди сборки), `pdf_missing` и коды сборки проекта (`build_failed`, `font_missing`, `image_missing`, `docker_unavailable`, `no_runners`, `quota_exceeded` и другие). Новая сборка того же документа в том же наборе и комбинации отменяет прежнюю; идущих сборок у человека не больше `HSE_STUDIO__PACK_STUDIO__PREVIEW_MAX_CONCURRENT` (429 `preview_quota`).

## Места подписей

`PackSignatures` это каталог `signatures.slots` версии: у слота `default_place` (общее место, как его читает лоадер; `default_set` ложно, если ключа нет), `places` (записи `placements` по документам), `dates` (метки `default_dates` с индексом в списке YAML: битая метка пропущена, индексы остальных не сдвигаются). Записи в мм (`source: mm`) или на якоре шаблона (`source: anchor`), та же форма, что у мест пака в состоянии подписей проекта. С `build_id` у слота, применимого к документу сборки, есть `document`: чья запись (`place` своя, `default` общая), рамка `box` по якорям сборки (null: места в этой сборке нет) и состояние якоря, метки даты с рамками; `build` перечисляет якоря подписи и даты сборки.

Правки (`ops`, до 50): `set_place` (рамка `box`; без `doc` это общее место), `remove_place`, `make_default`, `bind_anchor` и `unbind_anchor` (без `doc` общее место), `add_date` (`mark` в мм или `anchor` строки даты сборки), `set_date` и `remove_date` по `index`. Место на якоре двигается относительно своей линии, новое место документа встаёт на строку шаблона с id слота, если она есть в сборке на той же странице; координаты округляются до 1 мм. Ответ это `PackSignatures` по новому тексту с новым ETag.

## Формы версии

`PackVersionModel` это манифест версии (`manifest.data` как его читает `yaml.safe_load`, даты строкой ISO) и документы ростера: у документа папки (`files/<id>/doc.yaml`) свой `manifest` с ETag, у записи v1 прямо в ростере `manifest: null` и данные в `data`. `files` это файлы папки документа от `files/` версии: `bare` путь без языкового кода, `lang` код (пусто у файла для всех языков), по грамматике суффиксов загрузчика. `usage` говорит, где печатается поле: документ, макросы `\hse...` подключённых инклудов, `direct` (исходник ссылается сам), `whole` (строка инклуда на весь документ, например шрифт). `checks` это файлы проверок версии без `.yaml` (для `gost_ref`). `references` документа это места манифеста, где он назван (слоты, места, метки даты, профили сдачи). `problems` это находки лоадера и схемы по манифестам сейчас.

Правка (`PackModelPatchRequest`): `file` от каталога версии (`version.yaml` или `files/<id>/doc.yaml`), `ops` те же, что у `PATCH .../files/...` (до 50). Правка не пишется, если после неё у файла есть находка лоадера или схемы, которой не было раньше (`model_invalid`, причина в `reason`): старые находки не мешают править дальше. Операции (`PackModelActionRequest`): `rename_field` (`field`, `to`: ключ в `meta_fields` и ссылки `project.meta.<ключ>`, `author.meta.<ключ>` во всех текстовых файлах `files/` версии), `add_document` (`document`, `name`; `source` это папка документа-заготовки, без неё пустой документ: `doc.yaml` и главный `.tex` для всех языков), `remove_document` (запись ростера и папка документа), `add_translation` (`document`, `lang`; `files` это пути без кода: без них переводятся все файлы с редакцией языка по умолчанию копией в `<stem>.<код>.<ext>`, файл для всех языков переводится только по явной просьбе и становится редакцией языка по умолчанию). Ответ это модель после правки, `changed` перечисляет записанные и удалённые пути.

## Точки сдачи

`PackSubmission` это `pack_submission.profiles` версии так, как их читает лоадер, но с индексами в списках YAML: профиль адресуется индексом `index`, записи `items`, `extra_items` и `signing_slots` своим `index`; запись, которую лоадер не читает, приходит с `entry: null` и причиной `error`, у профиля `error` это первая проблема строгого разбора. `supported_kinds` записи пусто: запись в обоих видах; `methods` без слота: любой способ. `slots` каталог слотов (для подписей пункта и `signing_slots`), `forms` анкеты версии (для `extra_items`: `source` это файл ответов анкеты в проекте), `route` порядок версии (`null`: ключа нет, действует `builtin_route`).

Правки (`ops`, до 50): `add_profile` (`head`: id, name, description; пунктов пока нет), `set_profile` (`head`, `deadline_hint: null` убирает подсказку), `remove_profile`, `move_profile` (`to`), `set_profile_route` (`steps`, `null` убирает ключ), `add_entry`, `set_entry`, `remove_entry`, `move_entry` у списка `entries` (запись полем по виду: `item`, `extra` или `slot`), `set_route` (порядок версии, `null` убирает ключ). Поля со значением лоадера по умолчанию не пишутся, незнакомые форме ключи записи остаются как были. После правки у профилей и порядка не должно появиться новых проблем строгого разбора лоадера и схемы `contracts/pack/version.schema.json`, иначе `submission_invalid` с причиной; связи (документ в ростере, слот в каталоге) проверяет линтер после записи.

`PackSubmissionRoutes` маршрут каждого профиля на синтетическом проекте комбинации тем же кодом, что маршрут проекта: `steps` людьми (персона, роль, имя из набора; пусто: подписи точке не нужны), `pairs` подписи маршрута (`point` требует пункт, `preset` добавил `signing_slots` по условию), `skipped` слоты сверх точки, которые условие не пропустило, `may_add` подписи, которые автор проекта включит сам, `items_off` документы пунктов, которые в этой комбинации не сдаются, `order_source` откуда порядок (`profile`, `version`, `builtin`). Профиль, который лоадер не читает, в ответе отсутствует.

Пути файлов идут от папки паков пространства (`hse-cs-sse/templates/coursework/versions/2026.1.5/version.yaml`): без `..`, абсолютных путей, обратных слешей, `.git` и символьных ссылок.

Операции git идут под замком пространства: вторая одновременная отвечает `workspace_busy`. Пространство со служебным доступом (`service_access: true` при создании, только сервер) отправляет ветку токеном установки, а коммит подписан человеком; форк ему недоступен (`push_denied`).

Официальные паки (срез T22, `docs/design/template-studio.md`, 4.7): вклад только своим аккаунтом GitHub (личный доступ git, форк человека, поток T6); бота установки нет. У пространства `official` (адрес совпадает с официальным репозиторием установки) и `license_accepted_at`; первое «Предложить» из официального пространства без `accept_license: true` отвечает `license_consent_required` (`license`, `license_url`, `contributing_url`). Ветка официального пространства и любого служебного доступа не трогает ничего вне папки паков, иначе `paths_outside_packs` (`files`). Статус проверок: `awaiting_approval` (запуск ждёт одобрения сопровождающего) и `pr_state` (`open`, `merged`, `closed`).

Форму меняют так: сначала эталоны, затем модели и клиент, тесты в том же коммите.
