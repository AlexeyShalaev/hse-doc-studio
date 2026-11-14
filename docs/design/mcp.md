# MCP-сервер Студии

Статус: дизайн (03.11.2026), ветка `feat/mcp` от `next`. Реализация идёт срезами из раздела 9; срез 2 (бэкенд) в ветке `feat/mcp-server`.

Цель: внешние ИИ-клиенты (Claude Desktop и Claude Code, Cursor, VS Code, Zed и т. п.) делают в Студии то же,
что пользователь в интерфейсе, через тул-коллы Model Context Protocol. Действует тот же человек, с теми же правами,
квотами и журналом, что и в HTTP API.

## 0. Решения

| № | Решение | Почему |
|---|---|---|
| M1 | Официальный Python SDK `mcp` 2.3.x (`mcp>=2.3,<2.4`), низкоуровневый `mcp.server.lowlevel.Server` и `StreamableHTTPSessionManager`. `MCPServer` (бывший FastMCP) не используем. | Каталог тулов у нас уже табличный (`ToolDefinition`), декораторы FastMCP его бы только дублировали. Низкоуровневый сервер даёт полный контроль над схемами, ошибками и аннотациями. Закрепляем минорную версию: SDK 2.x быстро меняется (протокол 2026-07-28, «современный» режим без `initialize`). |
| M2 | Транспорт Streamable HTTP, **без состояния** (`stateless=True`) и с JSON-ответами (`json_response=True`). Адрес `/mcp` на том же приложении FastAPI (ASGI-маршрут перед SPA-фолбэком). Менеджер SDK создаётся на каждый запрос (`run()` вокруг одного запроса): ему не нужен общий жизненный цикл приложения, и тестовым приложениям без событий старта он тоже работает. | Без сессий не нужна привязка клиента к реплике api и нет общей памяти между процессами. Уведомления от сервера к клиенту (sampling, elicitation, progress) не используются: тулы короткие либо сами ждут результата (сборка). |
| M3 | Слой тулов общий со встроенным агентом: `core/agent` (`ToolSpec`, `ToolDefinition`, `IToolHandler`, `ToolResult`) и обработчики `use_cases/chat/tools`. Недостающие тулы пишутся в `use_cases/mcp/tools` тем же интерфейсом и вызывают те же use cases, что маршруты `/api/v1`. | Одна реализация на действие; встроенный агент сможет подключить новые тулы без переписывания. |
| M4 | Права: таблица «тул → действие (`Action`) и аргумент-область» по образцу `use_cases/chat/tool_access.py` и `api/route_actions.py`. Перед каждым вызовом `IProjectAccessChecker.require(project_id, action, path)`, для записи ещё проверка «проект доступен для записи» (`GetProjectAccessUC`, аналог `project_write_guard`). Тест сверяет таблицу с каталогом: новый тул без записи не собирается. | Гард маршрутов MCP не видит, а большинство use cases права не проверяют сами (их проверяет гард). |
| M5 | Аутентификация первого среза: персональные токены доступа (PAT, `Authorization: Bearer`) с новыми областями `mcp` (пользовательские тулы) и `mcp:admin` (админские). Cookie сессии на `/mcp` не принимаются никогда. OAuth 2.1 (PKCE, динамическая регистрация клиентов, метаданные защищённого ресурса) отдельным срезом. | PAT, области и device flow в Студии уже есть, а OAuth-сервер это крупная самостоятельная работа. Заголовок `WWW-Authenticate` уже на первом срезе отвечает по RFC 6750, чтобы OAuth добавился без поломки клиентов. |
| M6 | Опасные тулы (удаление проекта и файла, жёсткий откат истории, синхронизация с git-remote, админские изменения) помечены `dangerous`. По умолчанию выключены: админ (облако) или пользователь (локально) включает их явно. Подпись ЭП через MCP только одна: `sign_submission` (комплект своим ключом по умолчанию) с отдельным правом токена `sign`; ключ с паролем через MCP не подписывает (docs/design/signature-plan.md, раздел 9). | Подпись юридически значима и требует пароля ключа: передавать его модели нельзя. Остальное обратимо, но с риском. |
| M7 | Админские тулы: группа `admin`, выключена по умолчанию, требует одновременно `actor.is_instance_admin`, область токена `mcp:admin` и включённую группу. | HTTP-админка принимает только сессию (`admin_guard` отвергает PAT). MCP ослабляет это лишь при трёх явных согласиях. |
| M8 | Настройки MCP: облако хранит в `instance_settings` (ключ `mcp.config`, словарь), локальная Студия в `config.json` (ключ `mcp`). Один порт `IMcpSettingsStore`, две реализации. Поля: `enabled`, `disabled_tools`, `disabled_groups`, `allow_dangerous`, `enabled_dangerous` (поимённо). | Без миграций: оба хранилища уже ключ-значение. |
| M9 | Облако: MCP по умолчанию **выключен**, включается в админке. Локально: тоже выключен, включается переключателем в настройках. | Новая поверхность атаки включается сознательно. |
| M10 | Журнал вызовов: в облаке событие аудита `mcp.call` (тул, проект, исход, код ошибки, длительность, клиент), читается админкой через фильтр по категории `mcp`. Локально кольцевой буфер в памяти на 500 записей. Аргументы не пишутся (там исходники), только имена ключей. | Существующий аудит со сроком хранения и фильтрами; дублировать таблицу незачем. |
| M11 | Лимиты частоты (облако): правило `MCP_CALL` на пользователя (по умолчанию 120 вызовов в минуту) плюс правила дорогих маршрутов для соответствующих тулов (`COMPILE` для сборки и проверок, `UPLOAD` для записи файла, `GIT_SYNC` для git). Тот же `IRateLimiter`, что у `/api/v1`, тот же ключ пользователя, поэтому MCP не обходит лимит HTTP. Квоты (место, сборки, токены ИИ) срабатывают внутри use cases сами. | Единый счёт по человеку. |
| M12 | Локальный режим: тот же `/mcp` на порту Студии (по умолчанию loopback). Актор локальный, токен не нужен. Защита от DNS-rebinding: Host и Origin должны быть loopback или адресом самой Студии (`require_trusted_local_host`), плюс `TransportSecuritySettings` SDK. Отдельного порта нет: «порт» в настройках показывает порт Студии. | Локальная Студия и так открыта на loopback без входа; второй сервер на другом порту добавил бы точку отказа без выигрыша. |
| M13 | stdio: команда `hse-doc-studio mcp` это мост stdio ↔ Streamable HTTP к работающей Студии (`--url`, по умолчанию локальная; `--token` или `HSE_STUDIO_TOKEN` для облака). | Одна реализация тулов, нет второго процесса, пишущего в те же проекты. Мост работает и с облаком для клиентов, не умеющих HTTP. |
| M14 | Имена тулов: у переиспользованных из агента сохраняются (`read_tex`, `edit_tex`, `compile_document`, ...), новые в `snake_case` по действию (`list_files`, `write_file`). Тулы проекта получают обязательный аргумент `project_id`. Описания тулов на русском, как у агента; тексты ответов и ошибок на языке из `X-Interface-Language` или `Accept-Language` клиента, по умолчанию русский. | Совместимость с подсказками агента; модели одинаково понимают оба языка, а человек читает ошибки на своём. |
| M15 | Аннотации MCP из вида тула: `read` даёт `readOnlyHint`, `dangerous` даёт `destructiveHint`, сборка и проверки `idempotentHint=false`, всё работает с внешним миром только через Студию (`openWorldHint=false`). | Клиенты по ним решают, спрашивать ли пользователя. |
| M16 | Тул зависит от режима, если от режима зависит сценарий. `create_project`: на общем сервере папку выделяет сервер, поэтому в облачной схеме поля `folder` нет, а присланное значение не используется; локально `folder` обязателен. Тулы только для локальной Студии помечены `local_only` (облачный каталог их не содержит), как серверные `server_only`. | Иначе облачный клиент видит обязательное поле, которое сервер отвергает, и создать проект через MCP нельзя. |
| M17 | Изменение людей проекта (`set_project_people`) идёт через тот же `UpdateProjectUC`, что PATCH проекта в вебе, с тем же правом `PROJECT_SETTINGS` и запретом записи в проект «только для чтения». Кроме строки журнала `mcp.call` каждое изменение пишет событие аудита `project.people_update` (поля, было и стало) через порт `IMcpChangeAudit`; локально это строка лога без значений. | Руководитель и авторы попадают в заявку и заявление: кто и что поменял, должно быть видно в аудите, а журнал вызовов хранит только имена аргументов. |
| M18 | `clone_cloud_project` (только локально) скачивает проект облака сценарием кнопки «Открыть» (`OpenCloudProjectUC`) с сохранённым входом кодом устройства. Токен из хранилища доступов в тул не попадает; адрес с логином или токеном отклоняется, не повторяясь в ответе. Скачивание фоновое: тул ждёт до `wait_s` секунд (по умолчанию 45, меньше таймаута клиента), повторный вызов подхватывает ту же операцию. | Один путь клонирования для интерфейса и MCP; вход на сервер требует подтверждения человека в браузере, поэтому MCP только использует готовый. |
| M19 | Обновление шаблона идёт путём окна «Обновить шаблон»: `template_update_status` (`GetTemplateUpdateStatusUC`, PROJECT_VIEW как GET `template-update`), `plan_template_update` (`PlanTemplateUpdateUC`, dry-run с отпечатком) и `apply_template_update` (`ApplyTemplateUpdateUC` с отпечатком и решениями по конфликтам), оба TEMPLATE_MANAGE и под запретом записи, как POST `plan` и `apply`. Конфликт без решения остаётся «моим», как по умолчанию в окне; снимок истории перед записью делает сценарий. Маршрут аудита не пишет, поэтому применение через MCP пишет `project.template_update` (версии, число файлов и мест подписей) через `IMcpChangeAudit`. План и применение отдают места подписей из шаблона (`signature_presets`, `signature_places`, signing-route.md, 15.9). Не опасный: обновление отменяется из настроек проекта. | Один сценарий для кнопки и MCP; отпечаток гарантирует, что применяется ровно показанный план. |
| M20 | Вариант документа (`set_document_variant`, например формат презентации pptx, beamer, reveal) меняется тем же `UpdateDocumentUC`, что PATCH документа из настроек проекта («Форматы документов»), с тем же правом `FILES_WRITE`: область права слаг автора из id документа `<база>--<автор>`, как `scope_for_rule` у маршрута (поле правила `instance_args`). Допустимые варианты берутся из определения документа в шаблоне проекта с фильтром по языку проекта, как в интерфейсе; без `variant` тул только показывает текущий и допустимые. Веб смену варианта в аудит не пишет, поэтому тул пишет событие `document.variant_update` через `IMcpChangeAudit`, как M17. | Смена варианта сбрасывает статус документа и меняет то, что уйдёт в сдачу: видно, кто и что поменял. Проверки варианта одни на интерфейс и MCP. |
| M21 | Доступ к проекту (только облако, локально доступа нет): `list_project_access`, `invite_to_project`, `revoke_project_invitation`, `remove_project_member` идут сценариями панели «Доступ» (`ListProjectAccessUC`, `CreateInvitationUC`, `RevokeInvitationUC`, `RemoveProjectMemberUC`) с правами их маршрутов: список PROJECT_VIEW, приглашения ACCESS_MANAGE и лимит `INVITE`, снятие участника PROJECT_SETTINGS. Аудит пишут сами сценарии. Приглашение только по почте; ссылка с одноразовым секретом попадает в ответ лишь при ручной доставке (почта не настроена), как в окне приглашения веба; хеш и токен отдельно не отдаются. Ожидающие приглашения в списке видит только тот, у кого есть ACCESS_MANAGE. | Агент может позвать научрука и убрать лишний доступ тем же путём и с теми же ограничениями, что человек в панели; два тула на отзыв, потому что права у отзыва приглашения и снятия участника разные. |
| M22 | `create_project` создаёт и командный проект: тот же `CreateProjectUC`, что `POST /projects` мастера создания. Авторы в `authors` (`name`, `group`, `email`, `topic`, `slug`, `managed`), руководители в `supervisor`, `co_supervisor`, `academic_supervisor` того же вида, что у `set_project_people` (разбор общий). Тул повторяет то, что мастер делает в браузере: больше одного автора означает `staffing: team`, у ведомого автора нужна тема, ведомым должен быть хотя бы один, явный `slug` допустим и уникален, `meta.group` берётся у первого автора с группой. Поддержку командного режима шаблоном, минимум двух авторов и вывод `slug` из фамилии проверяет сценарий. `author_name` остаётся для одного автора. `list_templates` показывает `staffing` шаблона. В командном проекте `set_project_people` добавляет нового автора без комплекта (`managed: false`), как «Добавить автора» в настройках, и меняет `topic`. | Иначе командный проект через MCP не создать: один автор не проходит проверку «минимум двух», а свой разбор в туле разошёлся бы с вебом. |
| M23 | Маршрут подписания (только облако, локально маршрутов нет, docs/design/signing-route.md, раздел 6.8): `get_signing_route` (ход маршрута точки: шаги, люди и их состояния, чья очередь, причина остановки; без `profile_id` сводка по маршрутам проекта) и `list_signing_tasks` (задачи владельца токена «На подпись») читают теми же сценариями, что `GET .../signing-routes` и `GET /account/signing-tasks`; гостю и ссылочному доступу маршрут не раскрывается. `send_for_signing` (`project_id`, `profile_id`) опасный: черновик точки как у `POST .../signing-routes`, предпросмотр, отправка с отпечатками этого предпросмотра (`POST .../send` без ключа). Помехи предпросмотра и участник с непринятым приглашением это отказ со списком причин, ничего не отправляется. Согласовать, подписать задачу, вернуть на доработку и пропустить подписанта через MCP нельзя: таких тулов нет, тест каталога это держит. Необязательные подписи и пропуск (signing-route.md, 13.10): `get_signing_route` отдаёт у слотов `extra` и `optional`, статус `skipped`, у участника `skipped_at` и `skippable`, у маршрута `skip_hint` («пропустить может автор в интерфейсе»); `get_signature_plan` показывает `optional` и `skipped`. Версия на подписи (signing-route.md, 12.10): `get_signing_route` отдаёт у документов `sent` и `changed`, у маршрута `changed_docs`, `changed_hint` и `stop_text` (в том числе `sent_changed`), сводка `docs` и `changed_docs`; `send_for_signing` из `active` и `completed` отказывает (`new_version_in_ui`) до создания черновика, поэтому завершённый маршрут не снимается с контроля; тулы правки и сборки (`touches` в каталоге: пути, документ или весь проект) добавляют к ответу `signing_note`, если задет документ идущего маршрута, это не отказ; `package_project` перечисляет предупреждения `changed_after_sent`. | Отправка рассылает запросы и письма людям и записывает согласие отправителя, поэтому включается админом поимённо, как остальные опасные тулы (M6). Решение подписанта юридически значимо и остаётся за человеком на странице подписи. Приглашённого без аккаунта MCP не ждёт: ссылку с `next` на страницу подписи создаёт только редактор маршрута. Новая версия сбрасывает чужие согласия и подписи изменившихся документов: это решение человека, а не агента (решение владельца 10.11.2026). Пометка вместо запрета правки, потому что правку и так не остановить (локальная Студия, git), а подписываемая версия защищена снимком. |
| M24 | Сроки контрольных точек (docs/design/signing-route.md, раздел 16): `list_submission_profiles` отдаёт у точки `deadline`, `deadline_state` (`none`, `upcoming`, `soon`, `today`, `packaged`, `overdue`), `deadline_hint` пака и `packaged_at`; `get_project` отдаёт `deadlines`; `get_signing_route` отдаёт у маршрута `point_deadline`, срок точки, из которого посчитан срок черновика (R29). `set_checkpoint_deadline` (`project_id`, `profile_id`, `deadline` ISO 8601 с поясом или `null`) идёт тем же `SetCheckpointDeadlineUC`, что `PUT .../submissions/profiles/{profile_id}/deadline`, с правом `SUBMISSION_CREATE`; неверный срок это ошибка тула с текстом `bad_deadline`, срок маршрута тул не меняет. Без `touches`: срок не входит в сборку и версию на подписи, пометка `signing_note` была бы неправдой. | Срок это настройка проекта, как поля меты: людей не уведомляет, письмо по нему шлёт только напоминание автору (R29), и легко исправляется, поэтому тул не опасный. Срок объявляют в ЛМС, агенту его называет человек; ставить его агенту естественно. |
| M25 | Маршрут из шаблона (docs/design/signing-route.md, раздел 15): MCP только читает. `get_signing_route` отдаёт у маршрута `preset` (версия шаблона, шаги персонами, `extra_slots` с условием `when`, `optional`, `skipped_by_condition`, `differs` из `order`, `slots`, `optional`) всегда, а не только тому, кто управляет маршрутом, как в API; `preset_hint`, если маршрут, который можно править, отличается от шаблона («Вернуть как в шаблоне может автор в интерфейсе»); у слотов `added_by` (`pack`, `author`, null у пары точки) и `preset_optional`. `get_signature_plan` (и план в ответе `sign_submission`) отдаёт у слота `place`: `pack`, `seed`, `manual` или `none`. `list_submission_profiles` отдаёт у точки `route_preset`: версия, шаги и `signing_slots` с условием, выполнено ли оно в проекте (`met`) и `optional`; null, если шаблон пресета не задаёт или точке подписи не нужны. `list_signatures` отдаёт `from_pack` в размещениях сам. Записи нет: ни «Вернуть как в шаблоне», ни «Вернуть место из шаблона». `send_for_signing` создаёт черновик тем же `SigningRouteDrafts.create`, что `POST .../signing-routes`, поэтому пресет (состав с условиями, отметки «необязательна», места и метки даты) применяется сам. `touches` у `send_for_signing` нет: места пишутся при создании черновика, до отправки, и входят в версию на подписи, а пометка `signing_note` («изменения не попадут в версию на подписи») была бы неправдой. | Правка маршрута и мест это решение автора на странице, у MCP правки маршрута нет вовсе (M23). Агенту нужно знать, отличается ли маршрут от шаблона и почему шаблон не добавил подпись, чтобы объяснить это человеку; отправка без ручной расстановки мест и есть смысл пресета. |

## 1. Что есть

- Агент: `core/agent` (типы), `use_cases/chat/tools` (24 обработчика поверх use cases), `ToolRegistry`, таблица прав `use_cases/chat/tool_access.py`, ворота одобрения `IApprovalGate` (запись и запуск требуют подтверждения в интерфейсе).
- Идентичность: актор в contextvar (`core/access/context.py`), цепочка `IActorResolver` (сессия, PAT, гость), PAT с областями `api`, `git:read`, `git:write`, device flow для устройств.
- Права: `core/access/policy.decide`, таблица маршрутов `ROUTE_ACTIONS`, порт `IProjectAccessChecker` для сценариев с проектом в теле запроса.
- Аудит (`IAuditLog`, `IAuditReader`), ограничитель частоты (`IRateLimiter` в `app.state`), квоты (`core/quotas`).

## 2. Архитектура

```
клиент MCP ── Streamable HTTP ──> /mcp (api/mcp/asgi.py)
                                     │ актор: PAT (облако) или локальный; язык; лимит частоты
                                     ▼
                         mcp.server.lowlevel.Server (api/mcp/server.py)
                                     │ list_tools / call_tool / resources / prompts
                                     ▼
                  use_cases/mcp: каталог, CallMcpToolUC (вкл/выкл, права, запись, журнал)
                                     │
                  обработчики: use_cases/chat/tools + use_cases/mcp/tools
                                     │
                         те же use cases, что у /api/v1
```

- `core/mcp/`: `McpToolGroup`, `McpSettings`, `McpCallRecord`, протоколы `IMcpSettingsStore`, `IMcpCallJournal`, `IMcpChangeAudit`, ошибки `McpError` с кодами.
- `use_cases/mcp/`: `McpCatalog` (записи `McpToolEntry`: определение, группа, правило прав, флаги `dangerous`, `server_only`, `local_only`, `admin`), `ListMcpToolsUC`, `CallMcpToolUC`, ресурсы и prompts, настройки (`GetMcpSettingsUC`, `UpdateMcpSettingsUC`), журнал (`ListMcpCallsUC`).
- `infra/mcp/`: хранилища настроек (локальное, серверное), журнал (память, аудит).
- `api/mcp/`: сервер SDK, ASGI-обёртка с аутентификацией, монтирование и жизненный цикл менеджера сессий (вход в `run()` на старте приложения, выход на остановке).
- `api/routers`: `/api/admin/mcp/*` (настройки, журнал), `/api/v1/mcp/*` (каталог и сведения для подключения; локальные настройки только в локальном режиме).

Вызов тула идёт в собственном REQUEST-контейнере dishka: обработчик ставит актора и язык в contextvars, открывает контейнер, берёт `CallMcpToolUC`. Ошибки use cases (`NotFoundError`, `ProjectForbiddenError`, квоты, `ValueError`) превращаются в результат с `isError: true` и понятным текстом; чужой проект неотличим от несуществующего, как в HTTP (404).

## 3. Безопасность

1. Аутентификация облака: только `Authorization: Bearer <PAT>`; токен должен иметь область `mcp`. Нет токена или он неверен: 401 и `WWW-Authenticate: Bearer realm="hse-doc-studio", error="invalid_token"`. Нет области: 403 `insufficient_scope`. Cookie игнорируются, поэтому CSRF к `/mcp` неприменим.
2. Действия от имени владельца токена: актор PAT проходит те же `decide`, квоты и аудит. Гостевые ссылки к MCP не допускаются.
3. Права на каждый вызов (M4); ответ на чужой проект такой же, как на несуществующий.
4. Опасные и админские тулы выключены по умолчанию (M6, M7); выключенный тул не виден в `tools/list` и отвечает ошибкой `tool_disabled` при прямом вызове.
5. Лимиты частоты (M11) и предел тела запроса SDK (4 МиБ).
6. Журнал (M10).
7. Локально: проверка Host/Origin (M12). MCP выключен, пока его не включат.
8. Отзыв: токен отзывается в профиле («Токены»), действует сразу (резолвер читает БД на каждый запрос).

## 4. Настройки

- Облако, админка «MCP»: общий переключатель; список тулов по группам с переключателями группы и тула, значки «только чтение», «опасный», «админ»; разрешение опасных тулов; журнал вызовов с фильтрами (пользователь, тул, исход).
- Пользователь, профиль «Подключение ИИ-клиентов (MCP)»: адрес сервера, выпуск токена с областью `mcp` (через существующие «Токены»), готовые конфиги для Claude Desktop, Claude Code, Cursor, VS Code и stdio-моста; список доступных ему тулов.
- Локально, настройки «MCP»: переключатель, адрес `http://127.0.0.1:<порт>/mcp`, тот же список тулов с переключателями, журнал последних вызовов, конфиги клиентов.

## 5. Тулы

Обозначения: R чтение, W запись, X запуск; ! опасный; S только облако; L только локальная Студия; A админ. «агент» значит обработчик встроенного агента.

| Группа | Тул | Вид | Действие | Источник |
|---|---|---|---|---|
| account | `whoami` | R | — | новый |
| projects | `list_projects` | R | — | агент |
| projects | `get_project` | R | PROJECT_VIEW | новый |
| projects | `list_templates` | R | — | агент |
| projects | `create_project` | X | — (облако: без `folder`, M16) | агент (+ команда, M22) |
| projects | `list_project_fields` | R | PROJECT_VIEW | новый |
| projects | `set_project_meta` | W | PROJECT_SETTINGS | агент (+ `unset`) |
| projects | `set_project_people` | W | PROJECT_SETTINGS | новый (M17, M22) |
| projects | `set_language` | W | PROJECT_SETTINGS | агент |
| projects | `delete_project` | W ! | PROJECT_DELETE | новый |
| projects | `clone_cloud_project` | X L | — (сохранённый вход на сервер) | новый (M18) |
| projects | `template_update_status` | R | PROJECT_VIEW | новый (M19) |
| projects | `plan_template_update` | X | TEMPLATE_MANAGE | новый (M19) |
| projects | `apply_template_update` | X | TEMPLATE_MANAGE | новый (M19) |
| projects | `list_project_access` | R S | PROJECT_VIEW (приглашения: ACCESS_MANAGE) | новый (M21) |
| projects | `invite_to_project` | W S | ACCESS_MANAGE | новый (M21) |
| projects | `revoke_project_invitation` | W S | ACCESS_MANAGE | новый (M21) |
| projects | `remove_project_member` | W S | PROJECT_SETTINGS | новый (M21) |
| files | `list_documents` | R | PROJECT_VIEW | агент |
| files | `set_document_variant` | W | FILES_WRITE (doc_id: слаг автора) | новый (M20) |
| files | `list_files` | R | SOURCES_READ | новый |
| files | `read_tex` | R | FILES_READ (path) | агент |
| files | `read_pdf` | R | FILES_READ (path) | агент |
| files | `grep_project` | R | SOURCES_READ | агент |
| files | `edit_tex` | W | FILES_WRITE (path) | агент |
| files | `write_file` | W | FILES_WRITE (path) | новый |
| files | `move_file` | W | FILES_WRITE (src, dst) | новый |
| files | `delete_file` | W ! | FILES_WRITE (path) | новый |
| build | `compile_document` | X | BUILD_RUN | агент; в MCP `wait` и ожидание до 45 с, дальше `compile_id` для `get_compile` |
| build | `list_compiles` | R | OUTPUT_READ | новый |
| build | `get_compile` | R | OUTPUT_READ | новый |
| build | `cancel_compile` | X | BUILD_RUN | новый |
| checks | `list_check_findings` | R | OUTPUT_READ | агент |
| checks | `run_checks` | X | BUILD_RUN | новый |
| checks | `list_check_rules` | R | OUTPUT_READ | новый |
| checks | `normcontrol_report` | R | OUTPUT_READ | новый |
| checks | `trace_requirements` | R | PROJECT_VIEW | агент |
| checks | `preview_requirements_format` | R | PROJECT_VIEW | агент |
| checks | `set_requirements_format` | W | PROJECT_SETTINGS | агент |
| review | `list_review_threads` | R S | SOURCES_READ | новый |
| review | `create_review_thread` | W S | COMMENT | новый |
| review | `reply_review_thread` | W S | COMMENT | новый |
| review | `set_review_thread_status` | W S | COMMENT | новый |
| history | `vcs_status` | R | SOURCES_READ | агент |
| history | `vcs_list_history` | R | SOURCES_READ | агент |
| history | `vcs_diff` | R | SOURCES_READ | агент |
| history | `vcs_save_snapshot` | W | HISTORY_WRITE | агент |
| history | `vcs_restore` | X ! | HISTORY_REWRITE | агент |
| history | `git_status` | R | SOURCES_READ | новый |
| history | `git_fetch` | X | HISTORY_WRITE | новый |
| history | `git_sync` | X ! | HISTORY_REWRITE | новый: `StartSyncUC` кнопки, ждёт до `wait_s`, при `sync_busy` присоединяется, файлы конфликтов из `GetConflictsUC` |
| submission | `list_submission_profiles` | R | PROJECT_VIEW | новый (+ срок точки, M24; пресет маршрута, M25) |
| submission | `set_checkpoint_deadline` | W | SUBMISSION_CREATE | новый (M24) |
| submission | `list_submissions` | R | SUBMISSION_READ | новый |
| submission | `package_project` | X | SUBMISSION_CREATE | агент |
| submission | `list_signatures` | R | OUTPUT_READ | новый |
| submission | `get_signature_plan` | R | OUTPUT_READ | новый (+ `place` слота, M25) |
| submission | `sign_submission` | X ! | OUTPUT_READ + SIGN по слоту, право токена `sign` | новый |
| submission | `get_signing_route` | R S | OUTPUT_READ | новый (M23; пресет, M25) |
| submission | `list_signing_tasks` | R S | — (свои задачи) | новый (M23) |
| submission | `send_for_signing` | X ! S | SUBMISSION_CREATE | новый (M23; применяет пресет, M25) |
| admin | `admin_list_users` | R S A | instance admin | новый |
| admin | `admin_queue_summary` | R S A | instance admin | новый |
| admin | `admin_runner_summary` | R S A | instance admin | новый |
| admin | `admin_list_audit` | R S A | instance admin | новый |
| admin | `admin_list_mail_log` | R S A | instance admin | новый: `ListMailLogUC`, фильтры `recipient`, `template`, `status`, `since`, `limit` до 50; только id людей и проекта, без превью (mail-log.md, 6.4); с версии 2 попытки и автоповтор (V15), повтора через MCP нет |
| admin | `admin_disable_user` | W ! S A | instance admin | новый |
| admin | `admin_enable_user` | W S A | instance admin | новый |
| admin | `admin_cancel_job` | X ! S A | instance admin | новый |

Не выставляются: `ask_user`, `set_theme`, `set_engine` (настройки интерфейса), подписание отдельного слота (M6; комплект подписывает `sign_submission`, docs/design/signature-plan.md, раздел 9), действия подписанта в маршруте подписания: согласовать, подписать, вернуть на доработку, картинка и плашка, пропуск подписанта и флаг «Подпись необязательна» (M23), «Вернуть как в шаблоне» и «Вернуть место из шаблона» (M25), служебные операции установки (бэкапы, обновления, раннеры: изменение).

Экспорт: отдельного экспорта проекта архивом в Студии нет. Его роль играют `package_project` (пакет сдачи) и ресурс PDF сборки; выгрузка git bundle остаётся в интерфейсе.

### Ресурсы

- `studio://projects` — список проектов (JSON).
- `studio://projects/{project_id}` — карточка проекта и документы (JSON).
- `studio://projects/{project_id}/files/{path}` — файл проекта (текст или base64-blob), право FILES_READ.
- `studio://projects/{project_id}/compiles/{doc_id}/{compile_id}/pdf` — PDF сборки (blob), право OUTPUT_READ.

### Prompts

- `fix_build` (`project_id`, `doc_id`): собрать, прочитать хвост лога, исправить ошибки, пересобрать.
- `normcontrol` (`project_id`, `doc_id`): прогнать проверки, разобрать замечания, предложить и внести правки.
- `review_changes` (`project_id`): статус и дифф истории, краткое описание изменений для снимка.

## 6. Ошибки

Ответ тула с `isError: true`, текст на языке клиента. Коды в `_meta.code`: `mcp_disabled` (весь MCP выключен, HTTP 503 ещё до SDK), `tool_disabled`, `not_found`, `forbidden` (роль ниже нужной, с названием роли), `read_only` (проект только для чтения), `rate_limited` (с `retry_after_s`), `quota_exceeded`, `invalid_arguments`, `failed`.

## 7. Тесты

- unit: каталог (каждая запись в таблице прав, уникальные имена, флаги), политика включения (группы, опасные, админ), конвертация ошибок, хранилища настроек.
- integration: клиент SDK (`mcp.client.client.Client` поверх `httpx2.ASGITransport`) против тестового приложения: `tools/list` учитывает настройки и роль, вызовы тулов чтения и записи, отказ чужому, выключенный MCP, нет токена и нет области, лимит частоты, журнал.
- pg: серверный режим с PAT и двумя пользователями (`two_actors`).
- e2e: по возможности сценарий подключения из профиля (выпуск токена, копирование конфига).

## 8. Документация

`docs/ru` и `docs/en`: «Подключение ИИ-клиентов (MCP)» (локально и в облаке, конфиги клиентов, мост stdio), раздел админа (включение, тулы, журнал), безопасность.

## 9. Срезы

| № | Срез | Ветка |
|---|---|---|
| 1 | Этот дизайн | `feat/mcp` |
| 2 | Бэкенд: зависимость `mcp`, `core/mcp`, каталог и все тулы, `CallMcpToolUC`, `/mcp` с PAT (`mcp`, `mcp:admin`), настройки и журнал, ресурсы и prompts, API настроек (админ и локальный), тесты | `feat/mcp-server` |
| 3 | stdio-мост `hse-doc-studio mcp` и локальная защита Host/Origin | `feat/mcp-stdio` |
| 4 | Интерфейс: админка MCP, профиль (подключение), локальные настройки, области токена | `feat/mcp-ui` |
| 5 | Документация пользователя ru/en | `feat/mcp-docs` |
| 6 | OAuth 2.1: сервер авторизации (PKCE S256, DCR RFC 7591, метаданные RFC 8414 и RFC 9728), согласие пользователя, подключённые клиенты в профиле | `feat/mcp-oauth` |

## 10. Решения для подтверждения

1. Облачный MCP и локальный выключены по умолчанию (M9).
2. Первый срез аутентификации на PAT, OAuth 2.1 позже (M5, срез 6).
3. Админские тулы через PAT при трёх условиях (M7) против полного запрета админки через MCP.
4. Опасные тулы включаются админом поимённо; пользователь облака сам их включить не может (M6).
5. ЭП через MCP: только `sign_submission`, опасный тул с правом токена `sign`, без пароля ключа (M6).
6. Журнал пишет каждый вызов, включая чтение, в общий аудит (M10): объём аудита вырастет.
7. Лимит `MCP_CALL` 120 в минуту на пользователя (M11).
8. Локальный MCP на порту Студии без отдельного порта (M12).
9. stdio как мост к работающей Студии, а не самостоятельный процесс (M13).
10. Отдельного экспорта проекта архивом не делаем (раздел 5).

## 11. Развилки на будущее

- Сессии Streamable HTTP с уведомлениями о ходе сборки (progress) и подпиской на ресурсы (`resources/subscribe`) на изменения файлов.
- Подтверждение опасных тулов через elicitation клиента вместо выключения.
- Квота на вызовы MCP в `core/quotas` (сейчас только лимит частоты).
- Тулы встроенного агента из `use_cases/mcp/tools` (`write_file`, `list_files`, `run_checks`) в каталог агента.
