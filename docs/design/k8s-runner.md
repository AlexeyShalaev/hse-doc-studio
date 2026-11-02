# Исполнитель kubernetes: под на задачу

Этап из раздела 14 `docs/design/collaboration.md` («исполнители docker, podman, kubernetes») для установки в Kubernetes. Раннер (`hse-doc-studio runner`) в режиме `executor=kubernetes` запускает TeX-сборку отдельным подом в своём namespace через Kubernetes API, без `docker.sock` и `hostPath`.

Решения ниже приняты по умолчанию; неочевидные помечены **Развилка**.

## 1. Что меняется и что нет

| Вид задачи | Где выполняется сейчас | В режиме kubernetes |
|---|---|---|
| `compile` (latexmk, texcount) | соседний контейнер через `docker run` | под на задачу |
| `compile` copy-only, проверки (`run_checks`) | процесс раннера (Python) | без изменений, в поде раннера |
| `verify.detached`, `pack.submission` | процесс раннера | без изменений |
| `office.convert` | HTTP в постоянный Gotenberg (`HSE_RUNNER__OFFICE_URL`) | без изменений |
| `ai.relay` | HTTP из процесса раннера | без изменений |

Docker нужен раннеру только для TeX: остальное уже работает без контейнеров. Поэтому исполнитель kubernetes заменяет ровно одну деталь: реализацию `run(...)` сборки (`DockerCompileExecutor`) и проверку окружения перед сборкой (`DockerImageManager.docker_status/inspect`). `EmbeddedCompileRunner`, разбор потока сборки, проверки, отправка выходов, протокол раннера и api не меняются. Для этого `EmbeddedCompileRunner` принимает протоколы `ITexBuildExecutor` и `IBuildEnvironment` (`infra/compile/backend.py`) вместо конкретных docker-классов.

Режим выбирает `HSE_RUNNER__EXECUTOR=docker|kubernetes` (по умолчанию `docker`, как было). Настройки исполнителя в `HSE_RUNNER__K8S__*`.

## 2. Жизненный цикл пода сборки

1. **Создание.** `POST pods` в namespace исполнителя. Имя `hds-build-<8 символов id задачи>-<случайные 8>`, метки `app.kubernetes.io/managed-by=hse-doc-studio-runner`, `hse-doc-studio/component=build`, `hse-doc-studio/runner=<экземпляр раннера>`, `hse-doc-studio/job=<id задачи>`.
2. **Ожидание запуска.** Опрос `GET pod` до фазы `Running` не дольше `pod_start_timeout_s` (по умолчанию 300 с: первый pull образа TeX Live занимает минуты). `ErrImagePull`, `ImagePullBackOff`, `InvalidImageName` дают сбой `image_missing` (тот же код, что у docker); `Unschedulable`, `CreateContainerConfigError`, фаза `Failed` и таймаут дают `build_backend_unavailable`.
3. **Вход.** Рабочая папка задачи уходит tar-потоком через `pods/exec` (раздел 3).
4. **Сборка и лог.** Контейнер ждёт метку готовности входа, запускает latexmk, затем texcount. Раннер читает `pods/log?follow=true&timestamps=true` и передаёт строки в журнал задачи тем же путём, что строки `docker run` (`JobContext.log`, далее api и SSE). Конец сборки и код возврата приходят строкой-маркером с одноразовым nonce пода, слова и символы texcount так же. Пользовательский документ не угадает nonce, поэтому подделать маркер из `\typeout` нельзя.
5. **Выход.** `pods/exec` с `tar c` каталога `.build/<doc_id>` документа; раннер распаковывает его в свою рабочую папку (с фильтром `data`: без абсолютных путей, `..`, ссылок и устройств, с пределом размера). Дальше всё как у docker: при неуспехе сбрасывается `.fdb_latexmk`, при успехе PDF перекладывается к исходнику, страницы берутся из `.log`.
6. **Удаление.** Под удаляется (`gracePeriodSeconds=0`) в `finally`, при успехе, ошибке и отмене. Удаление идёт под `asyncio.shield`, чтобы повторная отмена посреди него не оставила под жить.

Контейнер сборки после маркера конца не выходит, а спит до удаления: иначе выход забрать нечем (exec в завершённый контейнер невозможен).

**Развилка: голый Pod, а не Job.** Job добавляет контроллер повторов (`backoffLimit`), задержку контроллера и отдельный объект для уборки, а повторы задач уже ведёт очередь api (аренда, до двух повторов). Нужен один конкретный под, в который раннер делает exec; у Pod есть и `activeDeadlineSeconds`, и `restartPolicy: Never`. Права на `jobs` поэтому не нужны.

## 3. Вход и выход без общего тома

**Развилка: `pods/exec` с tar, а не общий том или HTTP.** Варианты:

| Вариант | Почему нет |
|---|---|
| общий PVC раннера и подов | RWO: под задачи должен попасть на узел раннера; в целевом кластере это так (local-path, один узел), но на этом нельзя строить; RWX есть не везде |
| ConfigMap или Secret со входом | предел объекта 1 MiB, проекты с картинками больше; лишние права на запись секретов |
| init-контейнер скачивает вход у раннера по одноразовому токену, sidecar отдаёт выход | раннеру нужен свой HTTP-сервер и Service, поду задачи нужна сеть до раннера (а значит, и путь в кластер), выход отдаёт sidecar с синхронизацией по меткам; больше подвижных частей и шире поверхность атаки |
| `pods/attach` (stdin вход, stdout выход) | одно соединение на всю сборку: обрыв на 10-й минуте теряет результат; лог и выход перемешаны |
| **`pods/exec` + tar** (выбрано) | так работает `kubectl cp`; в образе TeX есть `sh`, `tar`, `head`; поду задачи сеть не нужна вовсе |

Выбранный путь даёт поду задачи **полную сетевую изоляцию**: чарт кладёт NetworkPolicy, запрещающую подам сборки весь вход и выход (раздел 6). Цена: право `pods/exec` у ServiceAccount раннера. Оно ограничено его namespace, где живут только поды сборки, и Role не даёт ни `secrets`, ни других ресурсов.

Детали протокола. Используется websocket-подпротокол `v4.channel.k8s.io` (байт канала, затем данные: 0 stdin, 1 stdout, 2 stderr, 3 статус). В v4 нельзя закрыть stdin отдельно от соединения, поэтому вход передаётся с известной длиной: `head -c <N> | tar -x -f - -C /work && touch /tmp/.hds/ready`. Выход: `tar -c -f - -C /work <путь>` в stdout до закрытия соединения; код выхода из статуса канала 3. В вход попадает вся рабочая папка, кроме чужих `.build/`; `.build/<doc_id>` этого документа входит, чтобы latexmk пересобирал инкрементально, как с docker. Размер выхода ограничен `max_output_bytes` (по умолчанию 512 MiB).

Websocket даёт пакет `websockets` (extra `kubernetes`, в образе установлен). REST-часть (`pods`, `pods/log`) идёт через `httpx`. **Развилка: свой тонкий клиент, а не `kubernetes_asyncio`.** Нужно пять вызовов; официальный клиент тянет aiohttp и сгенерированные модели на десятки мегабайт, а тесты на фейковом API проще с узким портом `IKubeApi` (`infra/compile/k8s/api.py`).

Доступ к API: in-cluster ServiceAccount (`/var/run/secrets/kubernetes.io/serviceaccount/{token,ca.crt,namespace}`, адрес из `KUBERNETES_SERVICE_HOST/PORT`). Токен перечитывается из файла раз в минуту: projected-токены ротируются. Для проверки вне кластера (kind) адрес, файл токена и CA задаются `HSE_RUNNER__K8S__API_URL`, `TOKEN_FILE`, `CA_FILE`.

## 4. Лог, таймауты, отмена, сироты

- **Лог.** Строки с метками времени; при обрыве потока (таймаут прокси, рестарт apiserver) раннер переподключается с `sinceTime` и пропускает уже прочитанные строки по метке времени.
- **Тишина.** Нет строк дольше `tex_idle_timeout_s` (как у docker, 120 с): под удаляется, сборка падает с `[error] no output for …`.
- **Предел времени.** `activeDeadlineSeconds` пода = `HSE_RUNNER__K8S__ACTIVE_DEADLINE_S` (по умолчанию 1800). Это страховка на случай, если раннер умер, не убрав под: основное ограничение времени по-прежнему делают аренда и таймаут задачи в api, отмена которых удаляет под.
- **Отмена.** Цикл раннера отменяет asyncio-задачу; исполнитель ловит `CancelledError`, удаляет под и пробрасывает отмену.
- **Сироты.** Два механизма. Под сборки получает `ownerReference` на под раннера (имя и uid из downward API, `HSE_RUNNER__K8S__OWNER_POD_NAME/UID`): удалили под раннера, сборщик мусора Kubernetes удалит его поды. Рестарт процесса внутри того же пода (OOM, падение) ловит уборка на старте: раннер удаляет поды с меткой своего экземпляра (uid пода раннера, а без него имя раннера), как `sweep_build_containers` у docker. **Развилка:** уборка только по своей метке, а не всех подов namespace: несколько раннеров в одном namespace (будущий KEDA) не убивают сборки друг друга.
- **Параллелизм.** Без изменений: `HSE_RUNNER__CONCURRENCY` слотов цикла и тот же `CompileConcurrencyLimiter`. Подов сборки одновременно не больше `concurrency`. ResourceQuota namespace остаётся на совести оператора; при нехватке квоты создание пода падает с `build_backend_unavailable` и задача возвращается в очередь.

## 5. Образ, ресурсы, кэш TeX

- **Образ** тот же `HSE_RUNNER__TEX_IMAGE` (`texlive/texlive:TL2024-historic`). `imagePullPolicy: IfNotPresent`, при желании `imagePullSecrets`. Образ на несколько гигабайт: первый под на узле ждёт pull; заранее подтянуть можно DaemonSet-ом с этим образом (в чарт не входит, см. README чарта).
- **Ресурсы.** `requests` и `limits` CPU и памяти из `HSE_RUNNER__K8S__CPU_REQUEST/CPU_LIMIT/MEMORY_REQUEST/MEMORY_LIMIT` (по умолчанию 500m/2, 1Gi/4Gi, как у docker `--cpus 2 --memory 4g`), `ephemeral-storage` для `emptyDir` (`/work` и `/tmp` с `sizeLimit`).
- **Где под.** `nodeSelector`, `tolerations`, `priorityClassName`, `runtimeClassName` (gVisor или Kata для общих установок, как требует раздел 14) задаются JSON-ом в `HSE_RUNNER__K8S__*` и значениями чарта.
- **Кэш TeX.** **Развилка: по умолчанию без кэша.** У docker кэш это именованный том в `/root`, но в изолированном режиме (не root, read-only корень) TeX и так пишет в tmpfs `/tmp` и собирает формат на каждую сборку; под повторяет ровно этот профиль. PVC для кэша опционален (`HSE_RUNNER__K8S__TEX_CACHE_CLAIM`): монтируется в `/cache`, туда уходят кэши шрифтов (`TEXMFCACHE` для luaotfload, `XDG_CACHE_HOME` для fontconfig), формат остаётся в `/tmp`, чтобы параллельные поды не писали один файл формата. Нужен `ReadWriteMany` или один узел: с RWO на нескольких узлах под не запустится, это и записано в README.

## 6. Безопасность

Под сборки проходит Pod Security Standard **restricted**: `runAsNonRoot`, `runAsUser/runAsGroup/fsGroup` (по умолчанию 1000), `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `readOnlyRootFilesystem: true` (пишет только в `emptyDir` `/work` и `/tmp`), `automountServiceAccountToken: false`, `enableServiceLinks: false`. Секретов раннера и токенов задач в поде нет.

Под раннера в режиме kubernetes тоже restricted: без `hostPath`, без `docker.sock`, без init-контейнера с `chown`, корень только для чтения (`/tmp` это `emptyDir`), каталог данных на PVC.

NetworkPolicy (`runner.kubernetes.networkPolicy.enabled`, по умолчанию включена) выбирает поды сборки по меткам и не разрешает ни входа, ни выхода. Без CNI с поддержкой политик (flannel) она ничего не делает, но и не мешает.

RBAC: Role в namespace подов сборки:

| Ресурс | Глаголы | Зачем |
|---|---|---|
| `pods` | `create`, `get`, `list`, `delete` | создать, ждать, убрать сирот, удалить |
| `pods/log` | `get` | лог сборки |
| `pods/exec` | `create`, `get` | вход и выход; websocket-exec авторизуется как `get` в старых версиях и как `create` в новых |

`jobs`, `secrets`, `configmaps` не нужны. Остаточный риск: украденный токен ServiceAccount раннера позволяет запускать поды в этом namespace, но только те, что пропустит Pod Security restricted, и делать exec в поды сборки, где нет ничего, кроме исходников этой задачи. Поэтому поды сборки держите в отдельном namespace с меткой `pod-security.kubernetes.io/enforce=restricted`.

## 7. Чарт

- `runner.executor: docker|kubernetes`, по умолчанию `docker`: рендер существующих установок не меняется.
- При `kubernetes`: ServiceAccount раннера, Role и RoleBinding в `runner.kubernetes.namespace` (пусто значит namespace релиза; чужой namespace должен существовать), NetworkPolicy, PVC данных раннера (`runner.persistence`), downward API для владельца, `securityContext` restricted.
- Значения подов сборки: `runner.kubernetes.{image, resources, nodeSelector, tolerations, priorityClassName, runtimeClassName, imagePullSecrets, activeDeadlineSeconds, podStartTimeoutSeconds, runAsUser, texCache.existingClaim}`.

**Развилка: данные раннера на PVC.** Токен регистрации одноразовый (`max_uses=1`), а раннер хранит выданный токен в `data_dir/identity.json`: с `emptyDir` первый же рестарт пода оставил бы раннер без личности. Поэтому PVC (RWO, одна реплика). Альтернатива без PVC: постоянный токен раннера в Secret (`runner-token`, `HSE_RUNNER__RUNNER_TOKEN`), тогда `runner.persistence.enabled=false` и данные в `emptyDir`.

## 8. Точка расширения: KEDA

В этом этапе раннер в одной реплике. Масштабирование это число реплик раннера, а не подов сборки: под на задачу уже есть, и каждый раннер держит `concurrency` подов. Для KEDA нужно:

1. Личность на реплику: токен регистрации с `max_uses>1` (уже поддерживается админкой) и `emptyDir` вместо общего PVC, либо StatefulSet с PVC на реплику.
2. Метрика глубины очереди: скейлер `postgresql` KEDA по таблице `jobs` (`state='queued'` с тегом `tex`) или будущая метрика api.
3. Мягкая остановка уже есть: на SIGTERM цикл перестаёт брать задачи и дорабатывает текущие (`terminationGracePeriodSeconds` должен покрывать сборку).

Уборка сирот уже разделена по экземплярам (раздел 4), `ownerReference` привязывает поды к своей реплике, поэтому ScaledObject над Deployment раннера добавляется без изменений кода.

## 9. Тесты

- **Юнит** (`tests/unit/infra/compile/k8s/`): исполнитель на фейковом `IKubeApi`, который держит «файловую систему пода» во временном каталоге, распаковывает вход, исполняет сценарий сборки и отдаёт выход. Проверяются спецификация пода (restricted, ресурсы, размещение, владелец), успех с PDF и счётчиками, неуспех, отсутствие образа, тишина, отмена с удалением пода, обрыв лога, уборка сирот, предел выхода. Клиент API проверяется на `httpx.MockTransport` и разборе кадров exec.
- **Интеграция на kind** (`tests/integration/k8s/`, маркер `k8s`, пропускается без `HSE_TEST_K8S_*`): отдельная необязательная джоба CI поднимает kind, применяет RBAC и NetworkPolicy из чарта, собирает маленький образ с поддельными `latexmk`/`texcount` на busybox и гоняет исполнитель с токеном ServiceAccount раннера, то есть с ровно теми правами, что даёт чарт. Настоящий TeX Live в kind не тянется: образ на гигабайты, а проверяется механика пода, не TeX.
- **Чарт**: golden-рендер, restricted у подов раннера в режиме kubernetes, отсутствие `hostPath` и `docker.sock`, права Role.

## 10. Что не входит

- KEDA (раздел 8), podman-исполнитель.
- Pre-pull образа TeX DaemonSet-ом в чарте.
- Шрифты установки (`fonts_dir`) в поде: у раннера их и в docker-режиме нет.
