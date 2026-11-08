# Helm-чарт HSE Doc Studio

Серверный режим в Kubernetes: api (одна реплика, стратегия `Recreate`), по желанию раннер задач (исполнитель docker или kubernetes).
Postgres и S3-совместимое хранилище внешние, в чарт они не входят. Том исходников проектов
(`/data`) это PVC `ReadWriteOnce`: поэтому реплика одна и rolling-обновления нет.

## Установка

```bash
helm install studio deploy/helm/hse-doc-studio -f my-values.yaml
```

Минимум в `my-values.yaml`: `publicUrl`, `database.dsn`, `s3.*`, `secrets.secretsKey`,
`secrets.runnerBootstrapToken`. Рекомендуется не класть секреты в values, а завести Secret
заранее и указать `secrets.existingSecret`. Ключи Secret:
`dsn`, `secrets-key`, `s3-access-key`, `s3-secret-key`, `runner-bootstrap-token`,
необязательные `smtp-password`, `health-token`, `metrics-token`.

Ключ `secrets.secretsKey` (Fernet) нельзя терять: без него сохранённые секреты нечитаемы.

## Миграции

На первой установке схему создаёт сам api под advisory-локом. При `helm upgrade` перед заменой api
выполняется Job `hse-doc-studio db upgrade` (hook `pre-upgrade`), api после этого стартует без
автомиграции. Job берёт Secret предыдущей версии выпуска: меняя секреты, обновляйте их отдельно от версии образа
или используйте `secrets.existingSecret`. Отключить: `migrations.enabled=false` (тогда мигрирует api).

## Обновление версии

Два пути, выбирайте один.

**Оператор (по умолчанию).** Исполнитель выключен (`HSE_STUDIO__SERVER_UPDATE__EXECUTOR=none`): Студия проверяет релизы и уведомляет админов, страница «Обновления» показывает команду. Ставьте так, откат при неуспехе делает Helm:

```bash
helm upgrade hse-doc-studio deploy/helm/hse-doc-studio --reuse-values --set image.tag=<версия> --atomic --wait
```

**Установка раннеров из админки: `runner.installFromUi.enabled=true`.** По умолчанию выключено (на проде общие раннеры включают сознательно). Включение добавляет ServiceAccount `<релиз>-runner-ui` с Role только на поды сборки и ServiceAccount `<релиз>-api` с Role на Deployment (`create`, `list`, `update`, `delete`; `update` нужен обновлению раннера на месте), Secret (`create`, `delete`) и PersistentVolumeClaim (`create`, `delete`) в namespace релиза, переключает на него api и включает кнопку «На этой же машине» на странице «Раннеры». Role и RoleBinding Студия создавать не может, ClusterRole нет. Ход установок хранится в памяти одного процесса api, поэтому функция рассчитана на одну реплику (как и сам чарт). Лимиты раннера задаются `runner.installFromUi.resources`, `buildResources`, `maxCpu`, `maxMemory` (их же можно выбрать в форме установки в границах). Поды сборки таких раннеров по умолчанию идут в namespace релиза; `runner.installFromUi.buildNamespace` выносит их в свой namespace (раннер остаётся в namespace релиза): туда переезжают Role и RoleBinding `<релиз>-runner-ui-builds`, запрет сети подов сборки, квота и LimitRange из `runner.kubernetes.quota` и `limitRange` (общий с `runner.kubernetes.namespace` namespace получает их один раз). Namespace чарт не создаёт: создайте его заранее с меткой `pod-security.kubernetes.io/enforce=restricted`, после `helm upgrade` нажмите «Обновить» у каждого раннера из админки. Подробности: `docs/ru/deploy/runners.md`.

**Кнопки в админке: `updater.enabled=true`.** Чарт добавляет под `updater` (исполнитель `kubernetes`), его ServiceAccount и Role и переключает api на этот исполнитель:

```bash
helm upgrade hse-doc-studio deploy/helm/hse-doc-studio --reset-then-reuse-values \
  --set updater.enabled=true --set updater.token=$(openssl rand -hex 32)
```

Токен (общий секрет api и апдейтера) можно завести ключом `updater-token` в `secrets.existingSecret`. Role строго на namespace релиза: `get` и `patch` одного Deployment `<релиз>-api` по имени (`resourceNames`), Job (`create`, `get`, `list`, `watch`, `delete`), `pods` (`get`, `list`) и `pods/log` (`get`). Секретов, других namespace и `ClusterRole` нет; под апдейтера проходит Pod Security restricted, сети он не ограничивает и NetworkPolicy чарта не меняет.

Исполнитель проверяет образ (дайджест релиза записывается в Deployment, подпись cosign при желании проверяет Job), `db current` Job’ом на новом образе, останавливает api, применяет миграции Job’ом, меняет образ и ждёт здоровья. Снимка базы нет: перед обновлением идёт полный бэкап (если настроено назначение) либо нужно подтвердить риск; образ откатывается сам, только пока миграции не меняли схему, иначе статус «Нужны руки» с инструкцией. Опирается на Deployment и Job, поэтому работает и без записи релиза Helm. Дрейф: после обновления из админки зафиксируйте версию в values (`image.tag`), иначе следующий `helm upgrade` вернёт образ из values. Раннер и сам апдейтер обновляются `helm upgrade`. Подробно: `docs/design/auto-update.md`, раздел 5а.

Проверку и уведомления выключает `api.extraEnv.HSE_STUDIO__SERVER_UPDATE__ENABLED=false`.

## Ingress и долгий опрос

Раннер держит запрос опроса до 25 секунд. Аннотации по умолчанию рассчитаны на ingress-nginx
(`proxy-read-timeout: 75`, `proxy-buffering: off`). Для другого контроллера задайте
`ingress.annotations` с read-timeout не меньше 60 секунд и выключенной буферизацией.

## Раннер

`runner.enabled=true` добавляет раннер задач. Исполнитель сборки TeX выбирает `runner.executor`:

- `docker` (по умолчанию, как раньше): соседние контейнеры через `docker.sock` узла;
- `kubernetes`: под на каждую сборку в своём namespace через Kubernetes API, без сокета и `hostPath`.

Раннер всегда в одной реплике (`runner.replicas` не больше 1): токен регистрации одноразовый.

### executor=docker

Все поды работают от числового uid/gid из `podSecurityContext` (10001, как пользователь `app` в образе). Каталог `runner.dataDir` на узле создаётся от root, поэтому initContainer `fix-data-dir` выдаёт его этому пользователю. Из-за `docker.sock` и `chown` в initContainer под раннера не проходит Pod Security Standard restricted, api и migrate проходят.

Сокет эквивалентен root на узле, а на узлах с containerd Docker нет вовсе: используйте выделенные узлы (`runner.nodeSelector`, `runner.tolerations`) или исполнитель `kubernetes`.

### executor=kubernetes

Чарт создаёт:

- ServiceAccount раннера и Role с RoleBinding в namespace подов сборки (`runner.kubernetes.namespace`, пусто значит namespace релиза): только `pods` (create, get, list, delete), `pods/log` (get) и `pods/exec` (create, get). Ни `secrets`, ни `jobs`, ни ClusterRole;
- NetworkPolicy, которая запрещает подам сборки весь вход и выход (`runner.kubernetes.networkPolicy.enabled`; без CNI с поддержкой политик она ничего не делает; действует и для подов сборки раннеров из админки);
- по желанию: NetworkPolicy исходящего доступа раннеров (`runner.networkPolicy`), ResourceQuota и LimitRange отдельного namespace сборок (`runner.kubernetes.quota`, `limitRange`; ставятся в `runner.kubernetes.namespace` и `runner.installFromUi.buildNamespace`, если они не namespace релиза); у подов сборки requests и limits `cpu`, `memory`, `ephemeral-storage`. Подробно: `docs/ru/deploy/runner-isolation.md`;
- экран изоляции раннеров в админке: выжимку values Студия получает всегда (`HSE_STUDIO__RUNNER_CLUSTER__DECLARED`), а живое состояние (NetworkPolicy, ResourceQuota, LimitRange, метки Pod Security) читает только с `runner.isolationInfo.readCluster=true`: Role с `get` и `list` на эти объекты в namespace релиза и namespace подов сборки (обоих видов раннеров) и ClusterRole с `get` на эти namespace. По умолчанию выключено;
- PVC данных раннера `<release>-runner-data` (`runner.persistence`): там `identity.json` с выданным раннеру токеном, кэш блобов и рабочие папки. RWO, `local-path` подходит. Без тома (`runner.persistence.enabled=false`) положите постоянный токен раннера в Secret под ключом `runner-token`, иначе рестарт пода оставит раннер без личности;
- Deployment раннера со стратегией `Recreate`, проходящий Pod Security restricted: `runAsNonRoot`, `seccompProfile: RuntimeDefault`, `drop: [ALL]`, корень только для чтения.

Поды сборки тоже restricted, без токена ServiceAccount и без сети; исходники уходят в под и результат возвращается через `exec`, общий том не нужен. Под удаляется после сборки, при отмене задачи и по `activeDeadlineSeconds`; поды, пережившие процесс раннера, убирает сборщик мусора (владелец это под раннера) и уборка на старте.

Отдельный namespace под сборки рекомендуется:

```bash
kubectl create namespace hds-builds
kubectl label namespace hds-builds pod-security.kubernetes.io/enforce=restricted
```

```yaml
runner:
  enabled: true
  executor: kubernetes
  concurrency: 2
  persistence:
    storageClassName: local-path
    size: 10Gi
  kubernetes:
    namespace: hds-builds
    # image: ""                       # по умолчанию texlive/texlive:TL2024-historic
    resources:
      requests: {cpu: 500m, memory: 1Gi}
      limits: {cpu: "2", memory: 4Gi}
    activeDeadlineSeconds: 1800
    nodeSelector: {}
    tolerations: []
    # runtimeClassName: gvisor        # для общих установок, если RuntimeClass есть
    # texCache: {existingClaim: tex-cache}
    # fonts: {existingClaim: studio-fonts}   # PVC со шрифтами Times New Roman, Arial, Consolas
```

Образ TeX Live весит несколько гигабайт: первая сборка на узле ждёт его pull (`podStartTimeoutSeconds`, по умолчанию 300). Заранее подтянуть можно DaemonSet-ом с этим образом и командой `sleep`. Кэш TeX по умолчанию не нужен (формат собирается во временном каталоге пода); `texCache.existingClaim` монтирует PVC с кэшем шрифтов, нужен `ReadWriteMany` или один узел. `fonts.existingClaim` монтирует PVC со шрифтами (`.ttf`, `.otf`, `.ttc`) в поды сборки только для чтения: шаблоны ГОСТ просят Times New Roman, Arial и Consolas, а в образе TeX Live их нет и Studio не поставляет их из-за лицензии. Без шрифтов шаблоны с `\IfFontExistsTF` берут свободную замену, а прямой `\setmainfont{Arial}` даёт сбой `font_missing`.

Проверка в кластере после установки: собрать документ, в журнале задачи видна строка `pod=hds-builds/hds-build-…`, а `kubectl -n hds-builds get pods -w` показывает появление и удаление пода. Устройство и развилки: `docs/design/k8s-runner.md`.

## Офисные задачи (Gotenberg)

Задачи с тегом `office` (pptx, docx и другие в PDF) раннер отправляет в постоянный Gotenberg. `services.officeConvert.enabled=true` ставит его в namespace релиза:

```yaml
services:
  officeConvert:
    enabled: true
    image: {repository: gotenberg/gotenberg, tag: 8.39.0-libreoffice}   # точный тег, вариант без Chromium
    replicas: 1
    resources:
      requests: {cpu: 250m, memory: 512Mi, ephemeral-storage: 256Mi}
      limits: {cpu: "2", memory: 2Gi, ephemeral-storage: 2Gi}
    timeout: 180s          # предел одной конвертации
    tmpSizeLimit: 1Gi      # emptyDir /tmp
    networkPolicy: {enabled: true}
```

- Deployment и Service `<релиз>-office-convert:3000`; под проходит Pod Security restricted (uid 1001 образа, корень только для чтения, `/tmp` и `/home/gotenberg` в emptyDir, пробы на `/health`), webhook и загрузка по ссылке выключены.
- NetworkPolicy: вход только от подов раннеров релиза на порт 3000, выход закрыт.
- Адрес получают раннер чарта (`HSE_RUNNER__OFFICE_URL`, если `runner.officeUrl` пуст) и раннеры из админки (`HSE_STUDIO__RUNNER_INSTALL__OFFICE_URL`, при установке и при «Обновить»). Свой `runner.officeUrl` перекрывает встроенный для обоих.
- Egress-политика раннеров (`runner.networkPolicy`) разрешает встроенный Gotenberg сама.

Пример значений: `ci/values-office.yaml`; в CI тот же рендер ставится на kind в namespace с restricted и конвертирует документ. Подробнее: `docs/ru/deploy/runners.md`, «Офисные задачи в кластере».

## Хранилище для раннеров и браузеров вне кластера

`s3.endpoint` это внутренний адрес S3 (`http://<сервис>.<namespace>.svc`): по нему ходят api и раннеры в кластере. Личные раннеры на ноутбуках, локальные Студии и браузеры (PDF по ссылке) его не откроют. Для них задайте публичный адрес: `s3.publicEndpoint: https://files.example.org`. Ссылки подписываются сразу для этого хоста; раннер чарта по-прежнему получает внутренний адрес.

- Маршрут к MinIO (Ingress или Gateway API, TLS, только `GET`, `HEAD`, `PUT` на путях бакета, `Host` без изменений) чарт не создаёт, примеры в `docs/ru/deploy/runners.md`, раздел «Раннеры вне сети сервера».
- Если публиковать хранилище нельзя: `s3.outsideRunnerAccess: proxy`, внешние раннеры отправляют результат через api.
- `s3.sharedRunnersOutside: true` считает внешними и общие раннеры (например, раннер на отдельной ВМ).
- `s3.corsOrigins` выставляет CORS бакета для AWS, Yandex Object Storage и Ceph; MinIO отвечает на CORS сам.

Пример значений: `ci/values-public-s3.yaml`.

## Бэкапы

`backups.enabled=true` включает начальную настройку бэкапов: на первом старте api создаёт назначение по умолчанию
(`backups.destination`) и расписание (`backups.schedule`), но только если назначений в базе ещё нет, поэтому правки в админке
рестарты не затирают. Остальное (новые назначения, смена расписания) делается в админке.

- `backups.local.enabled=true` добавляет отдельный PVC `<release>-backups` (политика `keep`), монтирует его в `/backups` и задаёт
  `HSE_STUDIO__BACKUPS__LOCAL_ROOT`. `backups.local.persistence.existingClaim` берёт готовый том. Том должен быть не там же, где `/data`.
- `backups.destination.kind=s3`: обязателен `bucket`; ключи в `accessKey` и `secretKey` или в Secret (`backup-access-key`, `backup-secret-key`).
- `backups.encryptionMode=passphrase`: фраза от 12 символов в `backups.passphrase` или в Secret (`backup-passphrase`).
- При `backups.enabled=false` чарт ничего не добавляет, приложение работает с умолчаниями.

Восстановление в Kubernetes: см. раздел «Kubernetes (Helm)» в `docs/ru/deploy/backups.md`.

## Проверка

```bash
helm lint deploy/helm/hse-doc-studio -f deploy/helm/hse-doc-studio/ci/values-test.yaml --strict
cd services/api && uv run pytest tests/unit/test_helm_chart.py   # UPDATE_GOLDEN=1 обновляет эталоны рендера (docker и kubernetes)
```
