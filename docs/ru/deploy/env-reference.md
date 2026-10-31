---
title: Переменные окружения
description: Все настройки бэкенда, которые задаются переменными окружения HSE_STUDIO__*.
tags:
  - Развёртывание
  - Справочник
---

<!-- Файл сгенерирован scripts/gen_env_reference.py из pydantic Settings. Не правьте его руками. -->

# Переменные окружения

Имя переменной строится из префикса `HSE_STUDIO__` и пути поля; вложенные группы разделяются `__`, регистр не важен. Значения можно положить и в файл `.env`.

Режим «server» означает, что настройка действует только на общем сервере, «оба» значит, что она работает и в локальной установке. Секреты помечены 🔒, их значения по умолчанию не показываются: задавайте их через окружение или docker secrets.

| Переменная | Тип | По умолчанию | Режим | Описание |
|---|---|---|---|---|
| `HSE_STUDIO__SERVER__HOST` | str | `0.0.0.0` | оба | Server bind address |
| `HSE_STUDIO__SERVER__PORT` | int | `17240` | оба | Server port |
| `HSE_STUDIO__SERVER__WORKERS` | int | `1` | оба | Number of worker processes |
| `HSE_STUDIO__SERVER__TIMEOUT_KEEP_ALIVE` | int | `5` | оба | Keep-alive timeout in seconds |
| `HSE_STUDIO__SERVER__TIMEOUT_GRACEFUL_SHUTDOWN` | int | `10` | оба | Graceful shutdown timeout in seconds |
| `HSE_STUDIO__SERVER__ACCESS_LOG` | bool | `false` | оба | Enable uvicorn access log |
| `HSE_STUDIO__SERVER__PROXY_HEADERS` | bool | `false` | оба | Пусть uvicorn сам подменяет адрес клиента по X-Forwarded-For. Выключено: адрес за прокси определяет client_ip() по auth.trusted_proxies, иначе любой пир подставит себе произвольный адрес. |
| `HSE_STUDIO__SERVER__FORWARDED_ALLOW_IPS` | str | `127.0.0.1` | оба | Пиры, чьим заголовкам верит uvicorn при proxy_headers=true |
| `HSE_STUDIO__SERVER__PROJECTS_ROOT` | Path | не задано | оба | Корень томов проектов сервера (projects_root/<project_id>); по умолчанию data_dir/projects. |
| `HSE_STUDIO__SERVER__INSTANCE_NAME` | str | не задано | оба | Название установки из окружения: заданное побеждает правку админа и не меняется в админке. |
| `HSE_STUDIO__SERVER__DOCS_URL` | str | не задано | оба | Ссылка на документацию установки из окружения: заданная не меняется в админке. |
| `HSE_STUDIO__SERVER__PROJECT_RETENTION_DAYS` | int | `30` | оба | Через сколько суток удалённый проект стирается с тома и из каталога; 0 выключает стирание. |
| `HSE_STUDIO__SERVER__PROJECT_PURGE_INTERVAL_S` | float | `3600.0` | оба | Как часто сервер ищет удалённые проекты с истёкшим сроком. |
| `HSE_STUDIO__SERVER__AUDIT_RETENTION_DAYS` | int | `365` | оба | Сколько суток хранится журнал аудита; 0 хранит его без срока. |
| `HSE_STUDIO__SERVER__AUDIT_PURGE_INTERVAL_S` | float | `86400.0` | оба | Как часто сервер стирает события аудита старше срока хранения. |
| `HSE_STUDIO__SERVER__COMPILE_RECORDS_PER_DOCUMENT` | int | `50` | оба | Сколько последних записей сборок хранится на документ; старые стираются при записи новой. |
| `HSE_STUDIO__SERVER__COMPILE_LOG_LIMIT_BYTES` | int | `1048576` | оба | Предел размера лога в записи сборки; у более длинного лога теряется начало. |
| `HSE_STUDIO__SERVER__BLOB_GC_INTERVAL_S` | float | `3600.0` | оба | Как часто сервер стирает блобы входа задач, на которые давно нет ссылок. |
| `HSE_STUDIO__SERVER__BLOB_GC_MIN_AGE_DAYS` | float | `14.0` | оба | Сколько суток блоб живёт без упоминаний в манифестах до удаления; 0 выключает сборку мусора. |
| `HSE_STUDIO__SERVER__MANIFEST_MAX_FILE_BYTES` | int | `268435456` | оба | Предел размера одного файла во входе задачи; больший файл даёт типизированный отказ. |
| `HSE_STUDIO__SERVER__MANIFEST_MAX_JOB_BYTES` | int | `1073741824` | оба | Предел суммарного размера входа одной задачи; не зависит от квоты проекта. |
| `HSE_STUDIO__SERVER__PROJECT_QUOTA_BYTES` | int | `2147483648` | оба | Предел размера проекта (дерево, git-стор, S3); запись сверх него отклоняется, 0 без предела. |
| `HSE_STUDIO__SERVER__PROJECT_IMPORT_MAX_BYTES` | int | `524288000` | оба | Предел размера проекта в архиве при импорте (после распаковки); не больше предела проекта. |
| `HSE_STUDIO__SERVER__PROJECT_IMPORT_MAX_FILES` | int | `50000` | оба | Сколько файлов допускается в архиве проекта при импорте. |
| `HSE_STUDIO__SERVER__PROJECT_QUOTA_WARN_PERCENT` | int | `80` | оба | С какого процента предела статус проекта предупреждает о нехватке места. |
| `HSE_STUDIO__SERVER__PROJECT_USAGE_INTERVAL_S` | float | `3600.0` | оба | Как часто сервер переизмеряет размер проектов (пачкой самых давних). |
| `HSE_STUDIO__SERVER__PROJECT_USAGE_BATCH` | int | `20` | оба | Сколько проектов измеряется за один прогон. |
| `HSE_STUDIO__SERVER__ORPHAN_GC_INTERVAL_S` | float | `21600.0` | оба | Как часто сервер ищет папки тома и префиксы S3 без записи в projects. |
| `HSE_STUDIO__SERVER__ORPHAN_GC_MIN_AGE_HOURS` | float | `24.0` | оба | Сколько часов сирота должен пролежать, прежде чем его удалят. |
| `HSE_STUDIO__SERVER__JOB_RETENTION_DAYS` | int | `30` | оба | Через сколько суток после применения результата терминальная задача и её лог стираются; 0 выключает стирание. |
| `HSE_STUDIO__SERVER__JOB_RETENTION_INTERVAL_S` | float | `21600.0` | оба | Как часто сервер убирает выходы задач без владельца и устаревшие записи задач. |
| `HSE_STUDIO__SERVER__JOB_OUTPUT_MIN_AGE_HOURS` | float | `24.0` | оба | Сколько часов выходы терминальной или неизвестной задачи в S3 должны пролежать, прежде чем их удалят. |
| `HSE_STUDIO__SERVER__AUTH_CLEANUP_INTERVAL_S` | float | `3600.0` | оба | Как часто сервер стирает просроченные сессии, токены, письма outbox и счётчики входов. |
| `HSE_STUDIO__CORS__ALLOW_ORIGINS` | `list[str]` | `http://localhost:3000`, `http://localhost:5173`, `http://localhost:17240` | оба | Allowed origins |
| `HSE_STUDIO__CORS__ALLOW_CREDENTIALS` | bool | `true` | оба | Отдавать Access-Control-Allow-Credentials (cookie и заголовки авторизации). |
| `HSE_STUDIO__CORS__ALLOW_METHODS` | `list[str]` | `*` | оба | Разрешённые методы CORS. |
| `HSE_STUDIO__CORS__ALLOW_HEADERS` | `list[str]` | `*` | оба | Разрешённые заголовки запроса CORS. |
| `HSE_STUDIO__LOGGING__LEVEL` | str | `INFO` | оба | Log level |
| `HSE_STUDIO__LOGGING__USE_JSON` | bool | `false` | оба | JSON format (False = console) |
| `HSE_STUDIO__COMPILE__IMAGE` | str | `texlive/texlive:latest` | оба | Default active image when the user hasn't picked one in Settings → Образы. |
| `HSE_STUDIO__COMPILE__ALLOWED_REPOS` | `list[str]` | `texlive/texlive` | оба | Docker Hub repos the UI is allowed to list, pull and activate. Acts as a security allowlist — without it the API could pull arbitrary images. |
| `HSE_STUDIO__COMPILE__DOCKER_HUB_BASE` | str | `https://hub.docker.com/v2` | оба | Docker Hub v2 API base URL used to fetch tag lists. |
| `HSE_STUDIO__COMPILE__CACHE_VOLUME_NAME` | str | `hse-tex-cache` | оба | Named Docker volume that persists font/format caches across compiles. |
| `HSE_STUDIO__COMPILE__CACHE_VOLUME_TARGET` | str | `/root` | оба | Mount target for the cache volume inside the TeX container. |
| `HSE_STUDIO__COMPILE__IDLE_TIMEOUT_S` | float | `120.0` | оба | Kill the build if no output is produced for this many seconds. |
| `HSE_STUDIO__COMPILE__DEFAULT_MAX_ITERATIONS` | int | `5` | оба | Fallback for latexmk $max_repeat when the user setting is missing. |
| `HSE_STUDIO__COMPILE__PREFETCH_IMAGE` | bool | `true` | оба | Pull the TeX image in the background once the install is configured. |
| `HSE_STUDIO__COMPILE__PROJECTS_HOST_PATH` | str | не задано | оба | Host-side root of the projects bind mount; required when backend runs in Docker. |
| `HSE_STUDIO__COMPILE__PROJECTS_CONTAINER_PATH` | str | не задано | оба | In-container mount point of projects; required when backend runs in Docker. |
| `HSE_STUDIO__FONTS__DIR_NAME` | str | `fonts` | оба | Subdirectory of data_dir holding the fonts. |
| `HSE_STUDIO__FONTS__SYSTEM_DIRS` | `list[str]` | пусто | оба | Explicit font roots to scan instead of the OS ones (host fonts bind-mounted into the container). |
| `HSE_STUDIO__FONTS__HOST_DIR` | str | не задано | оба | Explicit HOST font directory; empty means auto-detection over the known OS locations. |
| `HSE_STUDIO__FONTS__CONTAINER_MOUNT` | str | `/usr/local/share/fonts/hse` | оба | Where the fonts folder is mounted inside the TeX container (a fontconfig-scanned path). |
| `HSE_STUDIO__FONTS__ALLOWED_EXTENSIONS` | `list[str]` | `.ttf`, `.otf`, `.ttc` | оба | Расширения файлов, которые принимаются как шрифты. |
| `HSE_STUDIO__FONTS__DOWNLOAD_TIMEOUT_S` | float | `60.0` | оба | Per-file download timeout for catalog installs. |
| `HSE_STUDIO__FONTS__CATALOG` | `list[FontCatalogEntryConfig]` | встроенный список (7) | оба | Каталог рекомендуемых бесплатных шрифтов с кириллицей. |
| `HSE_STUDIO__FONTS__MARKETPLACE_METADATA_URL` | str | `https://fonts.google.com/metadata/fonts` | оба | GF metadata (family/category/subsets) for the marketplace inventory. |
| `HSE_STUDIO__FONTS__MARKETPLACE_TREE_URL` | str | `https://api.github.com/repos/google/fonts/git/trees/main?recursive=1` | оба | github.com/google/fonts file tree — source of static TTF download URLs. |
| `HSE_STUDIO__FONTS__MARKETPLACE_INDEX_TTL_S` | float | `86400.0` | оба | How long the in-memory marketplace index is reused before a refresh (seconds). |
| `HSE_STUDIO__FONTS__MARKETPLACE_FETCH_TIMEOUT_S` | float | `60.0` | оба | Timeout for the marketplace index fetches (tree + metadata). |
| `HSE_STUDIO__LANGUAGETOOL__IMAGE` | str | `erikvl87/languagetool:latest` | оба | Default LanguageTool image when the user hasn't picked one in Settings. |
| `HSE_STUDIO__LANGUAGETOOL__ALLOWED_REPOS` | `list[str]` | `erikvl87/languagetool` | оба | Docker Hub repos the UI may list/pull/run for LanguageTool (allowlist, separate from compile). |
| `HSE_STUDIO__LANGUAGETOOL__DOCKER_HUB_BASE` | str | `https://hub.docker.com/v2` | оба | Docker Hub v2 API base URL used to fetch LanguageTool tag lists. |
| `HSE_STUDIO__LANGUAGETOOL__CONTAINER_NAME` | str | `hse-languagetool` | оба | Stable name of the managed LanguageTool container (used to adopt/reconcile across restarts). |
| `HSE_STUDIO__LANGUAGETOOL__CONTAINER_PORT` | int | `8010` | оба | Port LanguageTool listens on inside the container; published to a free host port. |
| `HSE_STUDIO__LANGUAGETOOL__HEALTH_PATH` | str | `/v2/languages` | оба | HTTP path polled to decide the container is up and serving. |
| `HSE_STUDIO__LANGUAGETOOL__MODEL_VOLUME_NAME` | str | `hse-languagetool-cache` | оба | Named Docker volume persisting n-gram/model data across container restarts. |
| `HSE_STUDIO__LANGUAGETOOL__REQUEST_TIMEOUT_S` | float | `30.0` | оба | Timeout for a single LanguageTool /v2/check request (large documents are slow). |
| `HSE_STUDIO__LANGUAGETOOL__HEALTH_TIMEOUT_S` | float | `5.0` | оба | Timeout for a single container health probe. |
| `HSE_STUDIO__LANGUAGETOOL__STARTUP_TIMEOUT_S` | float | `90.0` | оба | How long to wait for the container to become healthy after start. |
| `HSE_STUDIO__LANGUAGETOOL__IDLE_TIMEOUT_S` | float | `600.0` | оба | Stop the auto-started container after this many seconds with no checks (frees RAM). |
| `HSE_STUDIO__LANGUAGETOOL__STOP_ON_SHUTDOWN` | bool | `true` | оба | Stop the managed container when the backend shuts down (it auto-starts again on demand). |
| `HSE_STUDIO__LANGUAGETOOL__POOL_REPLICAS` | `list[str]` | пусто | оба | Серверный режим: URL реплик LanguageTool за общим пулом (…LANGUAGETOOL__POOL_REPLICAS). |
| `HSE_STUDIO__LANGUAGETOOL__POOL_MAX_INFLIGHT` | int | `4` | оба | Одновременных запросов на одну реплику пула. |
| `HSE_STUDIO__LANGUAGETOOL__POOL_USER_RATE_PER_S` | float | `2.0` | оба | Пополнение доли пользователя, запросов в секунду. |
| `HSE_STUDIO__LANGUAGETOOL__POOL_USER_BURST` | int | `20` | оба | Запас запросов у пользователя. |
| `HSE_STUDIO__LANGUAGETOOL__POOL_CIRCUIT_FAILURES` | int | `3` | оба | Подряд неудач реплики до размыкания цепи. |
| `HSE_STUDIO__LANGUAGETOOL__POOL_CIRCUIT_OPEN_S` | float | `30.0` | оба | Сколько реплика исключена после размыкания. |
| `HSE_STUDIO__LANGUAGETOOL__POOL_CACHE_ENTRIES` | int | `2048` | оба | Размер LRU-кэша абзацев прокси, 0 выключает. |
| `HSE_STUDIO__LANGUAGETOOL__POOL_MAX_TEXT_CHARS` | int | `400000` | оба | Наибольший текст одного запроса к прокси. |
| `HSE_STUDIO__OFFICE_CONVERT__IMAGE` | str | `gotenberg/gotenberg:8` | оба | Default Gotenberg image when the user hasn't picked one in Settings (office→PDF conversion). |
| `HSE_STUDIO__OFFICE_CONVERT__ALLOWED_REPOS` | `list[str]` | `gotenberg/gotenberg` | оба | Docker Hub repos the UI may list/pull/run for the convert service (allowlist, as LanguageTool). |
| `HSE_STUDIO__OFFICE_CONVERT__DOCKER_HUB_BASE` | str | `https://hub.docker.com/v2` | оба | Docker Hub v2 API base URL used to fetch Gotenberg tag lists. |
| `HSE_STUDIO__OFFICE_CONVERT__CONTAINER_NAME` | str | `hse-office-convert` | оба | Stable name of the managed Gotenberg container (adopted across backend restarts). |
| `HSE_STUDIO__OFFICE_CONVERT__CONTAINER_PORT` | int | `3000` | оба | Port Gotenberg listens on inside the container; published to a free host port. |
| `HSE_STUDIO__OFFICE_CONVERT__HEALTH_PATH` | str | `/health` | оба | HTTP path polled to decide the container is up and serving. |
| `HSE_STUDIO__OFFICE_CONVERT__CONVERT_TIMEOUT_S` | float | `120.0` | оба | Timeout for a single LibreOffice conversion request (large decks are slow). |
| `HSE_STUDIO__OFFICE_CONVERT__HEALTH_TIMEOUT_S` | float | `5.0` | оба | Timeout for a single container health probe. |
| `HSE_STUDIO__OFFICE_CONVERT__STARTUP_TIMEOUT_S` | float | `60.0` | оба | How long to wait for the container to become healthy after start. |
| `HSE_STUDIO__OFFICE_CONVERT__IDLE_TIMEOUT_S` | float | `600.0` | оба | Stop the auto-started container after this many seconds without conversions (frees RAM). |
| `HSE_STUDIO__OFFICE_EDITOR__IMAGE` | str | `onlyoffice/documentserver:latest` | оба | Default ONLYOFFICE Document Server image when the user hasn't picked one in Settings. |
| `HSE_STUDIO__OFFICE_EDITOR__ALLOWED_REPOS` | `list[str]` | `onlyoffice/documentserver` | оба | Docker Hub repos the UI may list/pull/run for the editor service (allowlist, as LanguageTool). |
| `HSE_STUDIO__OFFICE_EDITOR__DOCKER_HUB_BASE` | str | `https://hub.docker.com/v2` | оба | Docker Hub v2 API base URL used to fetch Document Server tag lists. |
| `HSE_STUDIO__OFFICE_EDITOR__CONTAINER_NAME` | str | `hse-office-editor` | оба | Stable name of the managed Document Server container (adopted across backend restarts). |
| `HSE_STUDIO__OFFICE_EDITOR__CONTAINER_PORT` | int | `80` | оба | Port Document Server listens on inside the container; published to a free host port. |
| `HSE_STUDIO__OFFICE_EDITOR__HEALTH_PATH` | str | `/healthcheck` | оба | HTTP path polled to decide the container is up and serving (body must contain 'true'). |
| `HSE_STUDIO__OFFICE_EDITOR__STARTUP_TIMEOUT_S` | float | `180.0` | оба | How long to wait for the container to become healthy after start (DS is slow to boot). |
| `HSE_STUDIO__OFFICE_EDITOR__HEALTH_TIMEOUT_S` | float | `5.0` | оба | Timeout for a single container health probe. |
| `HSE_STUDIO__OFFICE_EDITOR__IDLE_TIMEOUT_S` | float | `1800.0` | оба | Stop the auto-started container after this many seconds without editor activity (frees RAM). |
| `HSE_STUDIO__OFFICE_EDITOR__BACKEND_HOST_FOR_CONTAINER` | str | `host.docker.internal` | оба | How the Document Server container reaches THIS backend (document download + save callback). host.docker.internal works natively via --add-host=host-gateway; compose deployments may override with the backend service name. |
| `HSE_STUDIO__OFFICE_EDITOR__POOL_REPLICAS` | `list[str]` | пусто | оба | Server mode: base URLs of the Document Server replicas (empty means the editor is unavailable). A document is pinned to one replica by rendezvous hashing of its key. |
| `HSE_STUDIO__OFFICE_EDITOR__POOL_MAX_SESSIONS` | int | `18` | оба | Concurrent editing sessions across the installation (Community Edition allows about 20). |
| `HSE_STUDIO__OFFICE_EDITOR__POOL_SESSION_TTL_S` | float | `1800.0` | оба | A session without a callback or keepalive for this long is released. |
| `HSE_STUDIO__OFFICE_EDITOR__POOL_PROBE_INTERVAL_S` | float | `15.0` | оба | How often replica health is re-polled. |
| `HSE_STUDIO__OFFICE_EDITOR__POOL_RETRY_AFTER_S` | int | `30` | оба | Retry hint returned with the editor_busy state. |
| `HSE_STUDIO__OFFICE_EDITOR__JWT_SECRET` 🔒 | str | секрет, не печатается | оба | Server mode: JWT secret shared with all replicas; derived from the key ring if empty. |
| `HSE_STUDIO__OFFICE_EDITOR__BACKEND_INTERNAL_URL` | str | пусто | оба | Server mode: base URL of this API as the Document Server replicas see it (document and callback). |
| `HSE_STUDIO__OFFICE_EDITOR__TOKEN_TTL_S` | int | `43200` | оба | Lifetime of the signed document and callback tokens (a long editing session needs saves). |
| `HSE_STUDIO__OLLAMA__IMAGE` | str | `ollama/ollama:latest` | оба | Docker image used for the managed (fallback) Ollama container. |
| `HSE_STUDIO__OLLAMA__CONTAINER_NAME` | str | `hse-ollama` | оба | Stable name of the managed Ollama container (adopt/reconcile across restarts). |
| `HSE_STUDIO__OLLAMA__CONTAINER_PORT` | int | `11434` | оба | Port Ollama listens on inside the container. |
| `HSE_STUDIO__OLLAMA__HOST_PORT` | int | `11434` | оба | Preferred host port to publish (Ollama's default; a free port is used if it's taken). |
| `HSE_STUDIO__OLLAMA__LOCAL_BASE_URL` | str | `http://127.0.0.1:11434` | оба | Endpoint probed for a native Ollama and used as the managed provider's base URL. |
| `HSE_STUDIO__OLLAMA__HEALTH_PATH` | str | `/api/tags` | оба | HTTP path polled to decide Ollama is up and serving. |
| `HSE_STUDIO__OLLAMA__MODEL_VOLUME_NAME` | str | `hse-ollama-models` | оба | Named Docker volume persisting pulled models across container restarts. |
| `HSE_STUDIO__OLLAMA__REQUEST_TIMEOUT_S` | float | `60.0` | оба | Timeout for status/list/delete calls (NOT model pulls, which stream without a read timeout). |
| `HSE_STUDIO__OLLAMA__HEALTH_TIMEOUT_S` | float | `5.0` | оба | Timeout for a single runtime health probe. |
| `HSE_STUDIO__OLLAMA__STARTUP_TIMEOUT_S` | float | `120.0` | оба | How long to wait for the managed container to become healthy after start. |
| `HSE_STUDIO__OLLAMA__IDLE_TIMEOUT_S` | float | `1800.0` | оба | Stop the managed container after this many seconds idle (frees RAM/VRAM). |
| `HSE_STUDIO__OLLAMA__STOP_ON_SHUTDOWN` | bool | `true` | оба | Stop the managed container when the backend shuts down (auto-starts again on demand). |
| `HSE_STUDIO__OLLAMA__KEEP_ALIVE` | str | `5m` | оба | How long Ollama keeps a model loaded in RAM/VRAM after the last request, set as OLLAMA_KEEP_ALIVE on the managed container. '5m' = default, '0' = unload immediately, '-1' = keep loaded. Frees memory automatically between uses. |
| `HSE_STUDIO__OLLAMA__PROVIDER_NAME` | str | `Ollama` | оба | Display name of the auto-managed AI provider record that points at the local runtime. |
| `HSE_STUDIO__OLLAMA__ALLOW_CUSTOM_MODELS` | bool | `true` | оба | Allow pulling any validly-named model (free-text / registry search), not just the catalog. |
| `HSE_STUDIO__OLLAMA__REGISTRY_SEARCH_URL` | str | `https://ollama.com/search` | оба | ollama.com search page scraped for live model discovery (best-effort, graceful on failure). |
| `HSE_STUDIO__OLLAMA__REGISTRY_TIMEOUT_S` | float | `10.0` | оба | Timeout for a single registry search request. |
| `HSE_STUDIO__OLLAMA__MAX_CONCURRENT_PULLS` | int | `2` | оба | Max simultaneous background model downloads (bounds disk/network use). |
| `HSE_STUDIO__OLLAMA__CATALOG` | `list[OllamaCatalogEntry]` | встроенный список (16) | оба | Curated local models offered in the UI (the recommended starting set, not a hard allowlist). |
| `HSE_STUDIO__AGENT__TOKEN_BUDGET` | int | `128000` | оба | Conservative context-token ceiling per turn; real per-model window may override it. |
| `HSE_STUDIO__AGENT__MAX_ITERATIONS` | int | `25` | оба | Hard cap on tool-call iterations in a single turn (stops runaway loops). |
| `HSE_STUDIO__AGENT__MAX_OUTPUT_TOKENS` | int | `4096` | оба | Max tokens the model may generate per round-trip. |
| `HSE_STUDIO__AGENT__TEMPERATURE` | float | `0.2` | оба | Sampling temperature for agent turns. |
| `HSE_STUDIO__AGENT__MAX_TOOL_RESULT_TOKENS` | int | `25000` | оба | Token cap applied to a single tool result before it re-enters context (then paginated). |
| `HSE_STUDIO__AGENT__COMPACTION_TRIGGER_RATIO` | float | `0.75` | оба | Compact history once the estimated context reaches this fraction of token_budget. |
| `HSE_STUDIO__AGENT__KEEP_RECENT_TOKENS` | int | `24000` | оба | Always keep at least this much of the most recent transcript verbatim when compacting. |
| `HSE_STUDIO__AGENT__KEEP_RECENT_MESSAGES_MIN` | int | `6` | оба | Always keep at least this many recent messages verbatim when compacting. |
| `HSE_STUDIO__AGENT__SUMMARY_MAX_TOKENS` | int | `1500` | оба | Max tokens for a rolling compaction summary. |
| `HSE_STUDIO__AGENT__AUTO_APPROVE_WRITES` | bool | `false` | оба | When True, write/exec tools run without an explicit per-call approval prompt. |
| `HSE_STUDIO__AGENT__RETENTION_RUNS` | int | `200` | оба | Max run records kept per session before the oldest are pruned (0 = unbounded). |
| `HSE_STUDIO__AGENT__RETENTION_MAX_TRANSCRIPT_BYTES` | int | `0` | оба | When >0, archive already-compacted transcript lines once a session exceeds this size. |
| `HSE_STUDIO__AGENT__DEBUG_TRACE` | bool | `false` | оба | When True, write a verbose per-run JSONL trace (exact request, every raw stream chunk, the parsed turn, tool dispatch) to `<debug_trace_dir>/<run>.jsonl`. Diagnostic only; off by default. Enable with HSE_STUDIO__AGENT__DEBUG_TRACE=true. |
| `HSE_STUDIO__AGENT__DEBUG_TRACE_DIR` | Path | не задано | оба | Directory for debug-trace files. None → `<data_dir>/agent-traces`. |
| `HSE_STUDIO__AGENT__DEBUG_TRACE_KEEP` | int | `50` | оба | Max trace files kept (oldest pruned). 0 = unbounded. |
| `HSE_STUDIO__VCS__ENABLED` | bool | `true` | оба | Master switch for ProjectVCS auto-tracking. |
| `HSE_STUDIO__VCS__DEFAULT_BRANCH` | str | `master` | оба | Initial branch name for a new project store. |
| `HSE_STUDIO__VCS__AUTHOR_NAME` | str | `HSE Studio` | оба | Committer name for service commits. |
| `HSE_STUDIO__VCS__AUTHOR_EMAIL` | str | `bot@hse-studio.local` | оба | Committer email for service commits. |
| `HSE_STUDIO__VCS__DIFF_MAX_BYTES` | int | `256000` | оба | Byte budget for an assembled diff before truncation. |
| `HSE_STUDIO__VCS__TRACK_PDF` | bool | `false` | оба | Global default for whether compiled PDFs enter history (per-project setting overrides). |
| `HSE_STUDIO__VCS__EDIT_MIN_INTERVAL_SECONDS` | float | `5.0` | оба | Throttle window for edit-commits (phase 2); edits within it are folded into the next commit. |
| `HSE_STUDIO__GIT__ENABLED` | bool | `true` | оба | Master switch for remotes, sync and clone from git. |
| `HSE_STUDIO__GIT__SSH_BINARY` | str | `ssh` | оба | ssh client used for ssh:// and scp-like remotes. |
| `HSE_STUDIO__GIT__SSH_KEYSCAN_BINARY` | str | `ssh-keyscan` | оба | Tool that reads host keys of an ssh server. |
| `HSE_STUDIO__GIT__SCAN_TIMEOUT_S` | float | `10.0` | оба | Timeout for reading the host keys of a server. |
| `HSE_STUDIO__GIT__GIT_MIN_VERSION` | str | `2.31` | оба | Oldest git the sync works with; older reports git_unavailable. |
| `HSE_STUDIO__GIT__ALLOW_INSECURE_HTTP` | bool | `false` | оба | Allow plain http remotes (each remote must opt in too). Off: tokens would travel in clear. |
| `HSE_STUDIO__GIT__ALLOW_LOCAL_REMOTES` | bool | `true` | оба | Allow file:// and absolute-path remotes. Local mode only; a shared server never allows them. |
| `HSE_STUDIO__GIT__PROBE_TIMEOUT_S` | float | `20.0` | оба | Timeout for checking a remote address. |
| `HSE_STUDIO__GIT__PROVIDER_DETECT_TIMEOUT_S` | float | `3.0` | оба | Timeout of each request that recognizes a git server (GitLab, Gitea, GitHub Enterprise). |
| `HSE_STUDIO__GIT__TOKEN_CHECK_TIMEOUT_S` | float | `10.0` | оба | Timeout of a request to the hosting API that tells whose token it is and its scopes. |
| `HSE_STUDIO__GIT__FETCH_TIMEOUT_S` | float | `120.0` | оба | Timeout for one fetch. |
| `HSE_STUDIO__GIT__PUSH_TIMEOUT_S` | float | `300.0` | оба | Timeout for one push. |
| `HSE_STUDIO__GIT__CLONE_TIMEOUT_S` | float | `900.0` | оба | Timeout for cloning and the first push of a long history. |
| `HSE_STUDIO__GIT__BUNDLE_TIMEOUT_S` | float | `600.0` | оба | Timeout for one git command over a bundle file (create, verify, unpack). |
| `HSE_STUDIO__GIT__BUNDLE_MAX_BYTES` | int | `2000000000` | оба | Largest bundle file the Studio accepts for import or for cloning a project. |
| `HSE_STUDIO__GIT__MAX_INCOMING_BLOB_BYTES` | int | `512000000` | оба | Largest single file of a remote branch the Studio reads into memory and writes to the project. A tiny pack can expand into a huge blob, so a sync, a clone or an import refuses bigger files. |
| `HSE_STUDIO__GIT__MAX_INCOMING_TOTAL_BYTES` | int | `2000000000` | оба | Largest total size of the files one sync, clone or import takes from a remote branch. |
| `HSE_STUDIO__GIT__FETCH_TICK_S` | float | `30.0` | оба | How often the background fetch looks for projects that are due. |
| `HSE_STUDIO__GIT__FETCH_STARTUP_DELAY_S` | float | `60.0` | оба | Delay before the first background fetch after the server starts. |
| `HSE_STUDIO__GIT__FETCH_CONCURRENCY` | int | `2` | оба | Projects fetched in the background at the same time. |
| `HSE_STUDIO__GIT__LARGE_FILE_WARN_BYTES` | int | `95000000` | оба | Blobs from this size are reported before push: hosting services reject files near 100 MB. |
| `HSE_STUDIO__GIT_REMOTE__ENABLED` | bool | `true` | оба | Отдавать проекты по git (clone, fetch, push) на /git/<id>.git. |
| `HSE_STUDIO__GIT_REMOTE__MAX_PUSH_BYTES` | int | `268435456` | оба | Предел тела одного push в байтах (и receive.maxInputSize). |
| `HSE_STUDIO__GIT_REMOTE__MAX_CONCURRENT_PER_USER` | int | `4` | оба | Сколько запросов git одного человека выполняются одновременно. |
| `HSE_STUDIO__GIT_REMOTE__TIMEOUT_S` | int | `600` | оба | Предел одного процесса git upload-pack или receive-pack. |
| `HSE_STUDIO__GIT_REMOTE__LOCK_WAIT_S` | int | `30` | оба | Сколько push ждёт замок папки проекта. |
| `HSE_STUDIO__SECRETS__KEY` 🔒 | str | секрет, не печатается | оба | Fernet key (urlsafe base64 of 32 bytes) taken from the environment. |
| `HSE_STUDIO__SECRETS__KEY_FILE` | Path | не задано | оба | File holding the Fernet key (docker secret). |
| `HSE_STUDIO__SECRETS__RETIRED_KEYS` 🔒 | str | секрет, не печатается | оба | Retired Fernet keys, comma separated: they only decrypt, which makes key rotation possible. |
| `HSE_STUDIO__JOBS__ROUND_TRIP_PAYLOADS` | bool | `false` | оба | Пропускать каждую задачу и её результат через проводной кодек (как при удалённом раннере). Для тестов: ловит живые объекты в нагрузке; в обычной работе выключено. |
| `HSE_STUDIO__JOBS__LEASE_S` | float | `45.0` | оба | Срок аренды задачи раннером: heartbeat продлевает её, без него задача возвращается. |
| `HSE_STUDIO__JOBS__REAPER_INTERVAL_S` | float | `5.0` | оба | Как часто сервер возвращает задачи с истёкшей арендой и проверяет таймауты. |
| `HSE_STUDIO__JOBS__TIMEOUT_GRACE_S` | float | `15.0` | оба | Сколько раннер получает на остановку задачи после таймаута, прежде чем сервер закончит её сам. |
| `HSE_STUDIO__JOBS__RUNNER_BOOTSTRAP_TOKEN` 🔒 | str | секрет, не печатается | оба | Одноразовый токен регистрации первого раннера. api кладёт его хеш в базу при старте; после регистрации раннера уберите значение из окружения. |
| `HSE_STUDIO__JOBS__BUILD_TIMEOUT_S` | int | не задано | оба | Предел длительности сборки из окружения: заданный побеждает правку админа. |
| `HSE_STUDIO__JOBS__ARTIFACT_RETENTION_DAYS` | int | не задано | оба | Срок хранения результатов сборок из окружения: заданный побеждает правку админа. |
| `HSE_STUDIO__JOBS__PERSONAL_RUNNERS_ENABLED` | bool | не задано | оба | Разрешены ли личные раннеры людей; заданное окружением побеждает правку админа (по умолчанию да). |
| `HSE_STUDIO__JOBS__PERSONAL_RUNNER_WAIT_S` | int | не задано | оба | Сколько секунд сборка ждёт личный раннер, прежде чем её возьмёт общий (по умолчанию 5). |
| `HSE_STUDIO__JOBS__PERSONAL_RUNNERS_MAX_PER_USER` | int | не задано | оба | Сколько неотозванных личных раннеров может быть у человека (по умолчанию 5). |
| `HSE_STUDIO__JOBS__STORAGE_DIR` | Path | не задано | оба | Каталог лога задач; блобы входа и выходы лежат в объектном хранилище. По умолчанию data_dir/jobs. |
| `HSE_STUDIO__JOBS__MAX_ARTIFACT_BYTES` | int | `536870912` | оба | Предел одного выхода задачи; больший отвергается при заявке. |
| `HSE_STUDIO__JOBS__MAX_LOG_BYTES` | int | `8388608` | оба | Предел лога одной попытки; остальное отбрасывается. |
| `HSE_STUDIO__JOBS__RELAY_PICKUP_S` | float | `10.0` | оба | Сколько ждать, пока личный раннер заберёт тело запроса к модели. |
| `HSE_STUDIO__JOBS__RELAY_MAX_REQUEST_BYTES` | int | `8388608` | оба | Предел тела запроса к модели через личный раннер. |
| `HSE_STUDIO__JOBS__RELAY_MAX_RESPONSE_BYTES` | int | `67108864` | оба | Предел ответа модели через личный раннер; больший обрывается. |
| `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_PER_USER` | int | `8` | оба | Одновременных ретрансляций ИИ на человека (в очереди и идущих). |
| `HSE_STUDIO__JOBS__RELAY_MAX_DURATION_S` | float | `900.0` | оба | Потолок длительности одной ретрансляции ИИ. |
| `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_BYTES_PER_USER` | int | `16777216` | оба | Сумма тел запросов к моделям одного человека в памяти api. |
| `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_TOTAL` | int | `32` | оба | Одновременных ретрансляций ИИ на весь процесс api (все люди). |
| `HSE_STUDIO__JOBS__RELAY_MAX_PENDING_BYTES_TOTAL` | int | `134217728` | оба | Сумма тел запросов к моделям в памяти api (все люди). |
| `HSE_STUDIO__AUTH__PUBLIC_URL` | str | не задано | server | Внешний адрес Студии (https://studio.example.org). По схеме выбирается Secure у cookie и HSTS, адрес входит в список допустимых Origin для небезопасных запросов. |
| `HSE_STUDIO__AUTH__FRAME_ANCESTORS` | `list[str]` | пусто | server | Дополнительные источники, которым разрешено встраивать страницы Студии (frame-ancestors). |
| `HSE_STUDIO__AUTH__TRUSTED_PROXIES` | `list[str]` | пусто | server | IP и CIDR обратных прокси, чьему X-Forwarded-For верим при определении адреса клиента. |
| `HSE_STUDIO__AUTH__SESSION_IDLE_DAYS` | int | `7` | server | Сессия гаснет без активности столько дней (скользящий срок). |
| `HSE_STUDIO__AUTH__SESSION_ABSOLUTE_DAYS` | int | `30` | server | Предельный возраст сессии, после которого нужен новый вход. |
| `HSE_STUDIO__AUTH__REGISTRATION_MODE` | open / domains / invite / closed | не задано | server | Режим регистрации из окружения: open, domains, invite или closed. Заданное побеждает БД и не правится в админке. |
| `HSE_STUDIO__AUTH__REGISTRATION_DOMAINS` | `list[str]` | не задано | server | Разрешённые домены почты для режима domains; заданный список блокирует правку в админке. |
| `HSE_STUDIO__AUTH__REQUIRE_APPROVAL` | bool | не задано | server | Новые аккаунты ждут одобрения админа; заданное значение блокирует правку в админке. |
| `HSE_STUDIO__AUTH__PASSWORD_ENABLED` | bool | не задано | server | Вход по паролю; заданное значение блокирует правку в админке. |
| `HSE_STUDIO__AUTH__PROJECT_INVITES_ALLOW_SIGNUP` | bool | не задано | server | Приглашение в проект даёт право зарегистрироваться в режиме invite (по умолчанию да); заданное значение блокирует правку в админке. |
| `HSE_STUDIO__AUTH__OIDC__ID` | str | `sso` | server | Идентификатор в адресах входа. |
| `HSE_STUDIO__AUTH__OIDC__LABEL` | str | `SSO` | server | Название на кнопке входа. |
| `HSE_STUDIO__AUTH__OIDC__ISSUER` | str | не задано | server | Адрес издателя (discovery лежит под ним). |
| `HSE_STUDIO__AUTH__OIDC__CLIENT_ID` | str | не задано | server | Идентификатор клиента у провайдера. |
| `HSE_STUDIO__AUTH__OIDC__CLIENT_SECRET` 🔒 | str | секрет, не печатается | server | Секрет клиента. |
| `HSE_STUDIO__AUTH__OIDC__CLIENT_SECRET_FILE` | Path | не задано | server | Файл с секретом клиента (docker secret). |
| `HSE_STUDIO__AUTH__OIDC__SCOPES` | str | `openid email profile` | server | Запрашиваемые области. |
| `HSE_STUDIO__AUTH__OIDC__AUTO_PROVISION` | bool | `false` | server | Создавать аккаунт при первом входе в обход политики регистрации. |
| `HSE_STUDIO__AUTH__ADMIN_EMAIL` | str | не задано | server | Первый администратор из окружения: вместе с паролем создаётся при старте, если админа ещё нет (идемпотентно, пароль существующего не трогается). Рекомендуемый путь для compose и helm. |
| `HSE_STUDIO__AUTH__ADMIN_NAME` | str | не задано | server | Имя первого администратора из окружения. |
| `HSE_STUDIO__AUTH__ADMIN_PASSWORD` 🔒 | str | секрет, не печатается | server | Пароль первого администратора из окружения. |
| `HSE_STUDIO__AUTH__ADMIN_PASSWORD_FILE` | Path | не задано | server | Файл с паролем первого администратора (docker secret). |
| `HSE_STUDIO__AUTH__SETUP_TOKEN_REQUIRED` | bool | не задано | server | Нужен ли токен установки в мастере первого запуска (печатается в журнале api). Не задано: нужен, если сервер слушает не только loopback, задан внешний public_url или trusted_proxies. |
| `HSE_STUDIO__MAIL__HOST` | str | не задано | server | SMTP host; empty means mail is off. |
| `HSE_STUDIO__MAIL__PORT` | int | `587` | server | SMTP port. |
| `HSE_STUDIO__MAIL__SECURITY` | starttls / tls / none | `starttls` | server | starttls upgrades a plain connection, tls connects over TLS at once. |
| `HSE_STUDIO__MAIL__USERNAME` | str | не задано | server | SMTP login; empty means no authentication. |
| `HSE_STUDIO__MAIL__PASSWORD` 🔒 | str | секрет, не печатается | server | SMTP password. |
| `HSE_STUDIO__MAIL__FROM_ADDRESS` | str | `no-reply@localhost` | server | Envelope and From address. |
| `HSE_STUDIO__MAIL__FROM_NAME` | str | `HSE Doc Studio` | server | Sender name shown to recipients. |
| `HSE_STUDIO__MAIL__TIMEOUT_S` | float | `10.0` | server | Connect and command timeout, seconds. |
| `HSE_STUDIO__DB__DSN` 🔒 | str | секрет, не печатается | server | DSN Postgres, например postgresql+asyncpg://user:pass@host:5432/db; без драйвера берётся asyncpg. |
| `HSE_STUDIO__DB__AUTO_MIGRATE` | bool | `false` | server | Мигрировать схему на старте под advisory-локом (compose); в helm выключено, мигрирует job. |
| `HSE_STUDIO__DB__POOL_SIZE` | int | `10` | server | Размер пула соединений. |
| `HSE_STUDIO__DB__MAX_OVERFLOW` | int | `10` | server | Сверх пула в пике. |
| `HSE_STUDIO__DB__ECHO` | bool | `false` | server | Печатать SQL (только для отладки). |
| `HSE_STUDIO__DB__CONNECT_TIMEOUT_S` | float | `10.0` | server | Сколько ждать установки соединения с Postgres. |
| `HSE_STUDIO__DB__COMMAND_TIMEOUT_S` | float | `30.0` | server | Сколько клиент ждёт ответа на команду; защита от зависшей или отрезанной базы. |
| `HSE_STUDIO__DB__POOL_TIMEOUT_S` | float | `10.0` | server | Сколько запрос ждёт свободное соединение из пула. |
| `HSE_STUDIO__DB__STATEMENT_TIMEOUT_S` | float | `30.0` | server | statement_timeout на стороне Postgres; 0 выключает (миграции идут без лимита). |
| `HSE_STUDIO__DB__LOCK_TIMEOUT_S` | float | `10.0` | server | lock_timeout на стороне Postgres: сколько ждать чужую блокировку строки или таблицы. |
| `HSE_STUDIO__DB__MIGRATION_LOCK_WAIT_S` | float | `600.0` | server | Сколько ждать advisory-лок миграций, занятый другим процессом. |
| `HSE_STUDIO__S3__BUCKET` | str | не задано | server | Имя закрытого бакета; пусто означает хранение в каталоге. |
| `HSE_STUDIO__S3__ENDPOINT` | str | не задано | server | Внутренний адрес S3 (MinIO, Ceph); пусто означает AWS по региону. |
| `HSE_STUDIO__S3__PUBLIC_ENDPOINT` | str | не задано | server | Адрес для подписанных ссылок, если клиенты видят S3 под другим именем, чем сервер. |
| `HSE_STUDIO__S3__REGION` | str | `us-east-1` | server | Регион подписи. |
| `HSE_STUDIO__S3__ACCESS_KEY` 🔒 | str | секрет, не печатается | server | Ключ доступа; пусто означает цепочку boto3. |
| `HSE_STUDIO__S3__SECRET_KEY` 🔒 | str | секрет, не печатается | server | Секретный ключ доступа. |
| `HSE_STUDIO__S3__PATH_STYLE` | bool | `true` | server | Адресация bucket в пути (MinIO, Ceph); false для виртуальной. |
| `HSE_STUDIO__S3__FS_ROOT` | Path | не задано | server | Каталог объектов, когда bucket не задан. |
| `HSE_STUDIO__S3__MAX_OBJECT_BYTES` | int | `2147483648` | server | Предел размера одного объекта. |
| `HSE_STUDIO__S3__MULTIPART_THRESHOLD_BYTES` | int | `67108864` | server | С какого размера загрузка идёт частями. |
| `HSE_STUDIO__S3__CORS_ORIGINS` | `list[str]` | пусто | server | Источники, которым бакет разрешает читать подписанные ссылки (pdf.js ходит туда с Range); пусто означает не трогать CORS бакета. |
| `HSE_STUDIO__S3__PRESIGN_TTL_S` | int | `300` | server | Срок подписанной ссылки по умолчанию. |
| `HSE_STUDIO__ADMIN__ALLOWED_HOSTS` | `list[str]` | пусто | server | Имена, под которыми открывается админка (заголовок Host): admin.example.org, *.example.org. Пусто: без ограничения. |
| `HSE_STUDIO__ADMIN__ALLOWED_CIDRS` | `list[str]` | пусто | server | IP и CIDR клиентов, которым открыта админка (адрес по auth.trusted_proxies). Пусто: без ограничения. Заданы оба списка: нужно пройти оба. |
| `HSE_STUDIO__EGRESS__ALLOWLIST` | `list[str]` | пусто | server | Внутренние узлы, к которым пользователям можно ходить: имя (git.corp.local, *.corp.local), IP или CIDR. Адреса метаданных облака и link-local закрыты всегда. |
| `HSE_STUDIO__RATE_LIMIT__ENABLED` | bool | `true` | server | Включить ограничение частоты (счётчики по реплике api). |
| `HSE_STUDIO__RATE_LIMIT__SCALE` | float | `1.0` | server | Множитель лимитов: больше 1 ослабляет (организация за одним NAT), меньше 1 ужесточает. |
| `HSE_STUDIO__OBSERVABILITY__HEALTH_TOKEN` 🔒 | str | секрет, не печатается | server | Bearer-токен, по которому /health/ready отдаёт детали проверок; без него детали только админу. |
| `HSE_STUDIO__OBSERVABILITY__METRICS_TOKEN` 🔒 | str | секрет, не печатается | server | Bearer-токен для /metrics; без токена эндпоинт отвечает 404. |
| `HSE_STUDIO__HSE_PERSONS__BASE_URL` | str | `https://www.hse.ru` | оба | HSE site origin. |
| `HSE_STUDIO__HSE_PERSONS__LIST_PATH` | str | `/org/persons/` | оба | Directory listing path (facets appended). |
| `HSE_STUDIO__HSE_PERSONS__USER_AGENT` | str | `Mozilla/5.0 (compatible; hse-doc-studio; +https://github.com/AlexeyShalaev/hse-doc-studio)` | оба | Identifying, honest User-Agent for outbound directory requests. |
| `HSE_STUDIO__HSE_PERSONS__CAMPUS_UDEPT` | `dict[str, str]` | `{'moscow': '', 'spb': '135083', 'nn': '135288', 'perm': '135213'}` | оба | Friendly campus key → top-level `udept` id (Moscow is the default, no param). |
| `HSE_STUDIO__HSE_PERSONS__REQUEST_TIMEOUT_S` | float | `15.0` | оба | Timeout for a single directory request. |
| `HSE_STUDIO__HSE_PERSONS__MIN_REQUEST_INTERVAL_S` | float | `3.0` | оба | Global minimum gap between outbound requests (honours the site's Crawl-delay: 3). |
| `HSE_STUDIO__HSE_PERSONS__MAX_CONCURRENCY` | int | `2` | оба | Bounded concurrent outbound requests (second guard). |
| `HSE_STUDIO__HSE_PERSONS__RETRIES` | int | `2` | оба | Retries on timeout / 5xx / 429 (honours Retry-After). |
| `HSE_STUDIO__HSE_PERSONS__LIST_CACHE_TTL_S` | float | `900.0` | оба | TTL of a cached listing page (querystring-keyed). |
| `HSE_STUDIO__HSE_PERSONS__DETAIL_CACHE_TTL_S` | float | `86400.0` | оба | TTL of a cached profile detail (id-keyed). |
| `HSE_STUDIO__HSE_PERSONS__FACETS_CACHE_TTL_S` | float | `86400.0` | оба | TTL of a cached facet vocabulary (campus-keyed). |
| `HSE_STUDIO__SHARING__LINKS_ENABLED` | bool | не задано | server | Разрешить ссылки на проекты (по умолчанию да); заданное значение блокирует правку в админке. |
| `HSE_STUDIO__SHARING__MAX_LINK_ROLE` | reader / reviewer / editor | не задано | server | Предел роли по ссылке: reader, reviewer или editor (по умолчанию editor); блокирует правку. |
| `HSE_STUDIO__SHARING__GUEST_SESSION_DAYS` | int | `30` | server | Срок гостевой сессии по ссылке, суток (скользящий). |
| `HSE_STUDIO__MODE` | local / server | `local` | оба | Instance mode: 'local' (single-user install) or 'server' (shared; not supported yet). |
| `HSE_STUDIO__DATA_DIR` | Path | `~/.config/hse-studio` | оба | Local data storage directory |
| `HSE_STUDIO__HOST_DATA_DIR` | str | не задано | оба | Host path of data_dir for sibling-container mounts; None when backend runs natively. |
| `HSE_STUDIO__PACKS_DIR` | Path | каталог `packs` монорепы, в образе `/app/packs` | оба | Directory with template packs (auto-detected from monorepo root locally; /app/packs in docker) |
| `HSE_STUDIO__STATIC_DIR` | Path | не задано | оба | Serve built frontend from this directory (all-in-one mode) |
| `HSE_STUDIO__DOCKER_BINARY` | str | не задано | оба | Explicit path to the docker CLI; empty means auto-discovery (PATH, then known locations). |
| `HSE_STUDIO__GITHUB_REPO` | str | `AlexeyShalaev/hse-doc-studio` | оба | owner/repo on GitHub — source of release/changelog info and the canonical source link. |
| `HSE_STUDIO__IMAGE_BASE` | str | `ghcr.io/alexeyshalaev/hse-doc-studio` | оба | GHCR image base for the published images (owner must be lowercase for GHCR). |
| `HSE_STUDIO__SOURCE_URL` | str | `https://github.com/AlexeyShalaev/hse-doc-studio` | оба | Canonical project source URL shown in About. |
| `HSE_STUDIO__LICENSE_NAME` | str | `Apache-2.0` | оба | License shown in About. |
| `HSE_STUDIO__UPDATE_FEED_URL` | str | пусто | оба | Release feed for update checks. Empty → the official GitHub Releases of `github_repo`; `off` (or none/disabled/-/0/false) disables the check for offline installs. |
| `HSE_STUDIO__UPDATE_CHECK_TIMEOUT_S` | float | `8.0` | оба | Timeout for one release-feed request — a slow feed must not hang the About screen. |
| `HSE_STUDIO__AUTO_UPDATE_INTERVAL_S` | float | `21600` | оба | How often the background auto-update checks the feed (the toggle itself is a user setting). |
| `HSE_STUDIO__AUTO_UPDATE_STARTUP_DELAY_S` | float | `300` | оба | Delay before the first auto-update check — never replace a container the user just started. |
| `HSE_STUDIO__BUILT` | str | пусто | оба | Build timestamp (ISO-8601) baked into the image by CI via the HSE_STUDIO_BUILT build-arg. Empty in a source checkout — a dev run has no build date to show. |
| `HSE_STUDIO__RELEASE_NOTES_FILE` | Path | `release-notes.json` монорепы, в образе `/app/release-notes.json` | оба | Curated bilingual release notes (release-notes.json), read once at startup. |
